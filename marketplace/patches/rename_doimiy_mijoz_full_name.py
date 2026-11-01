import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	"""Doimiy Mijoz.full_name -> mijoz_ismi ("Kim yozdi" maydonida mijoz ismi chiqardi)."""
	if frappe.db.has_column("Doimiy Mijoz", "full_name"):
		rename_field("Doimiy Mijoz", "full_name", "mijoz_ismi")
	for row in frappe.get_all("Doimiy Mijoz", fields=["name", "registered_by"]):
		if row.registered_by:
			frappe.db.set_value(
				"Doimiy Mijoz", row.name, "registered_by_full_name",
				frappe.db.get_value("User", row.registered_by, "full_name"), update_modified=False,
			)
