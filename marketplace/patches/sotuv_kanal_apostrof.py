import frappe


def execute():
	"""Kanal "Qo'ng'iroq" -> "Qo‘ng‘iroq": oddiy apostrof Desk ro'yxatida "Qo&#39;ng&#39;iroq" bo'lib chiqardi."""
	if frappe.db.table_exists("Aloqa Yozuvi"):
		frappe.db.sql("update `tabAloqa Yozuvi` set kanal = %s where kanal = %s", ("Qo‘ng‘iroq", "Qo'ng'iroq"))
	if frappe.db.has_column("Sales Order", "mp_aloqa_kanal"):
		frappe.db.sql("update `tabSales Order` set mp_aloqa_kanal = %s where mp_aloqa_kanal = %s", ("Qo‘ng‘iroq", "Qo'ng'iroq"))
