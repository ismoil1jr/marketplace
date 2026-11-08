import frappe

OLD = {"+998 90 910 22 02", "+998 99 801 10 26"}
NEW = "+998 50 781 86 76"


def _digits(s):
	return "".join(ch for ch in (s or "") if ch.isdigit())


def execute():
	"""Call-center raqami o'zgardi (2026-11-08): bosh sahifadagi aloqa telefoni va do'konlarda saqlangan eski
	raqam — yangisiga. Bo'sh qiymat tegilmaydi (u doctype'dagi yangi default'ga tushadi)."""
	old_digits = {_digits(o) for o in OLD}
	cur = frappe.db.get_single_value("Marketplace Settings", "aloqa_telefon")
	if cur and _digits(cur) in old_digits:
		frappe.db.set_single_value("Marketplace Settings", "aloqa_telefon", NEW)
	for shop in frappe.get_all("Shop", fields=["name", "phone"]):
		if shop.phone and _digits(shop.phone) in old_digits:
			frappe.db.set_value("Shop", shop.name, "phone", NEW, update_modified=False)
