"""Instagram (lead-forma) murojaatlari: reklama formasini to'ldirgan mijoz saytga "Murojaat" bo'lib tushadi,
do'konning sotuv menejeri Sotuv panelidagi "Murojaatlar" bo'limida qo'ng'iroq qiladi va natija yozadi.

Qabul: POST /api/method/marketplace.sotuv.murojaat.qabul?tovar=<tovar kodi>, sarlavha "X-Murojaat-Kalit: <do'kon kaliti>"
* kalit — do'konning "Murojaat API kaliti" (Shop.murojaat_kaliti): murojaat qaysi do'konga tushishini shu belgilaydi.
  Sarlavhada yuboriladi (havolada ?kalit=... ham ishlaydi, lekin havola server logiga tushadi);
* tovar — reklama qaysi kitob (tovar) bo'yicha: har bir tovarning o'z havolasi (tovar formasidagi «SMM havolasi»);
* tana — JSON: {"ism", "familiya", "telefon", "tovar"} (SAMPLE). Faqat telefon majburiy; tovar havolada bo'lsa
  tanada shart emas. Inglizcha nomlar (first_name, last_name, full_name, phone), qo'shimcha shahar/izoh/kampaniya
  va Meta lead-formasi ko'rinishi ({"field_data": [{"name", "values"}]}) ham tushuniladi.
SMM vositasi (Make, Zapier va h.k.) formani shu manzilga yuboradi. Bir xil lead qayta kelsa — yangisi yaratilmaydi.
Google Sheets: Meta Instant Form'ni jadvalga o'zi yozadi, jadvaldagi Apps Script (sotuv/google_sheets.gs, do'kon formasidagi
«Google Sheets» oynasi — sheets_setup) har daqiqada yangi qatorlarni shu yerga yuboradi. Tovar tovar_id ustunidan, bo'lmasa
varaq/forma nomidagi «Tovar ID»dan (Item.mp_tovar_id: 1, 2, 3…) yoki tovar nomidan aniqlanadi (_hint_item).
Javobda nima yozilgani qaytadi (ism, familiya, telefon, tovar) — SMM'chi tovar to'g'ri ulanganini shundan ko'radi.

Qo'ng'iroq yozuvi murojaatga RAQAM bo'yicha bog'lanadi (telefoniya.ingest_call), mijoz keyin saytda buyurtma bersa —
murojaat "Buyurtma berdi" bo'ladi.
"""

import json
import re
import secrets
from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, cint, flt, get_url, getdate, now_datetime, today

from marketplace.sotuv.telefoniya import normalize_phone, pretty_phone

RESULTS = ("Oladi", "Olmaydi", "Javob bermadi", "Keyinroq")
CHANNELS = ("Qo‘ng‘iroq", "SMS")
# Formadagi maydon nomlari har xil bo'ladi (Meta, Make, Zapier, o'zbekcha) — birinchi to'ldirilgani olinadi
KEYS = {
	"ism": ("ism", "first_name", "firstname", "name_first", "имя"),
	"familiya": ("familiya", "last_name", "lastname", "surname", "фамилия"),
	"to'liq": ("full_name", "fullname", "name", "ism_familiya", "fio", "фио"),
	"telefon": ("telefon", "phone", "phone_number", "phonenumber", "tel", "mobile", "номер_телефона", "телефон"),
	"izoh": ("izoh", "comment", "comments", "message", "note", "savol", "комментарий"),
	"shahar": ("shahar", "city", "viloyat", "region", "tuman", "город", "manzil"),
	"tovar": ("tovar", "tovar_id", "kitob", "product", "product_id", "book", "item", "item_code"),
	"kampaniya": ("kampaniya", "campaign", "campaign_name", "utm_campaign", "ad_name", "adset_name"),
	"forma": ("forma", "form", "form_name", "form_id"),
	"manba": ("manba", "source", "platform"),
	"lead_id": ("lead_id", "leadgen_id", "id"),
}
SOURCES = {"instagram": "Instagram", "ig": "Instagram", "facebook": "Facebook", "fb": "Facebook", "telegram": "Telegram", "sayt": "Sayt", "site": "Sayt"}
# SMM'chiga ko'rsatiladigan namuna (GET tekshiruv javobi; tovar formasidagi «SMM havolasi» oynasida ham shu)
SAMPLE = {"ism": "Ali", "familiya": "Valiyev", "telefon": "+998901234567"}


# ---------------- Do'kon kaliti ----------------


def ensure_key(shop):
	"""Do'konga murojaat kaliti (yo'q bo'lsa — yaratiladi). Shop.after_insert va bir martalik patch chaqiradi."""
	key = frappe.db.get_value("Shop", shop, "murojaat_kaliti")
	if not key:
		key = secrets.token_urlsafe(18)
		frappe.db.set_value("Shop", shop, "murojaat_kaliti", key, update_modified=False)
	return key


def _shop_by_key(key):
	key = (key or "").strip()
	return key and len(key) >= 16 and frappe.db.get_value("Shop", {"murojaat_kaliti": key}, "name")


@frappe.whitelist()
def smm_link(item: str | None = None, shop: str | None = None):
	"""Do'kon egasi / admin uchun: Make (Instagram lead-formasi) sozlamalari — manzil (tovar bo'yicha) va kalit.
	Kalit havolada emas, X-Murojaat-Kalit sarlavhasida yuboriladi: nginx sarlavhalarni logga yozmaydi, havolani esa yozadi.
	Sotuv menejeri va kuryerga — yo'q."""
	shop, item = _smm_scope(item, shop)
	url = f"{get_url()}/api/method/marketplace.sotuv.murojaat.qabul"
	if item:
		url += f"?tovar={quote(item)}"
	return {"url": url, "header": "X-Murojaat-Kalit", "kalit": ensure_key(shop), "shop": shop, "item": item,
	        "item_name": item and frappe.db.get_value("Item", item, "item_name")}


@frappe.whitelist(methods=["POST"])
def reset_smm_key(item: str | None = None, shop: str | None = None):
	"""Kalit begona qo'lga o'tgan bo'lsa: yangisi yaratiladi, eskisi darhol ishlamay qoladi (Make'dagi sarlavhani yangilash kerak)."""
	shop, item = _smm_scope(item, shop)
	frappe.db.set_value("Shop", shop, "murojaat_kaliti", secrets.token_urlsafe(18), update_modified=False)
	return smm_link(item=item, shop=shop)


def _smm_scope(item, shop):
	from marketplace.permissions import get_user_shop, is_admin

	if item:
		shop = frappe.db.get_value("Item", item, "shop")
		item = frappe.db.get_value("Item", item, "variant_of") or item
	own = get_user_shop()
	allowed = is_admin() or (own == shop and "Shop Seller" in frappe.get_roles())
	if not shop or not allowed:
		frappe.throw(_("SMM havolasini faqat do'kon egasi yoki admin ko'radi"), frappe.PermissionError)
	return shop, item


# ---------------- Qabul (reklama formasi) ----------------


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def qabul(**kwargs):
	"""Lead-formadan bitta murojaat (POST). Qaytaradi: {"status": "ok", "name", "duplicate", "ism", "familiya",
	"telefon", "tovar", "tovar_nomi"} (+ "ogohlantirish", agar yuborilgan tovar do'konda topilmasa).
	Kalit noto'g'ri bo'lsa — 403, telefon yo'q bo'lsa — 417 (SMM vositasi xatoni ko'radi va qayta yubormaydi).
	GET — faqat tekshirish: havolani brauzerda ochsa, qaysi do'kon va qaysi tovarga ulangani ko'rinadi."""
	data = _payload()
	# JSON tanali so'rovda Frappe havoladagi ?kalit=...&tovar=... ni form_dict'ga qo'shmaydi — _payload ularni o'zi oladi
	# "X-Murojaat-Kaliti" — SMM vositalari ko'p shunday yozadi (Make AI ham), xato deb tashlamaymiz
	shop = _shop_by_key(
		data.pop("kalit", None)
		or frappe.get_request_header("X-Murojaat-Kalit")
		or frappe.get_request_header("X-Murojaat-Kaliti")
	)
	if not shop:
		raise frappe.PermissionError(_("Murojaat kaliti noto'g'ri"))
	if frappe.request and frappe.request.method == "GET":
		return _link_check(shop, _pick(data, "tovar"))
	asked = _pick(data, "tovar") or _hint_item(shop, data)
	name, duplicate = save_lead(shop, data, asked)
	return _answer(name, duplicate, asked)


def save_lead(shop, data, asked=None):
	"""Bitta murojaat: data — tekis lug'at (kalitlar kichik harfda, KEYS bo'yicha o'qiladi), asked — tovar kodi yoki nomi.
	SMM havolasi (qabul) va Meta lead webhook'i (sotuv/meta.py) shu yerdan yozadi. Qaytaradi: (nomi, dublikatmi)."""
	# Meta jadvalga/CSV'ga "p:+998901234567" va "l:1234567890" ko'rinishida yozadi
	phone = re.sub(r"^p:\s*", "", _pick(data, "telefon"))
	normal = normalize_phone(phone)
	if not normal or len(normal) < 9:
		frappe.throw(_("Telefon raqami yo'q yoki noto'g'ri"))

	lead_id = re.sub(r"^l:", "", _pick(data, "lead_id"))[:140]
	tovar, tovar_nomi = _item(shop, asked)
	# Qayta yuborilgan lead (SMM vositasi takrorlasa) yoki 10 daqiqa ichida aynan o'sha mijoz + tovar — dublikat
	dup = (lead_id and frappe.db.get_value("Murojaat", {"shop": shop, "tashqi_id": lead_id})) or frappe.db.get_value(
		"Murojaat",
		{"shop": shop, "normal_telefon": normal, "tovar": tovar or ["is", "not set"],
		 "creation": [">", add_to_date(now_datetime(), minutes=-10)]},
	)
	if dup:
		return dup, True

	ism, familiya = _pick(data, "ism"), _pick(data, "familiya")
	full = _pick(data, "to'liq")
	if full and not (ism or familiya):
		ism, _sep, familiya = full.partition(" ")
	source = SOURCES.get(_pick(data, "manba").lower(), "Instagram")
	doc = frappe.get_doc(
		{
			"doctype": "Murojaat",
			"shop": shop,
			"ism": ism[:140] or None,
			"familiya": familiya.strip()[:140] or None,
			"mijoz_ismi": (" ".join(x for x in (ism, familiya.strip()) if x) or full or pretty_phone(phone))[:140],
			"telefon": pretty_phone(phone)[:40],
			"normal_telefon": normal,
			"izoh": _pick(data, "izoh")[:2000] or None,
			"shahar": _pick(data, "shahar")[:140] or None,
			"tovar": tovar,
			"tovar_nomi": tovar_nomi,
			"manba": source,
			"kampaniya": _pick(data, "kampaniya")[:140] or None,
			"forma": _pick(data, "forma")[:140] or None,
			"tashqi_id": lead_id or None,
			"holat": "Yangi",
			"xom": json.dumps(data, ensure_ascii=False, default=str)[:5000],
		}
	)
	doc.insert(ignore_permissions=True)
	_notify(doc)
	return doc.name, False


def _answer(name, duplicate, asked):
	"""SMM vositasiga javob: murojaat qanday yozilgani — ism, familiya, telefon va qaysi tovar bo'yicha."""
	row = frappe.db.get_value("Murojaat", name, ["ism", "familiya", "telefon", "tovar", "tovar_nomi"], as_dict=True)
	out = {"status": "ok", "name": name, "duplicate": duplicate, **row}
	if asked and not row.tovar:
		out["ogohlantirish"] = _("«{0}» tovari bu do'konda topilmadi — murojaat tovarsiz yozildi").format(asked)
	return out


def _link_check(shop, value):
	tovar, tovar_nomi = _item(shop, value)
	if value and not tovar:
		xabar = _("Diqqat: «{0}» tovari bu do'konda topilmadi — murojaatlar tovarsiz yoziladi").format(value)
	else:
		xabar = _("Havola ishlayapti. Murojaatni POST bilan yuboring: ism, familiya, telefon (namuna pastda)")
	return {
		"status": "ok", "dokon": frappe.db.get_value("Shop", shop, "shop_name"), "tovar": tovar, "tovar_nomi": tovar_nomi,
		"xabar": xabar, "namuna": {**SAMPLE, **({"tovar": tovar} if tovar else {})},
	}


def _payload():
	"""Havoladagi parametrlar (kalit, tovar) + JSON tana yoki form maydonlari; Meta'ning field_data ro'yxati
	tekis lug'atga aylantiriladi."""
	data = {}
	request = getattr(frappe.local, "request", None)
	if request is not None:
		data.update(request.args.to_dict())
		try:
			body = request.get_json(silent=True)
		except Exception:
			body = None
		if isinstance(body, dict):
			data.update(body)
	data.update({k: v for k, v in frappe.form_dict.items() if k != "cmd"})
	for row in data.pop("field_data", None) or []:
		if isinstance(row, dict) and row.get("name"):
			values = row.get("values") or []
			data.setdefault(str(row["name"]), values[0] if values else "")
	return {str(k).strip().lower().replace(" ", "_"): v for k, v in data.items()}


# Meta formasidagi o'z savollari kalit bo'lib keladi: "telefon_raqamingiz", "qaysi_shahardansiz?", "savolingiz_bormi?"
STEMS = {
	"telefon": ("phone", "telefon", "raqam", "номер", "телефон"),
	"shahar": ("shahar", "city", "viloyat", "hudud", "город"),
	"izoh": ("izoh", "savol", "comment", "вопрос", "коммент"),
	"to'liq": ("ism", "имя", "фио"),
}
KNOWN = {key for keys in KEYS.values() for key in keys}


def _pick(data, field):
	for key in KEYS[field]:
		value = data.get(key)
		if value not in (None, ""):
			return str(value).strip()
	for key, value in data.items():
		if key not in KNOWN and value not in (None, "") and any(stem in key for stem in STEMS.get(field, ())):
			return str(value).strip()
	return ""


# «1», «#1», «1 Audio kitob», «1-kitob» — boshidagi raqam Tovar ID (Item.mp_tovar_id)
TOVAR_ID = re.compile(r"#?\s*(\d{1,6})(?!\w)")


def _item(shop, value):
	"""Tovar kodi, Tovar ID yoki nomi (shu do'kon ichida). Topilmasa — (None, kelgan matn)."""
	if not value:
		return None, None
	value = str(value).strip()
	fields = ["name", "item_name", "variant_of"]
	row = frappe.db.get_value("Item", {"name": value, "shop": shop}, fields, as_dict=True) or frappe.db.get_value(
		"Item", {"item_name": value, "shop": shop, "variant_of": ["is", "not set"]}, fields, as_dict=True
	)
	# To'liq nom birinchi: «2 kishilik divan» degan tovar 2-ID'li tovarga tushib qolmasin
	number = not row and TOVAR_ID.match(value)
	if number and int(number.group(1)) > 0:
		row = frappe.db.get_value(
			"Item", {"shop": shop, "mp_tovar_id": int(number.group(1)), "variant_of": ["is", "not set"]}, fields, as_dict=True
		)
	if not row:
		return None, value[:140]
	if row.variant_of:
		return row.variant_of, frappe.db.get_value("Item", row.variant_of, "item_name")
	return row.name, row.item_name


def _hint_item(shop, data):
	"""Tovar alohida yuborilmasa: Google Sheets varag'i yoki forma nomidagi Tovar ID / tovar nomi («1 Audio kitob»),
	keyin reklama va kampaniya nomidagi tovar nomi. Topilsa — tovar kodi."""
	from marketplace.sotuv.meta import _guess_item

	hints = [(data.get("varaq"), True), (data.get("form_name") or data.get("forma"), True)]
	hints += [(data.get(key), False) for key in ("ad_name", "adset_name", "campaign_name", "kampaniya")]
	for text, exact in hints:
		text = str(text or "").strip()
		if not text:
			continue
		code = (exact and _item(shop, text)[0]) or _guess_item(shop, text)
		if code:
			return code
	return None


# ---------------- Tovar ID (reklama) ----------------


def item_tovar_id(doc, method=None):
	"""Item.validate: Tovar ID — do'kon ichida takrorlanmaydigan qisqa raqam (variantda yo'q). Bo'sh bo'lsa — keyingisi."""
	if not frappe.get_meta("Item").has_field("mp_tovar_id"):
		return
	if doc.variant_of or not doc.shop:
		doc.mp_tovar_id = 0
		return
	if cint(doc.mp_tovar_id) < 1:
		doc.mp_tovar_id = _next_tovar_id(doc.shop)
		return
	busy = frappe.db.get_value(
		"Item",
		{"shop": doc.shop, "mp_tovar_id": doc.mp_tovar_id, "name": ["!=", doc.name], "variant_of": ["is", "not set"]},
		"item_name",
	)
	if busy:
		frappe.throw(
			_("Tovar ID {0} band: «{1}». Boshqa raqam qo'ying yoki bo'sh qoldiring — o'zi beriladi").format(doc.mp_tovar_id, busy)
		)


def _next_tovar_id(shop):
	return cint(frappe.db.sql("select max(mp_tovar_id) from `tabItem` where shop = %s", shop)[0][0]) + 1


def fill_tovar_ids():
	"""after_migrate: Tovar ID'si yo'q tovarlarga (eski tovarlar) — qo'shilgan tartibida keyingi raqam."""
	for shop in frappe.get_all("Shop", pluck="name"):
		rows = frappe.db.sql(
			"""select name, ifnull(mp_tovar_id, 0) from `tabItem`
			where shop = %s and ifnull(variant_of, '') = '' order by creation, name""",
			shop,
		)
		last = max((cint(tid) for _name, tid in rows), default=0)
		for name, tid in rows:
			if cint(tid) < 1:
				last += 1
				frappe.db.set_value("Item", name, "mp_tovar_id", last, update_modified=False)


@frappe.whitelist()
def sheets_setup(shop: str):
	"""Do'kon egasi / admin: Google Sheets uchun Apps Script (do'kon kaliti bilan) va Tovar ID ro'yxati."""
	shop, _item_code = _smm_scope(None, shop)
	script = frappe.read_file(frappe.get_app_path("marketplace", "sotuv", "google_sheets.gs"))
	for key, value in {
		"__DOKON__": frappe.db.get_value("Shop", shop, "shop_name") or shop,
		"__MANZIL__": json.dumps(f"{get_url()}/api/method/marketplace.sotuv.murojaat.qabul"),
		"__KALIT__": json.dumps(ensure_key(shop)),
	}.items():
		script = script.replace(key, value)
	items = frappe.get_all(
		"Item",
		filters={"shop": shop, "variant_of": ["is", "not set"], "disabled": 0},
		fields=["mp_tovar_id as id", "item_name as name", "is_published as published", "mp_tez_kunda as soon"],
		order_by="mp_tovar_id asc",
	)
	# Google faqat ochiq HTTPS manzilga yuboradi — lokal nusxada ogohlantiramiz
	return {"script": script, "items": items, "local": not get_url().startswith("https://")}


def _notify(doc):
	"""Yangi murojaat — faqat saytda (Telegram'ga emas): do'kon egasi va sotuv menejerlariga Desk qo'ng'iroqchasi
	va ochiq oynada ovozli xabar. Murojaatning o'zi Sotuv panelidagi "Murojaatlar" bo'limida."""
	subject = _("Yangi murojaat ({0}): {1}, {2}").format(doc.manba, doc.mijoz_ismi, doc.telefon) + (
		f" — {doc.tovar_nomi}" if doc.tovar_nomi else ""
	)
	users = set(
		frappe.get_all("Shop Member", filters={"parent": doc.shop, "parenttype": "Shop", "role": ["!=", "Kuryer"]}, pluck="user")
	)
	for user in users:
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Murojaat",
			 "document_name": doc.name, "subject": subject}
		).insert(ignore_permissions=True)
		frappe.publish_realtime("marketplace_new_order", {"name": doc.name, "subject": subject}, user=user, after_commit=True)


# ---------------- Sotuv paneli: Murojaatlar ----------------


# "Hammasi" yonidagi natija bo'yicha filtrlar: menejer yozgan holat
STATUS_VIEWS = {"oladi": "Oladi", "keyinroq": "Keyinroq", "javob_bermadi": "Javob bermadi", "olmaydi": "Olmaydi",
                "buyurtma_berdi": "Buyurtma berdi"}


def _filters(view, shop):
	base = {"shop": shop}
	if view in STATUS_VIEWS:
		return {**base, "holat": STATUS_VIEWS[view]}
	if view == "yangi":
		return {**base, "holat": "Yangi"}
	if view == "bugun":
		return {**base, "keyingi_qongiroq": ["between", ["2000-01-01", today()]], "holat": ["not in", ["Olmaydi", "Buyurtma berdi"]]}
	if view == "jarayonda":
		return {**base, "holat": ["in", ["Oladi", "Javob bermadi", "Keyinroq"]]}
	return base


@frappe.whitelist()
def get_leads(view: str = "yangi", q: str | None = None, dan: str | None = None, gacha: str | None = None):
	"""Murojaatlar ro'yxati. dan / gacha — kelgan sanasi bo'yicha oraliq (ixtiyoriy, ikkalasi ham bo'lmasa — hammasi)."""
	from marketplace.sotuv.api import _has_must, _shop

	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	_sync_orders(shop)
	filters = _filters(view, shop)
	if dan or gacha:
		filters["creation"] = ["between", [f"{getdate(dan) if dan else '2000-01-01'} 00:00:00", f"{getdate(gacha) if gacha else today()} 23:59:59"]]
	or_filters = None
	if (q or "").strip():
		like = f"%{q.strip()}%"
		digits = normalize_phone(q) or ""
		or_filters = [["mijoz_ismi", "like", like], ["tovar_nomi", "like", like], ["tovar", "like", like], ["kampaniya", "like", like],
		              ["shahar", "like", like], ["name", "like", like]]
		if len(digits) >= 4:
			or_filters.append(["normal_telefon", "like", f"%{digits[-9:]}%"])
	rows = frappe.get_all(
		"Murojaat", filters=filters, or_filters=or_filters,
		fields=["name", "mijoz_ismi", "telefon", "normal_telefon", "izoh", "shahar", "tovar", "tovar_nomi", "manba", "kampaniya", "holat",
		        "keyingi_qongiroq", "aloqa_vaqt", "creation", "buyurtma"],
		order_by="creation desc", limit_page_length=500,
	)
	# Reklama uchun qisqa Tovar ID (SMM shu raqam bilan ishlaydi) — kartada kod o'rniga shu ko'rinadi
	codes = list({r.tovar for r in rows if r.tovar})
	tids = dict(frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "mp_tovar_id"], as_list=True)) if codes else {}
	for r in rows:
		r.tid = tids.get(r.tovar) or None
	calls = {}
	phones = list({r.normal_telefon for r in rows if r.normal_telefon})
	if phones:
		for c in frappe.get_all(
			"Telefon Qongiroq", filters={"shop": shop, "normal_telefon": ["in", phones]},
			fields=["normal_telefon", {"COUNT": "*", "as": "n"}], group_by="normal_telefon",
		):
			calls[c.normal_telefon] = c.n
	for r in rows:
		r.calls = calls.get(r.normal_telefon, 0)
	counts = {v: frappe.db.count("Murojaat", _filters(v, shop)) for v in ("yangi", "bugun", "jarayonda", "hammasi")}
	by_status = dict(frappe.get_all("Murojaat", filters={"shop": shop}, fields=["holat", {"COUNT": "*", "as": "n"}],
	                                group_by="holat", as_list=True))
	counts.update({v: by_status.get(holat, 0) for v, holat in STATUS_VIEWS.items()})
	# Rejim almashtirgichida "Buyurtmalar · N yangi" (murojaatlar rejimida ham ko'rinib tursin)
	from marketplace.sotuv.api import _filters as _order_filters

	return {"shop": shop, "shop_name": frappe.db.get_value("Shop", shop, "shop_name"), "rows": rows, "counts": counts,
	        "order_new": frappe.db.count("Sales Order", _order_filters("yangi", shop)), "must": _has_must(shop)}


def _sync_orders(shop):
	"""Murojaatdan keyin saytda buyurtma bergan mijozlar — "Buyurtma berdi" (raqam bo'yicha, shu do'konda)."""
	open_leads = frappe.get_all(
		"Murojaat", filters={"shop": shop, "holat": ["not in", ["Buyurtma berdi"]], "normal_telefon": ["is", "set"]},
		fields=["name", "normal_telefon", "creation"], limit_page_length=1000,
	)
	if not open_leads:
		return
	phones = {"+" + r.normal_telefon for r in open_leads}
	orders = frappe.get_all(
		"Sales Order", filters={"shop": shop, "docstatus": 1, "mp_placed": 1, "customer_phone": ["in", list(phones)]},
		fields=["name", "customer_phone", "creation"], order_by="creation asc",
	)
	for lead in open_leads:
		so = next((o for o in orders if o.customer_phone == "+" + lead.normal_telefon and o.creation >= lead.creation), None)
		if so:
			frappe.db.set_value("Murojaat", lead.name, {"holat": "Buyurtma berdi", "buyurtma": so.name}, update_modified=False)


def _lead(name, shop):
	doc = frappe.get_doc("Murojaat", name)
	if doc.shop != shop:
		frappe.throw(_("Bu murojaat sizning do'koningizniki emas"), frappe.PermissionError)
	# Patchgacha qo'lda yaratilgan murojaatda normal_telefon bo'sh bo'lishi mumkin — ochilganda to'ldiriladi
	# (majburiy tovar tarixi, buyurtma yaratish va saytdagi buyurtmani ulash shu raqam bo'yicha)
	if not doc.normal_telefon and doc.telefon:
		from marketplace.sotuv.doctype.murojaat.murojaat import lead_phone

		normal = lead_phone(doc.telefon)
		if normal:
			doc.db_set("normal_telefon", normal, update_modified=False)
	return doc


@frappe.whitelist()
def get_lead(name: str):
	"""Murojaat kartasi: mijoz, qaysi tovar (rasm, narx, saytdagi havola), qo'ng'iroqlar (audio), natijalar,
	shu raqamdan saytdagi buyurtmalar."""
	from marketplace.sotuv.api import _shop, mandatory_info
	from marketplace.storefront import _get_prices

	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	doc = _lead(name, shop)
	item = None
	if doc.tovar:
		row = frappe.db.get_value("Item", doc.tovar, ["name", "item_name", "image", "mp_tovar_id as tid"], as_dict=True) or {}
		item = {**row, "price": _get_prices([doc.tovar]).get(doc.tovar), "url": f"{get_url()}/s/{shop}/p/{doc.tovar}"}
	calls = frappe.get_all(
		"Telefon Qongiroq", filters={"shop": shop},
		or_filters=[["murojaat", "=", doc.name]] + ([["normal_telefon", "=", doc.normal_telefon]] if doc.normal_telefon else []),
		fields=["name", "boshlandi", "yonalish", "davomiyligi", "yozuv", "menejer", "holat", "ai_xulosa", "transkript"],
		order_by="boshlandi desc", limit_page_length=50,
	)
	logs = frappe.get_all(
		"Aloqa Yozuvi", filters={"shop": shop},
		or_filters=[["murojaat", "=", doc.name]] + ([["telefon", "=", doc.telefon]] if doc.telefon else []),
		fields=["name", "creation", "buyurtma", "murojaat", "kanal", "natija", "izoh", "keyingi_qongiroq", "menejer"],
		order_by="creation desc", limit_page_length=100,
	)
	orders = frappe.get_all(
		"Sales Order", filters={"shop": shop, "docstatus": ["in", [1, 2]], "customer_phone": "+" + (doc.normal_telefon or "")},
		fields=["name", "grand_total", "payment_status", "creation", "mp_placed", "docstatus"], order_by="creation desc", limit_page_length=20,
	)
	users = {u for u in [c.menejer for c in calls] + [lg.menejer for lg in logs] if u}
	names = {u: frappe.utils.get_fullname(u) for u in users}
	for c in calls:
		c.menejer_ismi = names.get(c.menejer) or c.menejer
	for lg in logs:
		lg.menejer_ismi = names.get(lg.menejer) or lg.menejer
	return {
		"name": doc.name, "mijoz_ismi": doc.mijoz_ismi, "telefon": doc.telefon, "izoh": doc.izoh, "shahar": doc.shahar, "manba": doc.manba,
		"kampaniya": doc.kampaniya, "forma": doc.forma, "holat": doc.holat, "created": str(doc.creation),
		"keyingi_qongiroq": str(doc.keyingi_qongiroq or ""), "tovar_nomi": doc.tovar_nomi, "item": item,
		"calls": calls, "logs": logs, "orders": orders,
		"mandatory": mandatory_info(shop, "+" + doc.normal_telefon if doc.normal_telefon else None),
		# «Oladi» bosilsa — shu yerdan buyurtma (tovar, variant, soni, manzil): save_lead_result(buyurtma=...).
		# Murojaatdan buyurtma allaqachon bo'lsa va u hali topshirilmagan bo'lsa — yangi tovar o'sha buyurtmaga qo'shiladi
		"order_form": {"item": _order_item(shop, doc.tovar) if doc.tovar else None, "address": doc.shahar or "",
		               "pickup": cint(frappe.db.get_value("Shop", shop, "enable_pickup")), "existing": doc.buyurtma,
		               "existing_open": _open_order(doc.buyurtma), "must": _must_items(shop, doc.normal_telefon)},
	}


def _open_order(name):
	"""Buyurtma hali ochiqmi (tasdiqlangan, bekor emas, topshirilmagan, onlayn to'lanmagan) — tovar qo'shsa bo'ladi."""
	if not name:
		return False
	so = frappe.db.get_value("Sales Order", name, ["docstatus", "payment_status", "payment_method", "per_delivered"], as_dict=True)
	return bool(so and so.docstatus == 1 and so.payment_status != "Bekor" and flt(so.per_delivered) < 100
	            and not (so.payment_status == "To'langan" and so.payment_method != "Naqd"))


@frappe.whitelist(methods=["POST"])
def save_lead_result(name: str, kanal: str, natija: str, izoh: str | None = None, keyingi_qongiroq: str | None = None,
                     buyurtma: str | dict | None = None):
	"""Menejer natijasi murojaat bo'yicha: Aloqa Yozuvi + murojaat holati va qayta qo'ng'iroq sanasi.
	«Oladi» + buyurtma ({"item", "qty", "yetkazish", "manzil"}) — menejer mijoz bilan kelishgan buyurtma darhol
	yaratiladi: naqd (yetkazganda), tasdiqlangan — kuryer ko'radi; murojaat «Buyurtma berdi»."""
	from marketplace.sotuv.api import _shop

	shop = _shop()
	doc = _lead(name, shop)
	if kanal not in CHANNELS or natija not in RESULTS:
		frappe.throw(_("Kanal va natijani tanlang"))
	date = getdate(keyingi_qongiroq) if keyingi_qongiroq else None
	if date and date < getdate(today()):
		frappe.throw(_("Qayta qo'ng'iroq sanasi o'tib ketgan kun bo'lmasin"))
	data = frappe.parse_json(buyurtma) if buyurtma else None
	order = None
	if natija == "Oladi" and data:
		if data.get("add_to"):
			# Murojaatdan buyurtma bor — mijoz rozi bo'lgan tovarlar o'sha buyurtmaning o'ziga qo'shiladi (alohida emas)
			from marketplace.orders import add_lines

			if data["add_to"] != doc.buyurtma or not _open_order(doc.buyurtma):
				frappe.throw(_("Bu murojaatning ochiq buyurtmasi yo'q — yangi buyurtma yarating"))
			order = frappe.get_doc("Sales Order", doc.buyurtma)
			if order.shop != shop:
				frappe.throw(_("Bu buyurtma sizning do'koningizniki emas"), frappe.PermissionError)
			lines = [{"code": (l.get("item") or "").strip(), "qty": cint(l.get("qty")) or 1} for l in (data.get("lines") or []) if l.get("item")]
			if lines:
				add_lines(order, lines)
				order.reload()
		else:
			order = _make_order(doc, shop, data, kanal)
	log = frappe.get_doc(
		{
			"doctype": "Aloqa Yozuvi", "murojaat": doc.name, "mijoz_ismi": doc.mijoz_ismi, "telefon": doc.telefon,
			"shop": shop, "kanal": kanal, "natija": natija, "izoh": (izoh or "").strip() or None,
			"keyingi_qongiroq": date, "menejer": frappe.session.user, "buyurtma": order and order.name,
		}
	)
	log.insert(ignore_permissions=True)
	doc.db_set(
		{"holat": "Buyurtma berdi" if order or doc.holat == "Buyurtma berdi" else natija, "keyingi_qongiroq": date,
		 "menejer": frappe.session.user, "aloqa_vaqt": now_datetime(), "buyurtma": order.name if order else doc.buyurtma},
		update_modified=False,
	)
	return {"name": log.name, "order": order and order.name, "total": order and order.grand_total}


# ---------------- Murojaatdan buyurtma ----------------

ORDER_SOURCE = {"Instagram": "Instagram", "Facebook": "Instagram", "Telegram": "Telegram"}


@frappe.whitelist()
def item_search(q: str | None = None):
	"""Murojaatdan buyurtma: mijoz boshqa tovarni so'rasa — do'kon tovarlari (andozalar) nomi yoki kodi bo'yicha."""
	from marketplace.sotuv.api import _shop

	shop = _shop()
	like = f"%{(q or '').strip()}%"
	return frappe.get_all(
		"Item", filters={"shop": shop, "disabled": 0, "variant_of": ["is", "not set"]},
		or_filters=[["item_name", "like", like], ["name", "like", like]],
		fields=["name", "item_name", "image"], order_by="item_name asc", limit_page_length=20,
	)


@frappe.whitelist()
def order_item(item: str):
	from marketplace.sotuv.api import _shop

	return _order_item(_shop(), item)


def _order_item(shop, code):
	"""Tovar va uning sotiladigan variantlari (rang · o'lcham): qoldiq va narx bilan."""
	from marketplace import storefront

	row = frappe.db.get_value(
		"Item", {"name": code, "shop": shop, "disabled": 0},
		["name", "item_name", "image", "has_variants", "variant_of", "is_published", "is_stock_item", "mp_tez_kunda"], as_dict=True,
	)
	if row and row.variant_of:
		return _order_item(shop, row.variant_of)
	if not row:
		return None
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	codes = frappe.get_all("Item", filters={"variant_of": row.name, "disabled": 0}, pluck="name", order_by="creation asc") \
		if row.has_variants else [row.name]
	stock = storefront._get_stock(codes, warehouse) if codes else {}
	prices = storefront._get_prices(codes) if codes else {}
	labels = storefront.variant_labels(codes) if row.has_variants else {}
	return {
		"code": row.name, "name": row.item_name, "image": row.image, "has_variants": cint(row.has_variants),
		"published": cint(row.is_published), "soon": cint(row.mp_tez_kunda),
		"options": [
			{"code": c, "label": labels.get(c) or "", "price": prices.get(c),
			 "qty": max(cint(stock.get(c, 0)), 0) if (row.is_stock_item or row.has_variants) else None}
			for c in codes
		],
	}


def _must_items(shop, normal_phone, codes=()):
	"""Mijoz hali olmagan majburiy tovarlar (variantlari bilan) — murojaatdan buyurtmaga o'zi qo'shiladi."""
	from marketplace import orders, storefront

	if not normal_phone or not frappe.db.get_value("Shop", {"name": shop, "status": "Active"}):
		return []
	need = orders.mandatory_status(storefront.get_shop(shop), frappe._dict(phone="+" + normal_phone), list(codes))
	return [x for x in (_order_item(shop, i["code"]) for i in need.get("items") or []) if x]


def _make_order(lead, shop_name, data, kanal):
	"""Sotuv menejeri mijoz bilan kelishgan buyurtma: narx va qoldiq — serverdan (orders.place_order), to'lov — naqd
	(yetkazganda), menejer tasdiqlagan (mp_aloqa_natija = Oladi) — kuryer darhol ko'radi va xabar oladi."""
	from marketplace import customers, orders, storefront
	from marketplace.seller_desk import notify_couriers

	data = frappe._dict(data or {})
	method = data.yetkazish or "Kuryer"
	# Bir nechta tovar: lines = [{"item", "qty"}, ...] (menejer mijozga taklif qilib qo'shganlari ham); eski shakl — item + qty
	raw_lines = data.lines if isinstance(data.lines, list) and data.lines else ([{"item": data.item, "qty": data.qty}] if data.item else [])
	lines = []
	for raw in raw_lines:
		raw = frappe._dict(raw or {})
		code, qty = (raw.item or "").strip(), cint(raw.qty) or 1
		info = _order_item(shop_name, code) if code else None
		if not info:
			frappe.throw(_("Buyurtma uchun tovarni tanlang"))
		if info["soon"]:
			frappe.throw(_("«{0}» — «Tez kunda»: hali sotuvda yo'q").format(info["name"]))
		if not info["published"]:
			frappe.throw(_("«{0}» saytda yopiq — avval tovarni saytga chiqaring").format(info["name"]))
		if info["has_variants"] and code == info["code"]:
			frappe.throw(_("«{0}»: rang / o'lchamni tanlang").format(info["name"]))
		if not 1 <= qty <= 99:
			frappe.throw(_("Soni 1 dan 99 gacha bo'lsin"))
		same = next((ln for ln in lines if ln["code"] == code), None)
		if same:
			same["qty"] = min(99, same["qty"] + qty)
		else:
			lines.append({"code": code, "qty": qty})
	if not lines:
		frappe.throw(_("Buyurtma uchun tovarni tanlang"))
	if not lead.normal_telefon:
		frappe.throw(_("Murojaatdagi telefon raqami noto'g'ri ({0}) — murojaatni ochib raqamni to'g'rilang").format(lead.telefon or "—"))

	shop = storefront.get_shop(shop_name)
	phone = "+" + lead.normal_telefon
	# Bor mijozning ismi o'zgartirilmaydi (raqam oila a'zosiniki bo'lishi mumkin) — yangisi murojaatdagi ism bilan
	customer = frappe._dict(phone=phone, customer=frappe.db.get_value("Customer", {"mp_phone": phone})
	                        or customers.get_or_create_customer(phone, lead.ism or lead.mijoz_ismi, lead.familiya, shop=shop.name))
	# Majburiy tovar (masalan, o'qiydigan ruchka) — mijoz hali olmagan bo'lsa buyurtmaga 1 dona qo'shiladi
	# (panelda ko'rinib turadi); variantlisining rang / o'lchamini menejer tanlaydi (qoshimcha)
	chosen = set(data.qoshimcha or [])
	for must in _must_items(shop_name, lead.normal_telefon, [ln["code"] for ln in lines]):
		pick = next((o["code"] for o in must["options"] if o["code"] in chosen), None)
		if not pick and must["has_variants"]:
			frappe.throw(_("Majburiy tovar «{0}»: rang / o'lchamni tanlang").format(must["name"]))
		lines.append({"code": pick or must["code"], "qty": 1})
	so = orders.place_order(shop, lines, method, data.manzil, customer)
	so.db_set({"payment_method": "Naqd", "order_source": ORDER_SOURCE.get(lead.manba, "Web"), "mp_aloqa_natija": "Oladi",
	           "mp_aloqa_kanal": kanal}, update_modified=False)
	so.add_comment("Info", _("Murojaat {0} bo'yicha sotuv menejeri yaratdi: {1}").format(lead.name, frappe.utils.get_fullname()))
	orders.confirm_order(so.name)
	if method == "Kuryer":
		notify_couriers(so)
	return so
