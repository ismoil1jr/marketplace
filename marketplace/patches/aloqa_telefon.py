import frappe

OLD, NEW = "+998 90 910 22 02", "+998 99 801 10 26"


def execute():
	"""Bosh sahifadagi aloqa telefoni: eski standart raqam saqlangan bo'lsa — yangisiga (2026-11-05)."""
	if frappe.db.get_single_value("Marketplace Settings", "aloqa_telefon") == OLD:
		frappe.db.set_single_value("Marketplace Settings", "aloqa_telefon", NEW)
