import frappe


def execute():
	"""Tranzaksiyalar uchun eski buyurtmalar: to'langan vaqt (izoh / topshirilgan vaqtdan) va naqdda noyob To'lov ID."""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	from marketplace.kassa import new_cash_id
	from marketplace.setup import CUSTOM_FIELDS

	# Maxsus maydonlar after_migrate'da (patch'lardan keyin) qo'shiladi — mp_payment_id / mp_paid_at kerak, hozir yaratamiz
	create_custom_fields({"Sales Order": CUSTOM_FIELDS["Sales Order"]}, update=True)

	for so in frappe.get_all(
		"Sales Order", filters={"docstatus": ["in", [1, 2]], "payment_method": "Naqd"},
		fields=["name", "payment_status", "mp_payment_id", "mp_paid_at", "mp_delivered_at", "modified"],
	):
		values = {}
		if not so.mp_payment_id:
			values["mp_payment_id"] = new_cash_id()
		if so.payment_status == "To'langan" and not so.mp_paid_at:
			comment = frappe.db.get_value(
				"Comment",
				{"reference_doctype": "Sales Order", "reference_name": so.name, "comment_type": "Info",
				 "content": ["like", "%aqd%olindi%"]},
				"creation", order_by="creation asc",
			)
			values["mp_paid_at"] = comment or so.mp_delivered_at or so.modified
		if values:
			frappe.db.set_value("Sales Order", so.name, values, update_modified=False)
