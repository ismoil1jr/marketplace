import frappe
from frappe.utils import flt


def execute():
	"""Oddiy tovarda «Sotish narxi» bor, lekin Item Price yo'q (narx keyin qo'yilgan): ro'yxatga yozamiz —
	aks holda sayt uni «narxsiz» deb ko'rsatmas edi (2026-11-06)."""
	from marketplace.seller_desk import _set_price
	from marketplace.storefront import _selling_price_list

	price_list = _selling_price_list()
	rows = frappe.get_all(
		"Item",
		filters={"shop": ["is", "set"], "has_variants": 0, "variant_of": ["is", "not set"], "standard_rate": [">", 0], "disabled": 0},
		fields=["name", "standard_rate"],
	)
	for r in rows:
		if not frappe.db.exists("Item Price", {"item_code": r.name, "price_list": price_list, "selling": 1}):
			_set_price(r.name, flt(r.standard_rate))
