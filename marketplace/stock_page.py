"""Sotuvchining "Ombor" sahifasi (Desk → /desk/ombor): barcha tovarlar rasmi, nomi va qoldig'i bir joyda.

Sahifa faqat ko'rish uchun: kirim tovar formasining "Ombor" tabida qilinadi, kamayish faqat sotuvdan.
"Kirim tarixi" bo'limida do'konning barcha kirimlari: kimdan, nechta, necha puldan.
"""

import frappe
from frappe.utils import cint, flt

from marketplace.inventory import low_threshold, status_of
from marketplace.permissions import get_user_shop, group_title


def _resolve_shop(shop=None):
	"""Sotuvchi — faqat o'z do'koni. Admin — tanlagan do'koni (shop parametri)."""
	own = get_user_shop()
	if own:
		return own
	if shop and set(frappe.get_roles()) & {"System Manager", "Marketplace Manager"} and frappe.db.exists("Shop", shop):
		return shop
	return None


@frappe.whitelist()
def get_stock_overview(search: str | None = None, only_low: int = 0, shop: str | None = None):
	"""Do'kon tovarlari (andoza va oddiy) qoldig'i bilan. Andozalarda variantlar ro'yxati."""
	shop = _resolve_shop(shop)
	is_admin = not get_user_shop()
	shops = frappe.get_all("Shop", fields=["name", "shop_name"], order_by="shop_name") if is_admin else []
	if not shop:
		return {"shop": None, "shops": shops, "products": []}
	data = shop_products(shop, search, only_low)
	return {"shop": shop, "shops": shops, **data}


def shop_products(shop, search=None, only_low=0):
	"""Do'kon tovarlari qoldig'i bilan (Desk'dagi Ombor, Telegram bot va ertalabki hisobot uchun).
	Ruxsat chaqiruvchida tekshiriladi: bu yerda faqat shu do'konning yozuvlari o'qiladi."""
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	threshold = low_threshold(shop)
	_status = lambda available: status_of(available, threshold)  # noqa: E731
	fields = ["name", "item_name", "item_group", "image", "has_variants", "variant_of", "variant_price", "is_published"]
	items = frappe.get_all("Item", filters={"shop": shop, "disabled": 0}, fields=fields, order_by="item_name asc")
	codes = [i.name for i in items]
	if not codes:
		return {"warehouse": warehouse, "low_stock": threshold, "products": []}

	# Bitta so'rov: do'kon omboridagi barcha qoldiqlar
	bins = {
		b.item_code: b
		for b in frappe.get_all(
			"Bin",
			filters={"item_code": ["in", codes], "warehouse": warehouse},
			fields=["item_code", "actual_qty", "reserved_qty"],
		)
	} if warehouse else {}

	pictures = {}
	for g in frappe.get_all(
		"Item Gallery",
		filters={"parent": ["in", codes], "parenttype": "Item"},
		fields=["parent", "thumbnail", "medium", "image"],
		order_by="idx asc",
	):
		pictures.setdefault(g.parent, g.thumbnail or g.medium or g.image)

	labels = {}
	for a in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", codes], "parenttype": "Item"},
		fields=["parent", "attribute_value"],
		order_by="idx asc",
	):
		if a.attribute_value:
			labels.setdefault(a.parent, []).append(a.attribute_value)

	from marketplace.storefront import _selling_price_list

	prices = {}
	for p in frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", codes], "price_list": _selling_price_list()},
		fields=["item_code", "price_list_rate"],
		order_by="valid_from desc",
	):
		prices.setdefault(p.item_code, flt(p.price_list_rate))

	def stock(code):
		b = bins.get(code) or {}
		actual, reserved = flt(b.get("actual_qty")), flt(b.get("reserved_qty"))
		return actual, reserved, max(actual - reserved, 0)

	variants = {}
	for i in items:
		if i.variant_of:
			actual, reserved, available = stock(i.name)
			variants.setdefault(i.variant_of, []).append(
				{
					"code": i.name,
					"name": i.item_name,
					"label": " · ".join(labels.get(i.name) or []) or i.item_name,
					"price": prices.get(i.name, 0),
					"actual": actual,
					"reserved": reserved,
					"available": available,
					"status": _status(available),
				}
			)

	products = []
	q = (search or "").strip().lower()
	for i in items:
		if i.variant_of:
			continue
		rows = sorted(variants.get(i.name, []), key=lambda v: v["code"]) if i.has_variants else []
		if i.has_variants:
			actual = sum(v["actual"] for v in rows)
			reserved = sum(v["reserved"] for v in rows)
			available = sum(v["available"] for v in rows)
			price = flt(i.variant_price) or min((v["price"] for v in rows if v["price"]), default=0)
		else:
			actual, reserved, available = stock(i.name)
			price = prices.get(i.name, 0)
		product = {
			"code": i.name,
			"name": i.item_name,
			"picture": pictures.get(i.name) or i.image,
			"category": group_title(i.item_group),
			"price": price,
			"is_template": cint(i.has_variants),
			"is_published": cint(i.is_published),
			"actual": actual,
			"reserved": reserved,
			"available": available,
			"status": _status(available),
			# Variantlardan biri tugagan yoki kam qolgan bo'lsa ham sotuvchi bilishi kerak
			"low_variants": sum(1 for v in rows if v["status"]),
			"variants": rows,
		}
		if q and q not in f"{i.item_name} {i.name} {i.item_group or ''}".lower():
			continue
		if cint(only_low) and not (product["status"] or product["low_variants"]):
			continue
		products.append(product)

	return {"warehouse": warehouse, "low_stock": threshold, "products": products}


@frappe.whitelist()
def get_movements(shop: str | None = None):
	"""Do'konning kirim tarixi (eng yangisi birinchi). Sotuvlar bu yerda yo'q: ular qoldiqni o'zi kamaytiradi."""
	from marketplace.reports import journal

	shop = _resolve_shop(shop)
	warehouse = shop and frappe.db.get_value("Shop", shop, "warehouse")
	return journal([warehouse], limit=200, kinds={"kirim"}) if warehouse else []
