import frappe


def execute():
	"""Sotuv menejeri roli — "Sotuv" moduli sahifasi va doctype'lari sinxronidan oldin bo'lishi kerak (rol havolasi)."""
	from marketplace.setup import SALES_ROLE

	if not frappe.db.exists("Role", SALES_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": SALES_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
