import frappe


def execute():
	"""Mavjud do'konlarga Instagram murojaatlari kaliti (yangi do'konga Shop.after_insert beradi)."""
	from marketplace.sotuv.murojaat import ensure_key

	for shop in frappe.get_all("Shop", pluck="name"):
		ensure_key(shop)
