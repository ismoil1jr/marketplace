"""Tovar bo'yicha murojaat: mijoz va do'kon menejeri o'rtasidagi chat. Har bir tovar uchun alohida (OLX kabi).

Mijoz: tovar sahifasida «Sotuvchi bilan bog'lanish» -> /s/<do'kon>/chat/<tovar> (Telegram orqali kirgan bo'lishi kerak).
Birinchi xabar yuborilganda Tovar Murojaat yaratiladi va boshiga tovar kartasi (turi «Tovar») qo'yiladi:
uni hech kim tahrirlay yoki o'chira olmaydi, menejer qaysi tovar haqida gap ketayotganini doim ko'radi.
Menejer: Sotuv paneli -> «Tovar murojaatlari» (do'kon egasi va sotuv menejerlari; kuryer/upakovkachi emas).

Xabar: matn, rasm (yopiq fayl, faqat shu chatning ikki tomoniga ko'rinadi — rasm()), stiker (STICKERS).
O'z xabarini tahrirlash (faqat matn) va o'chirish mumkin. ✓ — serverga yetdi, ✓✓ — ikkinchi tomon o'qidi (oqilgan).
Yangilanish: brauzer since (oxirgi ko'rgan modified) bilan so'raydi — yangi, tahrirlangan, o'chirilgan va o'qilgan
xabarlar qaytadi. Mijoz sahifasi so'rab turadi (polling), menejerga Frappe realtime («mp_tovar_chat»).
client_id — brauzer bergan id: internet uzilib «Qayta yuborish» bosilsa xabar ikki marta tushmaydi.
"""

import io
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_datetime, now_datetime

from marketplace.permissions import COURIER_MEMBERS, PACKER_MEMBERS, is_admin

TM, XABAR = "Tovar Murojaat", "Tovar Murojaat Xabar"
MIJOZ, SOTUVCHI = "Mijoz", "Sotuvchi"
# Sinov to'plami: katta emoji-stikerlar (Android/iPhone'da rangli shrift bor)
STICKERS = (
	"👍", "❤️", "😂", "😍", "🥰", "😊", "🤔", "😮", "😢", "😡", "🙏", "👏",
	"🔥", "🎉", "💯", "👌", "🤝", "😎", "🥳", "😅", "🤗", "✅", "📦", "🛍️",
)
TEXT_MAX = 4000
IMAGE_MAX = 10 * 1024 * 1024
IMAGE_SIDE = 1600
LAST = 300  # chat ochilganda oxirgi nechta xabar
FIELDS = ["name", "murojaat", "kimdan", "turi", "matn", "rasm", "stiker", "client_id", "oqilgan", "tahrirlangan",
          "ochirilgan", "creation", "modified"]


# ---------------- Umumiy ----------------


def _clean_text(value):
	text = re.sub(r"[ \t]+\n", "\n", (value or "").replace("\r\n", "\n")).strip()
	if not text:
		frappe.throw(_("Xabar bo‘sh"))
	if len(text) > TEXT_MAX:
		frappe.throw(_("Xabar juda uzun ({0} belgigacha)").format(TEXT_MAX))
	return text


def preview(m):
	"""Ro'yxatdagi oxirgi xabar matni."""
	if m.get("turi") == "Rasm":
		return "🖼 " + _("Rasm")
	if m.get("turi") == "Stiker":
		return m.get("stiker") or ""
	if m.get("turi") == "Tovar":
		return _("Tovar bo‘yicha murojaat")
	return (m.get("matn") or "")[:200]


def _msg(m, side):
	deleted = cint(m.ochirilgan)
	return {
		"id": m.name,
		"client_id": m.client_id,
		"kimdan": m.kimdan,
		"mine": m.kimdan == side,
		"turi": m.turi,
		"matn": None if deleted else m.matn,
		"stiker": None if deleted else m.stiker,
		"rasm": f"/api/method/marketplace.sotuv.tovar_chat.rasm?xabar={m.name}" if m.rasm and not deleted else None,
		"vaqt": str(m.creation),
		"oqilgan": bool(m.oqilgan),
		"tahrirlangan": bool(m.tahrirlangan),
		"ochirilgan": bool(deleted),
		"modified": str(m.modified),
	}


def product_cards(shop, codes):
	"""Tovar kartasi: nomi, rasmi, narxi, saytdagi havolasi (tovar keyin yashirilgan bo'lsa ham nomi qoladi)."""
	from marketplace import storefront

	codes = list({c for c in codes if c})
	if not codes:
		return {}
	items = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name", "image"])}
	thumbs = storefront._get_thumbnails(codes)
	prices = storefront._get_prices(codes)
	return {
		c: {
			"code": c, "name": items[c].item_name, "thumb": thumbs.get(c) or items[c].image,
			"price": prices.get(c), "price_text": storefront.fmt_sum(prices[c]) if prices.get(c) else None,
			"url": f"/s/{shop}/p/{c}",
		}
		for c in codes if c in items
	}


def _messages(thread, side, since=None):
	"""since bo'lmasa — oxirgi LAST ta (o'chirilganlarsiz); bo'lsa — shu paytdan keyin o'zgargan hammasi."""
	if since:
		rows = frappe.get_all(XABAR, filters={"murojaat": thread, "modified": [">=", get_datetime(since)]},
		                      fields=FIELDS, order_by="creation asc", limit_page_length=1000)
	else:
		rows = frappe.get_all(XABAR, filters={"murojaat": thread, "ochirilgan": 0}, fields=FIELDS,
		                      order_by="creation desc", limit_page_length=LAST)[::-1]
	return [_msg(m, side) for m in rows]


def _cursor(messages, since=None):
	return max([m["modified"] for m in messages] + ([since] if since else []), default=None)


def _mark_read(thread, reader):
	"""reader ochdi: ikkinchi tomonning o'qilmagan xabarlari — o'qildi (✓✓). modified ham yangilanadi —
	ikkinchi tomon since bilan so'raganda belgini ko'radi."""
	other = SOTUVCHI if reader == MIJOZ else MIJOZ
	names = frappe.get_all(XABAR, filters={"murojaat": thread, "kimdan": other, "oqilgan": ["is", "not set"], "ochirilgan": 0},
	                       pluck="name")
	if not names:
		return 0
	now = now_datetime()
	t = frappe.qb.DocType(XABAR)
	frappe.db.savepoint("mp_read")
	try:
		frappe.qb.update(t).set(t.oqilgan, now).set(t.modified, now).where(t.name.isin(names)).run()
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		# Ikkinchi tomon shu payt xabarini tahrirladi/o'chirdi — keyingi so'rovda (3 soniyadan keyin) belgilanadi
		frappe.db.rollback(save_point="mp_read")
		return 0
	if reader == MIJOZ:
		shop = frappe.db.get_value(TM, thread, "shop")
		_to_sellers(shop, {"thread": thread, "read": True})
	return len(names)


def _image(file):
	"""Yuklangan rasm: 10 MB gacha, ochiladigan rasm bo'lishi shart. EXIF (joylashuv va b.) olib tashlanadi,
	katta tomoni 1600px gacha kichraytiriladi, JPEG bo'lib saqlanadi."""
	from PIL import Image, ImageOps

	data = file.stream.read(IMAGE_MAX + 1)
	if len(data) > IMAGE_MAX:
		frappe.throw(_("Rasm 10 MB dan katta"))
	try:
		im = Image.open(io.BytesIO(data))
		im.load()
		im = ImageOps.exif_transpose(im)
	except Exception:
		frappe.throw(_("Faqat rasm yuborish mumkin (JPG, PNG, WEBP)"))
	if im.mode in ("RGBA", "LA", "P"):
		im = im.convert("RGBA")
		bg = Image.new("RGB", im.size, "white")
		bg.paste(im, mask=im.split()[-1])
		im = bg
	elif im.mode != "RGB":
		im = im.convert("RGB")
	im.thumbnail((IMAGE_SIDE, IMAGE_SIDE))
	out = io.BytesIO()
	im.save(out, "JPEG", quality=85, optimize=True)
	return out.getvalue()


def _request_file():
	request = getattr(frappe.local, "request", None)  # so'rovsiz (test, navbat) — None
	return request.files.get("rasm") if request is not None and request.files else None


def _send(thread, side, client_id=None, turi="Matn", matn=None, stiker=None, user=None, file=None):
	"""Xabar qo'shadi (client_id bilan avval tushgan bo'lsa — o'sha qaytadi). file — yuklangan rasm (turi «Rasm»)."""
	client_id = (client_id or "")[:64] or None
	if client_id:
		existing = frappe.get_all(XABAR, filters={"murojaat": thread.name, "client_id": client_id}, fields=FIELDS, limit=1)
		if existing:
			return _msg(existing[0], side)
	doc = frappe.new_doc(XABAR)
	doc.update({"murojaat": thread.name, "kimdan": side, "turi": turi, "client_id": client_id,
	            "yozgan": user if side == SOTUVCHI else None})
	content = None
	if turi == "Matn":
		doc.matn = _clean_text(matn)
	elif turi == "Stiker":
		if stiker not in STICKERS:
			frappe.throw(_("Bunday stiker yo‘q"))
		doc.stiker = stiker
	elif turi == "Rasm":
		if not file:
			frappe.throw(_("Rasm tanlanmagan"))
		content = _image(file)
	else:
		frappe.throw(_("Noto‘g‘ri xabar turi"))
	doc.insert(ignore_permissions=True)
	if content:
		f = frappe.get_doc({
			"doctype": "File", "file_name": f"chat-{doc.name}.jpg", "attached_to_doctype": XABAR,
			"attached_to_name": doc.name, "attached_to_field": "rasm", "is_private": 1, "content": content,
		}).insert(ignore_permissions=True)
		doc.db_set("rasm", f.file_url, update_modified=False)
	# Chat qatori (Tovar Murojaat) yangilanmaydi: oxirgi xabar ro'yxatda xabarlarning o'zidan olinadi (last_messages).
	# Aks holda bir chatga bir vaqtda kelgan xabarlar bitta qatorni yangilab, bittasi yiqilardi (MariaDB 1020)
	doc.reload()
	return _msg(doc, side)


def _own_message(name, side, thread_check):
	m = frappe.get_doc(XABAR, name)
	thread_check(m.murojaat)
	if m.kimdan != side or cint(m.ochirilgan):
		frappe.throw(_("Faqat o‘z xabaringizni o‘zgartira olasiz"), frappe.PermissionError)
	if m.turi == "Tovar":
		frappe.throw(_("Tovar kartasini o‘zgartirib yoki o‘chirib bo‘lmaydi"), frappe.PermissionError)
	return m


def last_messages(threads):
	"""Har bir chatning oxirgi (o'chirilmagan) xabari: {chat: {oxirgi_xabar, oxirgi_vaqt, oxirgi_kimdan}} — bitta so'rov."""
	if not threads:
		return {}
	rows = frappe.db.sql(
		"""select x.murojaat, x.turi, x.matn, x.stiker, x.kimdan, x.creation
		from `tabTovar Murojaat Xabar` x
		join (select murojaat, max(creation) as last from `tabTovar Murojaat Xabar`
		      where murojaat in %(t)s and ochirilgan = 0 group by murojaat) l
		  on l.murojaat = x.murojaat and l.last = x.creation
		where x.ochirilgan = 0""",
		{"t": tuple(threads)}, as_dict=True,
	)
	return {r.murojaat: {"oxirgi_xabar": preview(r), "oxirgi_vaqt": r.creation, "oxirgi_kimdan": r.kimdan} for r in rows}


def _with_last(rows):
	"""Ro'yxat qatorlariga oxirgi xabar va vaqt; yangi xabar kelgan chat — tepada."""
	last = last_messages([r.name for r in rows])
	for r in rows:
		r.update(last.get(r.name) or {"oxirgi_xabar": None, "oxirgi_vaqt": r.creation, "oxirgi_kimdan": None})
	rows.sort(key=lambda r: get_datetime(r.oxirgi_vaqt), reverse=True)
	return rows


def _edit(name, side, matn, thread_check):
	m = _own_message(name, side, thread_check)
	if m.turi != "Matn":
		frappe.throw(_("Faqat matnli xabarni tahrirlash mumkin"))
	m.matn = _clean_text(matn)
	m.tahrirlangan = now_datetime()
	m.save(ignore_permissions=True)
	return _msg(m, side)


def _delete(name, side, thread_check):
	"""O'chirish ikkala tomondan: matn va rasm fayli ham o'chadi, qator «o'chirildi» bo'lib qoladi (since uchun)."""
	m = _own_message(name, side, thread_check)
	for f in frappe.get_all("File", filters={"attached_to_doctype": XABAR, "attached_to_name": m.name}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True, force=True)
	m.update({"ochirilgan": 1, "matn": None, "rasm": None, "stiker": None})
	m.save(ignore_permissions=True)
	return _msg(m, side)


# ---------------- Bildirishnomalar ----------------


def _sellers(shop):
	"""Do'kon egasi va sotuv menejerlari (kuryer va upakovkachi emas)."""
	return set(frappe.get_all("Shop Member", filters={"parent": shop, "parenttype": "Shop",
	                                                  "role": ["not in", (*COURIER_MEMBERS, *PACKER_MEMBERS)]}, pluck="user"))


def _to_sellers(shop, data):
	for user in _sellers(shop):
		frappe.publish_realtime("mp_tovar_chat", data, user=user, after_commit=True)


def _notify_customer_message(thread, msg, new_thread, burst):
	"""Mijoz yozdi: panel darhol yangilanadi. Yangi murojaat — qo'ng'iroqcha (Notification Log) va ovoz;
	yangi murojaat yoki menejer hamma xabarni o'qib bo'lgandan keyingi birinchi xabar — Telegram."""
	subject = _("Tovar bo‘yicha murojaat: {0} — {1}").format(thread.mijoz_ismi or thread.telefon, thread.tovar_nomi)
	for user in _sellers(thread.shop):
		if new_thread:
			# link — qo'ng'iroqchadagi yozuv Sotuv panelida shu chatni ochadi (menejerga Tovar Murojaat formasi yopiq)
			frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": TM,
			                "document_name": thread.name, "subject": subject, "link": panel_link(thread.name)}).insert(ignore_permissions=True)
		frappe.publish_realtime("mp_tovar_chat", {"thread": thread.name, "subject": subject, "text": preview(msg),
		                                          "new_thread": new_thread, "alert": new_thread or burst},
		                        user=user, after_commit=True)
	if new_thread or burst:
		frappe.enqueue("marketplace.sotuv.tovar_chat.notify_telegram", queue="short", enqueue_after_commit=True,
		               name=thread.name, text=preview(msg))


def panel_link(name):
	return f"/desk/sotuv/sotuv-paneli?tovar_murojaat={name}"


def notify_telegram(name, text=None):
	"""Navbatdan: menejerlarning Telegram'iga (Shop.murojaat_telegram_ids) — kim, qaysi tovar va «Chatni ochish»."""
	import html

	from marketplace import telegram_bot

	if not telegram_bot.token():
		return
	t = frappe.db.get_value(TM, name, ["shop", "mijoz_ismi", "telefon", "tovar_nomi"], as_dict=True)
	if not t:
		return
	ids = telegram_bot._ids(frappe.db.get_value("Shop", t.shop, "murojaat_telegram_ids"))
	if not ids:
		return
	body = f"💬 <b>{html.escape(t.mijoz_ismi or t.telefon or '')}</b> — {html.escape(t.tovar_nomi or '')}"
	if text:
		body += f"\n{html.escape(text[:300])}"
	url = telegram_bot.site_url() + panel_link(name)
	button = {"inline_keyboard": [[{"text": "💬 Chatni ochish", "url": url}]]}
	for chat_id in dict.fromkeys(ids):
		try:
			telegram_bot.send(chat_id, body, reply_markup=button)
		except telegram_bot.TelegramError as e:
			try:  # lokal manzil tugmaga qabul qilinmaydi — havola matnda
				telegram_bot.send(chat_id, f"{body}\n\n{url}")
			except telegram_bot.TelegramError:
				frappe.log_error(f"Telegram: {chat_id} ga yuborilmadi: {e}", "Tovar murojaat")


# ---------------- Mijoz (sayt) ----------------


def _customer():
	from marketplace.customers import current_customer

	c = current_customer()
	if not c:
		frappe.throw(_("Avval Telegram orqali kiring"), frappe.AuthenticationError)
	return c


def _customer_thread(name, customer):
	t = frappe.db.get_value(TM, name, ["name", "shop", "customer", "tovar", "tovar_nomi", "mijoz_ismi", "telefon"], as_dict=True)
	if not t or t.customer != customer.customer:
		frappe.throw(_("Chat topilmadi"), frappe.DoesNotExistError)
	return t


def _shop_item(shop, tovar):
	"""Mijoz yozayotgan tovar shu do'konniki va saytda chiqqan bo'lishi kerak."""
	from marketplace import storefront

	shop_doc = storefront.get_shop(shop)
	if not frappe.db.exists("Item", {"name": tovar, "shop": shop_doc.name, "is_published": 1, "disabled": 0}):
		frappe.throw(_("Tovar topilmadi"), frappe.DoesNotExistError)
	return shop_doc.name


def find_thread(shop, customer, tovar):
	return frappe.db.get_value(TM, {"shop": shop, "customer": customer, "tovar": tovar})


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=600)
def mijoz_ochish(shop, tovar, since=None, oqidi=1):
	"""Mijozning shu tovar bo'yicha chati: tovar kartasi va xabarlar (hali yozmagan bo'lsa — bo'sh).
	oqidi=1 — sahifa ko'rinib turibdi: sotuvchi xabarlari o'qildi deb belgilanadi."""
	c = _customer()
	shop = _shop_item(shop, tovar)
	name = find_thread(shop, c.customer, tovar)
	if name and cint(oqidi):
		_mark_read(name, MIJOZ)
	messages = _messages(name, MIJOZ, since) if name else []
	return {
		"thread": name,
		"tovar": product_cards(shop, [tovar]).get(tovar),
		"shop_name": frappe.db.get_value("Shop", shop, "shop_name"),
		"messages": messages,
		"since": _cursor(messages, since),
		"stickers": STICKERS,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def mijoz_yuborish(shop, tovar, client_id=None, turi="Matn", matn=None, stiker=None):
	"""Mijoz xabari. Birinchi xabarda murojaat yaratiladi (boshida tovar kartasi) va do'konga xabar boradi."""
	c = _customer()
	shop = _shop_item(shop, tovar)
	name = find_thread(shop, c.customer, tovar)
	new_thread = False
	if not name:
		name, new_thread = _create_thread(shop, c, tovar)
	thread = frappe.db.get_value(TM, name, ["name", "shop", "tovar_nomi", "mijoz_ismi", "telefon"], as_dict=True)
	# Menejer oldingi xabarlarni o'qib bo'lgan bo'lsa — bu yangi savol: Telegram'ga ham
	burst = not new_thread and not frappe.db.exists(XABAR, {"murojaat": name, "kimdan": MIJOZ, "oqilgan": ["is", "not set"],
	                                                        "ochirilgan": 0, "turi": ["!=", "Tovar"]})
	msg = _send(thread, MIJOZ, client_id, turi, matn, stiker, file=_request_file())
	_notify_customer_message(thread, msg, new_thread, burst)
	return {"thread": name, "message": msg}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def mijoz_tahrirlash(xabar, matn):
	c = _customer()
	threads = []
	msg = _edit(xabar, MIJOZ, matn, lambda t: threads.append(_customer_thread(t, c)))
	_to_sellers(threads[0].shop, {"thread": threads[0].name})
	return msg


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def mijoz_ochirish(xabar):
	c = _customer()
	threads = []
	msg = _delete(xabar, MIJOZ, lambda t: threads.append(_customer_thread(t, c)))
	_to_sellers(threads[0].shop, {"thread": threads[0].name})
	return msg


def _create_thread(shop, c, tovar):
	"""Birinchi xabar: chat va boshidagi tovar kartasi. Ikki «birinchi» xabar bir vaqtda kelsa (rasm + matn) ikkita chat
	yaratilmasin: qulf ostida qayta tekshiriladi va chat darhol saqlanadi — keyingi so'rov uni ko'radi.
	Qaytaradi: (nomi, yangi yaratildimi)."""
	from frappe.utils.synchronization import filelock

	commit = not frappe.flags.in_test  # testda tranzaksiya oxirida orqaga qaytariladi
	if commit:
		frappe.db.commit()  # yangi o'qish: parallel so'rov saqlagan chat ko'rinsin
	with filelock("tovar_chat_yangi", timeout=15):
		name = find_thread(shop, c.customer, tovar)
		if name:
			return name, False
		t = frappe.get_doc({
			"doctype": TM, "shop": shop, "tovar": tovar, "customer": c.customer, "mijoz_ismi": c.name, "telefon": c.phone,
			"tovar_nomi": frappe.db.get_value("Item", tovar, "item_name"),
		}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": XABAR, "murojaat": t.name, "kimdan": MIJOZ, "turi": "Tovar"}).insert(ignore_permissions=True)
		if commit:
			frappe.db.commit()
		return t.name, True


def customer_threads(customer, shop):
	"""Profil: mijozning shu do'kondagi chatlari, har birida sotuvchidan o'qilmagan xabarlar soni."""
	rows = _with_last(frappe.get_all(TM, filters={"customer": customer, "shop": shop},
	                                 fields=["name", "tovar", "tovar_nomi", "creation"], limit_page_length=500))[:100]
	unread = _unread_by_thread([r.name for r in rows], SOTUVCHI)
	cards = product_cards(shop, [r.tovar for r in rows])
	for r in rows:
		r.unread = unread.get(r.name, 0)
		r.card = cards.get(r.tovar) or {"name": r.tovar_nomi, "thumb": None}
		r.url = f"/s/{shop}/chat/{r.tovar}"
	return rows


def customer_unread(customer, shop):
	"""Do'kon sarlavhasidagi «Profil» belgisi: sotuvchidan kelgan, mijoz hali o'qimagan xabarlar soni."""
	threads = frappe.get_all(TM, filters={"customer": customer, "shop": shop}, pluck="name")
	return sum(_unread_by_thread(threads, SOTUVCHI).values()) if threads else 0


def _unread_by_thread(threads, kimdan):
	if not threads:
		return {}
	return dict(frappe.get_all(XABAR, filters={"murojaat": ["in", threads], "kimdan": kimdan, "oqilgan": ["is", "not set"],
	                                           "ochirilgan": 0, "turi": ["!=", "Tovar"]},
	                           fields=["murojaat", {"COUNT": "*", "as": "n"}], group_by="murojaat", as_list=True))


# ---------------- Menejer (Desk → Sotuv paneli) ----------------


def _seller_shop():
	from marketplace.sotuv.api import _shop

	return _shop()


def _seller_thread(name):
	shop = _seller_shop()
	t = frappe.db.get_value(TM, name, ["name", "shop", "customer", "tovar", "tovar_nomi", "mijoz_ismi", "telefon"], as_dict=True)
	if not t or t.shop != shop:
		frappe.throw(_("Bu murojaat sizning do‘koningizniki emas"), frappe.PermissionError)
	return t


def seller_new_count(shop):
	"""Rejim almashtirgichida «Tovar murojaatlari · N yangi»: o'qilmagan mijoz xabari bor chatlar."""
	threads = frappe.get_all(TM, filters={"shop": shop}, pluck="name")
	return len(_unread_by_thread(threads, MIJOZ)) if threads else 0


@frappe.whitelist()
def yangi_soni():
	"""Boshqa bo'limda turganda «Tovar murojaatlari» tugmasidagi son (realtime xabar kelganda)."""
	return seller_new_count(_seller_shop())


@frappe.whitelist()
def royxat(q=None):
	from marketplace.sotuv.api import _filters as order_filters
	from marketplace.sotuv.api import _has_must, _shop

	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	or_filters = None
	if (q or "").strip():
		like = f"%{q.strip()}%"
		or_filters = [["mijoz_ismi", "like", like], ["telefon", "like", like], ["tovar_nomi", "like", like], ["name", "like", like]]
	rows = _with_last(frappe.get_all(TM, filters={"shop": shop}, or_filters=or_filters,
	                                 fields=["name", "mijoz_ismi", "telefon", "tovar", "tovar_nomi", "creation"],
	                                 order_by="modified desc", limit_page_length=2000))[:300]
	unread = _unread_by_thread([r.name for r in rows], MIJOZ)
	cards = product_cards(shop, [r.tovar for r in rows])
	for r in rows:
		r.unread = unread.get(r.name, 0)
		r.thumb = (cards.get(r.tovar) or {}).get("thumb")
	return {
		"shop": shop, "shop_name": frappe.db.get_value("Shop", shop, "shop_name"), "rows": rows,
		"yangi": seller_new_count(shop),
		"order_new": frappe.db.count("Sales Order", order_filters("yangi", shop)),
		"lead_new": frappe.db.count("Murojaat", {"shop": shop, "holat": "Yangi"}),
		"must": _has_must(shop),
	}


@frappe.whitelist()
def ochish(name, since=None, oqidi=1):
	t = _seller_thread(name)
	if cint(oqidi):
		_mark_read(name, SOTUVCHI)
	messages = _messages(name, SOTUVCHI, since)
	return {
		"thread": name, "mijoz": t.mijoz_ismi, "telefon": t.telefon,
		"tovar": product_cards(t.shop, [t.tovar]).get(t.tovar) or {"name": t.tovar_nomi},
		"messages": messages, "since": _cursor(messages, since), "stickers": STICKERS,
	}


@frappe.whitelist(methods=["POST"])
def yuborish(name, client_id=None, turi="Matn", matn=None, stiker=None):
	t = _seller_thread(name)
	return {"thread": name, "message": _send(t, SOTUVCHI, client_id, turi, matn, stiker, user=frappe.session.user, file=_request_file())}


@frappe.whitelist(methods=["POST"])
def tahrirlash(xabar, matn):
	return _edit(xabar, SOTUVCHI, matn, _seller_thread)


@frappe.whitelist(methods=["POST"])
def ochirish(xabar):
	return _delete(xabar, SOTUVCHI, _seller_thread)


# ---------------- Rasm (ikkala tomon) ----------------


@frappe.whitelist(allow_guest=True, methods=["GET"])
def rasm(xabar):
	"""Chatdagi rasm: faqat shu chatning mijoziga (sayt sessiyasi) yoki do'kon xodimi / adminga."""
	m = frappe.db.get_value(XABAR, xabar, ["murojaat", "rasm", "ochirilgan"], as_dict=True)
	if not m or not m.rasm or cint(m.ochirilgan):
		raise frappe.DoesNotExistError
	t = frappe.db.get_value(TM, m.murojaat, ["shop", "customer"], as_dict=True)
	if not _can_view(t):
		raise frappe.PermissionError
	f = frappe.get_doc("File", {"file_url": m.rasm})
	frappe.local.response.filename = f.file_name
	# encodings=[] — baytlarning o'zi (aks holda Frappe binar faylni ham bir baytli kodlash bilan matnga aylantiradi)
	frappe.local.response.filecontent = f.get_content(encodings=[])
	frappe.local.response.content_type = "image/jpeg"
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


def _can_view(t):
	from marketplace.customers import current_customer

	c = current_customer()
	if c and c.customer == t.customer:
		return True
	user = frappe.session.user
	if user == "Guest":
		return False
	return is_admin(user) or user in _sellers(t.shop)
