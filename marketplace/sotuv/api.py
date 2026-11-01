"""Sotuv paneli (Desk → Sotuv paneli): do'konning sotuv menejeri to'lanmagan buyurtmalar bilan ishlaydi.

* Ro'yxat: mijoz, telefon, summa; to'lanmagan / bugun qayta qo'ng'iroq / bekor / hammasi.
* Buyurtma: nima xarid qilingan, shu mijoz bilan qo'ng'iroqlar (audio) va oldingi natijalar.
* Natija (Aloqa Yozuvi): kanal (qo'ng'iroq / SMS), Oladi / Olmaydi / Javob bermadi / Keyinroq, qayta qo'ng'iroq sanasi.
  Oladi — saytda yakunlanmagan buyurtma tasdiqlanadi (naqd) va do'konga tushadi; Olmaydi — bekor (tovar sotuvga qaytadi).
* Qayta qo'ng'iroq sanasi kelganda menejerga eslatma (remind_callbacks, har soat).

Har bir menejer faqat o'z do'konini ko'radi (permissions.get_user_shop); admin — do'kon panelida tanlagan do'konni.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from marketplace.permissions import get_user_shop, is_admin, member_shop
from marketplace.sotuv.telefoniya import normalize_phone

ROLES = {"Shop Sales Manager", "Shop Seller", "System Manager", "Marketplace Manager"}
RESULTS = ("Oladi", "Olmaydi", "Javob bermadi", "Keyinroq")
# Tipografik apostrof (‘): oddiy ' Desk ro'yxatida "Qo&#39;ng&#39;iroq" bo'lib chiqadi
CHANNELS = ("Qo‘ng‘iroq", "SMS")
PAID, CANCELLED = "To'langan", "Bekor"


def _shop(admin_optional=False):
	# admin_optional: do'kon panelida bo'lmagan admin uchun xato emas, None (sahifa do'konni tanlashni so'raydi)
	if not ROLES & set(frappe.get_roles()):
		frappe.throw(_("Sotuv paneli faqat sotuv menejeri uchun"), frappe.PermissionError)
	shop = get_user_shop() or member_shop()
	if not shop and not (admin_optional and is_admin()):
		frappe.throw(_("Siz hech qaysi do'konga biriktirilmagansiz"), frappe.PermissionError)
	return shop


def _order(name, shop):
	so = frappe.get_doc("Sales Order", name)
	if so.shop != shop:
		frappe.throw(_("Bu buyurtma sizning do'koningizniki emas"), frappe.PermissionError)
	return so


def _filters(view, shop):
	base = {"shop": shop}
	if view == "tolanmagan":
		return {**base, "docstatus": 1, "payment_status": ["not in", [PAID, CANCELLED]]}
	if view == "bugun":
		return {**base, "docstatus": ["in", [1, 2]], "mp_keyingi_qongiroq": ["between", ["2000-01-01", today()]],
		        "payment_status": ["!=", PAID]}
	if view == "bekor":
		return {**base, "docstatus": ["in", [1, 2]], "payment_status": CANCELLED}
	return {**base, "docstatus": ["in", [1, 2]]}


@frappe.whitelist()
def get_orders(view: str = "tolanmagan", q: str | None = None):
	"""Ro'yxat va har bir bo'lim soni. q — ism, telefon yoki buyurtma raqami bo'yicha."""
	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	fields = [
		"name", "customer", "customer_name", "customer_phone", "grand_total", "transaction_date", "creation",
		"payment_status", "payment_method", "mp_placed", "docstatus", "per_delivered", "delivery_method",
		"mp_aloqa_natija", "mp_aloqa_kanal", "mp_aloqa_vaqt", "mp_keyingi_qongiroq",
	]
	or_filters = None
	if (q or "").strip():
		like = f"%{q.strip()}%"
		digits = normalize_phone(q) or ""
		or_filters = [["customer_name", "like", like], ["name", "like", like]]
		if len(digits) >= 4:
			or_filters.append(["customer_phone", "like", f"%{digits[-9:]}%"])
	rows = frappe.get_all(
		"Sales Order", filters=_filters(view, shop), or_filters=or_filters, fields=fields,
		order_by="creation desc", limit_page_length=300,
	)
	calls = {}
	phones = list({"".join(ch for ch in (r.customer_phone or "") if ch.isdigit()) for r in rows} - {""})
	if phones:
		for c in frappe.get_all(
			"Telefon Qongiroq", filters={"shop": shop, "normal_telefon": ["in", phones]},
			fields=["normal_telefon", {"COUNT": "*", "as": "n"}], group_by="normal_telefon",
		):
			calls[c.normal_telefon] = c.n
	# Oxirgi izoh — mijoz bo'yicha (raqam), qaysi buyurtmasiga yozilganidan qat'i nazar
	notes = {}
	tels = list({r.customer_phone for r in rows if r.customer_phone})
	if tels:
		for n in frappe.get_all(
			"Aloqa Yozuvi", filters={"shop": shop, "telefon": ["in", tels], "izoh": ["is", "set"]},
			fields=["telefon", "izoh", "creation"], order_by="creation desc",
		):
			notes.setdefault(n.telefon, n)
	for r in rows:
		r.calls = calls.get("".join(ch for ch in (r.customer_phone or "") if ch.isdigit()), 0)
		r.state = _state(r)
		note = notes.get(r.customer_phone)
		r.last_note = note.izoh if note else None
	counts = {v: frappe.db.count("Sales Order", _filters(v, shop)) for v in ("tolanmagan", "bugun", "bekor", "hammasi")}
	return {
		"shop": shop, "shop_name": frappe.db.get_value("Shop", shop, "shop_name"), "rows": rows, "counts": counts,
		# Rejim almashtirgichida "Murojaatlar · N yangi"
		"lead_new": frappe.db.count("Murojaat", {"shop": shop, "holat": "Yangi"}),
		"must": _has_must(shop),
	}


def _has_must(shop):
	"""Tepada "Majburiy tovar: raqam tekshirish" tugmasi — faqat majburiy tovari bor do'konda."""
	from marketplace.orders import mandatory_items

	return bool(mandatory_items(shop))


def _state(so):
	if so.docstatus == 2 or so.payment_status == CANCELLED:
		return "Bekor qilingan"
	if so.payment_status == PAID:
		return "To'langan"
	if not so.mp_placed:
		return "Saytda yakunlanmagan"
	return "Naqd — to'lanmagan" if so.payment_method == "Naqd" else "To'lov kutilmoqda"


@frappe.whitelist()
def get_order(name: str):
	"""Buyurtma kartasi: xarid qilingan tovarlar, qo'ng'iroqlar (audio) va natijalar tarixi."""
	shop = _shop()
	so = _order(name, shop)
	from marketplace.storefront import variant_labels

	codes = [i.item_code for i in so.items]
	labels = variant_labels(codes)
	info = {
		i.name: i
		for i in frappe.get_all("Item", filters={"name": ["in", codes or [""]]}, fields=["name", "item_name", "variant_of", "image"])
	}
	bases = dict(
		frappe.get_all("Item", filters={"name": ["in", [i.variant_of for i in info.values() if i.variant_of] or [""]]},
		               fields=["name", "item_name"], as_list=True)
	)
	items = []
	for i in so.items:
		it = info.get(i.item_code) or frappe._dict()
		items.append(
			{
				"item_code": i.item_code, "name": bases.get(it.variant_of) or it.item_name or i.item_name,
				"variant": labels.get(i.item_code) or "", "qty": flt(i.qty), "rate": flt(i.rate), "amount": flt(i.amount),
				"image": it.image,
			}
		)
	normal = normalize_phone(so.customer_phone)
	calls = frappe.get_all(
		"Telefon Qongiroq",
		filters={"shop": shop},
		or_filters=[["buyurtma", "=", so.name]] + ([["normal_telefon", "=", normal]] if normal else []),
		fields=["name", "boshlandi", "yonalish", "davomiyligi", "yozuv", "menejer", "izoh", "holat", "natija", "ai_xulosa", "transkript"],
		order_by="boshlandi desc", limit_page_length=50,
	)
	# Izohlar va natijalar — shu mijozning barcha buyurtmalari bo'yicha (raqam bilan): boshqa kuni ochilsa ham turadi
	log_filters = [["buyurtma", "=", so.name]] + ([["telefon", "=", so.customer_phone]] if so.customer_phone else [])
	logs = frappe.get_all(
		"Aloqa Yozuvi", filters={"shop": shop}, or_filters=log_filters,
		fields=["name", "creation", "buyurtma", "kanal", "natija", "izoh", "keyingi_qongiroq", "menejer", "bekor_qilindi"],
		order_by="creation desc", limit_page_length=100,
	)
	# Raqami kelmagan (mijozga bog'lanmagan) yaqindagi qo'ng'iroqlar — menejer shu buyurtmaga biriktira oladi
	unlinked = frappe.get_all(
		"Telefon Qongiroq",
		filters={"shop": shop, "buyurtma": ["is", "not set"], "boshlandi": [">=", add_days(now_datetime(), -3)]},
		fields=["name", "boshlandi", "yonalish", "davomiyligi", "yozuv", "menejer", "telefon"],
		order_by="boshlandi desc", limit_page_length=20,
	)
	users = {u for u in [c.menejer for c in calls + unlinked] + [lg.menejer for lg in logs] if u}
	names = {u: frappe.utils.get_fullname(u) for u in users}
	for c in calls + unlinked:
		c.menejer_ismi = names.get(c.menejer) or c.menejer
	for lg in logs:
		lg.menejer_ismi = names.get(lg.menejer) or lg.menejer
	return {
		"name": so.name, "customer_name": so.customer_name, "customer_phone": so.customer_phone,
		"grand_total": flt(so.grand_total), "created": str(so.creation), "state": _state(so),
		"payment_method": so.payment_method, "delivery_method": so.get("delivery_method"),
		"delivery_address": so.get("delivery_address"), "items": items, "calls": calls, "logs": logs, "unlinked": unlinked,
		"can_cancel": _can_cancel(so), "mandatory": mandatory_info(shop, so.customer_phone),
	}


def mandatory_info(shop, phone):
	"""Kartadagi "Majburiy tovar" bloki: har bir majburiy tovar alohida — shu raqam olganmi (asos bilan)."""
	from marketplace.orders import mandatory_bought, mandatory_items

	items = mandatory_items(shop)
	if not items:
		return None
	bought = mandatory_bought(shop, phone, items)
	names = dict(frappe.get_all("Item", filters={"name": ["in", items]}, fields=["name", "item_name"], as_list=True))
	return {
		"phone": phone,
		"items": [{"code": c, "name": names.get(c) or c, "basis": bought.get(c)} for c in items],
		"missing": sum(c not in bought for c in items),
	}


@frappe.whitelist()
def mandatory_check(phone: str):
	"""Call-center: mijoz qo'ng'iroq qildi — raqami bo'yicha qaysi majburiy tovarni olgan, qaysini yo'q
	(buyurtmasi yoki murojaati bo'lmasa ham)."""
	from marketplace.otp import normalize_phone

	info = mandatory_info(_shop(), normalize_phone(phone))
	if not info:
		frappe.throw(_("Bu do'konda majburiy tovar belgilanmagan"))
	return info


@frappe.whitelist(methods=["POST"])
def confirm_old_phone(phone: str, old_phone: str):
	"""Call-center: mijoz raqamini almashtirgan. Eski raqamdan qaysi majburiy tovar olingan bo'lsa — faqat o'sha
	tovarlar yangi raqamga tasdiqlanadi (har biri alohida Majburiy Tasdiq: kim, qachon, qaysi buyurtma asosida).
	Eski raqam ham olmagan tovarni tasdiqlab bo'lmaydi — mijoz uni sotib olishi kerak."""
	from marketplace.orders import mandatory_bought, mandatory_items
	from marketplace.otp import normalize_phone

	shop = _shop()
	new, old = normalize_phone(phone), normalize_phone(old_phone)
	if new == old:
		frappe.throw(_("Eski raqam yangi raqam bilan bir xil"))
	items = mandatory_items(shop)
	if not items:
		frappe.throw(_("Bu do'konda majburiy tovar belgilanmagan"))
	have = mandatory_bought(shop, new, items)
	old_have = mandatory_bought(shop, old, items)
	if not old_have:
		frappe.throw(_("{0} raqamidan bu do'konda majburiy tovar xaridi topilmadi").format(old))
	confirmed = []
	for code, basis in old_have.items():
		if code in have:
			continue
		order = basis if frappe.db.exists("Sales Order", basis) else frappe.db.get_value("Majburiy Tasdiq", basis, "asos_buyurtma")
		frappe.get_doc(
			{
				"doctype": "Majburiy Tasdiq", "shop": shop, "telefon": new, "tovar": code, "eski_telefon": old,
				"asos_buyurtma": order, "tasdiqladi": frappe.session.user,
				"izoh": _("Eski raqam {0} bo'yicha tekshirildi (asos: {1})").format(old, basis),
			}
		).insert(ignore_permissions=True)
		confirmed.append(code)
	info = mandatory_info(shop, new)
	names = {i["code"]: i["name"] for i in info["items"]}
	info["confirmed"] = [names[c] for c in confirmed]
	return info


def _can_cancel(so):
	return so.docstatus == 1 and so.payment_status != CANCELLED and not flt(so.per_delivered) and not (
		so.payment_status == PAID and so.payment_method in ("Payme", "Click")
	)


@frappe.whitelist(methods=["POST"])
def attach_call(call: str, order: str):
	"""Raqami kelmagan qo'ng'iroqni menejer shu buyurtmaga biriktiradi (mijoz, telefon ham yoziladi)."""
	shop = _shop()
	so = _order(order, shop)
	if frappe.db.get_value("Telefon Qongiroq", call, "shop") != shop:
		frappe.throw(_("Bu qo'ng'iroq sizning do'koningizniki emas"), frappe.PermissionError)
	frappe.db.set_value(
		"Telefon Qongiroq", call,
		{"buyurtma": so.name, "mijoz": so.customer, "mijoz_ismi": so.customer_name,
		 "telefon": so.customer_phone, "normal_telefon": normalize_phone(so.customer_phone)},
	)
	return get_order(so.name)


@frappe.whitelist(methods=["POST"])
def save_result(order: str, kanal: str, natija: str, izoh: str | None = None, keyingi_qongiroq: str | None = None,
                bekor: int = 0):
	"""Menejer natijasi. Oladi — saytda yakunlanmagan buyurtma tasdiqlanadi (naqd) va do'konga tushadi;
	Olmaydi + bekor — buyurtma bekor qilinadi (zaxira bo'shaydi, tovar sotuvga qaytadi)."""
	shop = _shop()
	so = _order(order, shop)
	if kanal not in CHANNELS or natija not in RESULTS:
		frappe.throw(_("Kanal va natijani tanlang"))
	date = getdate(keyingi_qongiroq) if keyingi_qongiroq else None
	if date and date < getdate(today()):
		frappe.throw(_("Qayta qo'ng'iroq sanasi o'tib ketgan kun bo'lmasin"))
	cancel = natija == "Olmaydi" and cint(bekor) and _can_cancel(so)

	log = frappe.get_doc(
		{
			"doctype": "Aloqa Yozuvi", "buyurtma": so.name, "mijoz_ismi": so.customer_name, "telefon": so.customer_phone,
			"shop": shop, "kanal": kanal, "natija": natija, "izoh": (izoh or "").strip() or None,
			"keyingi_qongiroq": date, "menejer": frappe.session.user, "bekor_qilindi": int(bool(cancel)),
		}
	)
	log.insert(ignore_permissions=True)
	so.db_set(
		{"mp_aloqa_natija": natija, "mp_aloqa_kanal": kanal, "mp_aloqa_vaqt": now_datetime(), "mp_keyingi_qongiroq": date},
		update_modified=False,
	)
	who = frappe.utils.get_fullname(frappe.session.user)
	note = f"{who}: {kanal} — {natija}" + (f". {log.izoh}" if log.izoh else "") + (f". Qayta qo'ng'iroq: {date}" if date else "")
	so.add_comment("Info", note)

	from marketplace.orders import as_system, confirm_order

	if natija == "Oladi" and so.docstatus == 1 and so.payment_status != CANCELLED and not so.mp_placed:
		# Mijoz saytda to'lov usulini tanlamay qolgan — menejer telefonda kelishdi: naqd, do'konga tushadi
		if not so.payment_method:
			so.db_set("payment_method", "Naqd", update_modified=False)
		confirm_order(so.name)
	if cancel:
		so.db_set("payment_status", CANCELLED)
		with as_system():
			so.reload()
			so.cancel()
	return {"name": log.name, "cancelled": bool(cancel)}


def remind_callbacks():
	"""Har soat: qayta qo'ng'iroq sanasi kelgan buyurtmalar — menejerga Desk'da eslatma (bir marta)."""
	for row in frappe.get_all(
		"Aloqa Yozuvi",
		filters={"keyingi_qongiroq": ["between", ["2000-01-01", today()]], "eslatildi": 0},
		fields=["name", "buyurtma", "murojaat", "mijoz_ismi", "telefon", "menejer", "shop", "keyingi_qongiroq"],
	):
		# Keyin yangi natija yozilgan bo'lsa (sana o'zgargan / olib tashlangan) — eski eslatma kerak emas
		doctype, docname = ("Murojaat", row.murojaat) if row.murojaat else ("Sales Order", row.buyurtma)
		current = frappe.db.get_value(doctype, docname, "keyingi_qongiroq" if row.murojaat else "mp_keyingi_qongiroq")
		if current and getdate(current) == getdate(row.keyingi_qongiroq):
			users = {row.menejer} if row.menejer else set(
				frappe.get_all("Shop Member", filters={"parent": row.shop, "role": "Sotuv menejer"}, pluck="user")
			)
			subject = _("Bugun qayta qo'ng'iroq: {0} {1} ({2})").format(row.mijoz_ismi or "", row.telefon or "", docname)
			for user in users:
				frappe.get_doc(
					{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": doctype,
					 "document_name": docname, "subject": subject}
				).insert(ignore_permissions=True)
				frappe.publish_realtime("marketplace_new_order", {"name": docname, "subject": subject}, user=user, after_commit=True)
		frappe.db.set_value("Aloqa Yozuvi", row.name, "eslatildi", 1, update_modified=False)
	frappe.db.commit()
