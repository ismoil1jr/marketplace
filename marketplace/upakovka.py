"""Upakovkachi: menejer tasdiqlagan buyurtmalarni kuryer kelguncha tayyorlab (upakovka qilib) qo'yadi.
Desk → Do'kon → "Upakovka" sahifasi (dokon/page/upakovka).

Oqim: menejer "Oladi" (sotuv/api.save_result yoki murojaat._make_order) → upakovkachiga xabar → u tovarlarni
rasmlari va soni bilan ko'rib yig'adi → "Upakovka qilindi" → kuryerga xabar, kuryer ro'yxatida "📦 Tayyor".
Mijoz o'zi olib ketadigan buyurtma ham upakovka qilinadi (menejersiz, saytda yakunlangach).
"""

import frappe
from frappe import _
from frappe.utils import flt, get_fullname, now_datetime

from marketplace.kassa import _shop

FIELDS = [
	"name", "customer_name", "customer_phone", "delivery_method", "delivery_address", "grand_total", "total_qty",
	"creation", "mp_aloqa_vaqt", "mp_courier", "mp_packed", "mp_packed_at", "mp_packer", "payment_method", "payment_status",
]


def _filters(shop, tab):
	"""todo — tasdiqlangan, hali upakovka qilinmagan; done — upakovka qilinganlar (topshirilganlari ham)."""
	base = {"shop": shop, "docstatus": 1, "mp_placed": 1, "payment_status": ["!=", "Bekor"]}
	if tab == "done":
		return {**base, "mp_packed": 1}
	return {**base, "mp_packed": 0, "per_delivered": ["<", 100]}


def _confirmed(so):
	"""Kuryer bilan yetkaziladigan buyurtma faqat menejer "Oladi" degandan keyin tayyorlanadi (kuryer ham shundan
	keyin ko'radi); o'zi olib ketadigan — saytda yakunlangani bilan."""
	return so.delivery_method != "Kuryer" or so.mp_aloqa_natija == "Oladi"


def _row(so):
	return {
		"name": so.name,
		"customer_name": so.customer_name,
		"phone": so.customer_phone,
		"delivery_method": so.delivery_method,
		"address": so.delivery_address,
		"amount": flt(so.grand_total),
		"qty": flt(so.total_qty),
		"created": str(so.creation),
		"confirmed_at": str(so.mp_aloqa_vaqt or so.creation),
		"courier": get_fullname(so.mp_courier) if so.mp_courier else None,
		"packed": int(bool(so.mp_packed)),
		"packed_at": str(so.mp_packed_at or ""),
		"packer": get_fullname(so.mp_packer) if so.mp_packer else None,
		"delivered": flt(so.per_delivered) >= 100,
	}


@frappe.whitelist()
def orders(tab: str = "todo"):
	shop = _shop()
	tab = "done" if tab == "done" else "todo"
	rows = frappe.get_all(
		"Sales Order", filters={**_filters(shop, tab), "docstatus": 1},
		fields=FIELDS + ["mp_aloqa_natija", "per_delivered"],
		order_by="mp_packed_at desc" if tab == "done" else "mp_aloqa_vaqt asc, creation asc",
		limit_page_length=60 if tab == "done" else 300,
	)
	rows = [r for r in rows if _confirmed(r)]
	# Har qatorda: nima tayyorlash kerak (nomi × soni) — ochmasdan ko'rinib tursin
	lines = {}
	for i in frappe.get_all(
		"Sales Order Item", filters={"parent": ["in", [r.name for r in rows] or [""]]},
		fields=["parent", "item_name", "qty"], order_by="idx asc",
	):
		lines.setdefault(i.parent, []).append(f"{i.item_name} × {flt(i.qty):g}")
	out = [{**_row(r), "lines": lines.get(r.name, [])} for r in rows]
	counts = {}
	for t in ("todo", "done"):
		found = frappe.get_all("Sales Order", filters=_filters(shop, t), fields=["delivery_method", "mp_aloqa_natija"], limit_page_length=0)
		counts[t] = sum(1 for r in found if _confirmed(r))
	return {"shop_name": frappe.db.get_value("Shop", shop, "shop_name") or shop, "rows": out, "counts": counts}


def _order(name, shop):
	so = frappe.get_doc("Sales Order", name)
	if so.shop != shop or so.docstatus != 1:
		frappe.throw(_("Bu buyurtma sizning do'koningizniki emas"), frappe.PermissionError)
	return so


@frappe.whitelist()
def order(name: str):
	"""Buyurtma kartasi: tovarlar rasmlari (mijoz olgan rangda), rang/o'lcham va soni — yig'ish uchun."""
	from marketplace.kuryer import _line_images
	from marketplace.storefront import variant_labels

	shop = _shop()
	so = _order(name, shop)
	codes = [i.item_code for i in so.items]
	names = dict(frappe.get_all("Item", filters={"name": ["in", codes or [""]]}, fields=["name", "variant_of"], as_list=True))
	titles = dict(frappe.get_all("Item", filters={"name": ["in", [v for v in names.values() if v] or [""]]}, fields=["name", "item_name"], as_list=True))
	labels = variant_labels(codes)
	images = _line_images(codes)
	items = [
		{
			"code": i.item_code,
			"name": titles.get(names.get(i.item_code)) or i.item_name,
			"variant": labels.get(i.item_code) or "",
			"qty": flt(i.qty),
			"images": images.get(i.item_code) or [],
		}
		for i in so.items
	]
	return {**_row(so), "items": items, "confirmed": _confirmed(so)}


@frappe.whitelist(methods=["POST"])
def mark_packed(name: str):
	"""Upakovkachi: buyurtma yig'ildi va qadoqlandi — kuryerga xabar ketadi, ro'yxatida «📦 Tayyor»."""
	from marketplace.seller_desk import _notify_users

	shop = _shop()
	so = _order(name, shop)
	if so.mp_packed:
		frappe.throw(_("Bu buyurtma allaqachon upakovka qilingan"))
	if so.payment_status == "Bekor" or so.docstatus != 1:
		frappe.throw(_("Bekor qilingan buyurtma"))
	if not _confirmed(so):
		frappe.throw(_("Menejer hali mijoz bilan gaplashib tasdiqlamagan — avval Sotuv panelida «Oladi»"))
	so.db_set({"mp_packed": 1, "mp_packed_at": now_datetime(), "mp_packer": frappe.session.user}, update_modified=False)
	who = get_fullname(frappe.session.user)
	so.add_comment("Info", _("📦 {0}: buyurtma upakovka qilindi, kuryerga tayyor").format(who))
	if so.delivery_method == "Kuryer":
		_notify_users(so, _("📦 {0} tayyor: {1} — {2}").format(so.name, so.customer_name, so.delivery_address or _("manzil yo'q")), {"role": "Kuryer"})
	return {"packed_at": str(so.mp_packed_at)}


@frappe.whitelist(methods=["POST"])
def unpack(name: str):
	"""Adashib bosilgan bo'lsa — qaytarish (topshirilmagan bo'lsa)."""
	shop = _shop()
	so = _order(name, shop)
	if flt(so.per_delivered) >= 100:
		frappe.throw(_("Buyurtma allaqachon mijozga topshirilgan"))
	so.db_set({"mp_packed": 0, "mp_packed_at": None, "mp_packer": None}, update_modified=False)
	so.add_comment("Info", _("{0}: upakovka belgisi olib tashlandi").format(get_fullname(frappe.session.user)))
	return True


def notify_packers(so):
	"""Tasdiqlangan buyurtma — do'kon upakovkachilariga (Desk xabari + sahifa o'zi yangilanadi)."""
	from marketplace.seller_desk import _notify_users

	if so.get("mp_packed"):
		return
	subject = _("Upakovka {0}: {1} — {2:g} dona").format(so.name, so.customer_name, flt(so.get("total_qty")))
	_notify_users(so, subject, {"role": "Upakovkachi"})
