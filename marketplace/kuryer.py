"""Kuryer: yetkaziladigan buyurtmalar sahifasi (Desk → Kuryer → "Yetkaziladigan buyurtmalar", dokon/page/kuryer_buyurtmalar).

Ro'yxatda: mijoz, telefon, holat, do'kon, to'lov holati, summa. Mijoz bosilganda — nima olgani (rasmlari bilan),
nechtadan, manzili; manzil bosilganda kuryer Google Maps yoki Yandex Maps'ni tanlaydi va yo'l ko'rsatiladi.
Topshirish — seller_desk.courier_delivered (buyurtma formasidagi tugma bilan bir xil).
"""

import frappe
from frappe import _
from frappe.utils import flt

from marketplace import kassa
from marketplace.permissions import require_roles
from marketplace.setup import COURIER_ROLE, SELLER_ROLE


def _shop(**kw):
	"""Kuryer sahifalari rollari (kuryer_buyurtmalar.json bilan bir xil): kuryer, do'kon egasi/xodimi, admin."""
	require_roles(COURIER_ROLE, SELLER_ROLE)
	return kassa._shop(**kw)
from marketplace.marketplace.doctype.rang.rang import color_names

FIELDS = [
	"name", "customer_name", "customer_phone", "shop", "payment_status", "payment_method", "grand_total",
	"delivery_address", "transaction_date", "per_delivered", "mp_cash_status", "mp_delivered_at", "docstatus",
	"mp_packed", "mp_packed_at",
]


def _filters(shop, tab):
	from marketplace.permissions import is_courier

	base = {"shop": shop, "docstatus": 1, "delivery_method": "Kuryer"}
	if tab == "done":
		# Kuryerga — o'zi topshirganlari (do'konning o'zi bergani aralashmasin)
		mine = {"mp_courier": frappe.session.user} if is_courier() else {}
		return {**base, **mine, "per_delivered": [">=", 100]}
	# Faqat menejer mijoz bilan gaplashib "Oladi" deb tasdiqlaganlari (sotuv/api.save_result)
	return {**base, "per_delivered": ["<", 100], "payment_status": ["!=", "Bekor"], "mp_aloqa_natija": "Oladi"}


def _state(so):
	"""(holat, rang): yetkazish nuqtai nazaridan — kuryerga nima qilish kerakligi."""
	if so.docstatus == 2 or so.payment_status == "Bekor":
		return "Bekor qilingan", "red"
	if flt(so.per_delivered) >= 100:
		return "Topshirilgan", "green"
	if so.payment_status == "To'langan" or so.payment_method == "Naqd":
		return "Yetkazilishi kerak", "blue"
	return "To'lov kutilmoqda", "gray"


def _loyal(shop, phones):
	"""{telefon: Doimiy Mijoz} — shu do'kon doimiy mijozlari ro'yxatidagilar (⭐ belgisi uchun)."""
	phones = list({p for p in phones if p})
	return dict(frappe.get_all(
		"Doimiy Mijoz", filters={"shop": shop, "phone": ["in", phones or [""]]}, fields=["phone", "name"], as_list=True,
	))


def _row(so, shop_name, loyal):
	state, color = _state(so)
	return {
		"name": so.name,
		"customer_name": so.customer_name,
		"phone": so.customer_phone,
		"shop_name": shop_name,
		"state": state,
		"state_color": color,
		"payment_status": so.payment_status,
		"payment_method": so.payment_method,
		"amount": flt(so.grand_total),
		"address": so.delivery_address,
		"date": str(so.transaction_date or ""),
		"delivered_at": str(so.mp_delivered_at or ""),
		"cash_in_hand": so.mp_cash_status == "Kuryerda",
		"loyal": loyal.get(so.customer_phone),
		# Upakovkachi yig'ib qadoqlab qo'ydimi (upakovka.py) — kuryer kelishidan oldin tayyor bo'lishi kerak
		"packed": int(bool(so.get("mp_packed"))),
		"packed_at": str(so.get("mp_packed_at") or ""),
	}


@frappe.whitelist()
def deliveries(tab: str = "active"):
	"""Kuryer ro'yxati. frappe.get_list — kuryerga faqat o'zinikini va hali hech kim olmaganini beradi
	(permissions.sales_order_query)."""
	shop = _shop()
	shop_name = frappe.db.get_value("Shop", shop, "shop_name") or shop
	tab = "done" if tab == "done" else "active"
	rows = frappe.get_list(
		"Sales Order",
		filters=_filters(shop, tab),
		fields=FIELDS,
		order_by="mp_delivered_at desc, creation desc" if tab == "done" else "creation desc",
		limit_page_length=50 if tab == "done" else 200,
	)
	counts = {t: len(frappe.get_list("Sales Order", filters=_filters(shop, t), pluck="name", limit_page_length=0)) for t in ("active", "done")}
	loyal = _loyal(shop, [so.customer_phone for so in rows])
	return {"shop_name": shop_name, "rows": [_row(so, shop_name, loyal) for so in rows], "counts": counts}


def _line_images(codes):
	"""{kod: [{src, full}]} — mijoz olgan rangdagi rasmlar: galereyada shu rangga bog'langanlari,
	bo'lmasa rangsizlari (umumiy rasmlar), bo'lmasa variant/tovar rasmi."""
	from marketplace.setup import COLOR_ATTR

	info = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", codes or [""]]}, fields=["name", "variant_of", "image"])}
	templates = {i.variant_of for i in info.values() if i.variant_of}
	base_image = dict(frappe.get_all("Item", filters={"name": ["in", list(templates) or [""]]}, fields=["name", "image"], as_list=True))
	gallery = {}
	for g in frappe.get_all(
		"Item Gallery",
		filters={"parent": ["in", list(set(codes) | templates) or [""]], "parenttype": "Item"},
		fields=["parent", "image", "medium", "rang"],
		order_by="idx asc",
	):
		gallery.setdefault(g.parent, []).append(g)
	# Galereyada Rang ID ("Oq (clothes)"), variantda nomi ("Oq")
	names = color_names([g.rang for rows in gallery.values() for g in rows])
	for rows in gallery.values():
		for g in rows:
			g.rang = names.get(g.rang)
	colors = dict(frappe.get_all(
		"Item Variant Attribute", filters={"parent": ["in", codes or [""]], "parenttype": "Item", "attribute": COLOR_ATTR},
		fields=["parent", "attribute_value"], as_list=True,
	))

	out = {}
	for code in codes:
		it = info.get(code) or frappe._dict()
		own = gallery.get(code) or []
		tpl = gallery.get(it.variant_of) or []
		color = colors.get(code)
		pics = own or [g for g in tpl if color and g.rang == color] or [g for g in tpl if not g.rang] or tpl
		images = [{"src": g.medium or g.image, "full": g.image or g.medium} for g in pics if g.image or g.medium]
		if not images:
			fallback = it.image or base_image.get(it.variant_of)
			images = [{"src": fallback, "full": fallback}] if fallback else []
		out[code] = images
	return out


def _route(so, city):
	"""Yo'l ko'rsatish uchun manzil: buyurtmadagi manzil (+ do'kon shahri, xarita topishi oson bo'lsin).
	Buyurtmada manzil yo'q bo'lsa — shu telefon bilan doimiy mijoz anketasidagi manzil va xaritadagi nuqta."""
	address = text = (so.delivery_address or "").strip()
	lat = lng = None
	source = "order"
	if not address and so.customer_phone:
		dm = frappe.db.get_value(
			"Doimiy Mijoz", {"shop": so.shop, "phone": so.customer_phone},
			["viloyat", "tuman", "kocha", "uy", "moljal", "latitude", "longitude"], as_dict=True,
		)
		if dm:
			address = text = ", ".join(p for p in (dm.viloyat, dm.tuman, dm.kocha, dm.uy and f"{dm.uy}-uy") if p)
			# Mo'ljal kuryerga ko'rinadi, lekin xarita qidiruviga qo'shilmaydi (topishni buzadi)
			if dm.moljal:
				text = f"{text} (mo'ljal: {dm.moljal})" if text else f"Mo'ljal: {dm.moljal}"
			if flt(dm.latitude) and flt(dm.longitude):
				lat, lng = flt(dm.latitude), flt(dm.longitude)
			source = "mijoz"
	query = address
	if address and city and city.lower() not in address.lower():
		query = f"{address}, {city}"
	return {"text": text, "query": query or text, "lat": lat, "lng": lng, "source": source}


@frappe.whitelist()
def delivery(order: str):
	"""Mijoz bosilganda: nima olgani (rasmlari bilan), nechtadan, manzili va to'lovi."""
	from marketplace.storefront import variant_labels

	shop = _shop()
	so = frappe.get_doc("Sales Order", order)
	if so.shop != shop or not frappe.has_permission("Sales Order", "read", so):
		frappe.throw(_("Bu buyurtma sizga tegishli emas"), frappe.PermissionError)

	shop_name, city = frappe.db.get_value("Shop", shop, ["shop_name", "city"]) or (shop, None)
	codes = [i.item_code for i in so.items]
	names = dict(frappe.get_all("Item", filters={"name": ["in", codes or [""]]}, fields=["name", "variant_of"], as_list=True))
	titles = dict(frappe.get_all("Item", filters={"name": ["in", [v for v in names.values() if v] or [""]]}, fields=["name", "item_name"], as_list=True))
	labels = variant_labels(codes)
	images = _line_images(codes)
	items = [
		{
			"name": titles.get(names.get(i.item_code)) or i.item_name,
			"variant": labels.get(i.item_code) or "",
			"qty": flt(i.qty),
			"uom": i.uom,
			"rate": flt(i.rate),
			"amount": flt(i.amount),
			"images": images.get(i.item_code) or [],
		}
		for i in so.items
	]
	return {
		**_row(so, shop_name, _loyal(shop, [so.customer_phone])),
		"route": _route(so, city),
		"items": items,
		"total_qty": flt(so.total_qty),
	}
