"""Chegirma soat («Tabriklaymiz! N soatlik chegirma» oynasi, tepadagi taymer, chegirma narxi) butunlay olib tashlandi
(2026-11-24, SMM rahbari bilan kelishilgan): tovar formasidagi 3 ta maydon va «Baraban Chegirma» jadvali o'chiriladi."""

import frappe


def execute():
	for fieldname in ("mp_chegirma_soat", "mp_chegirma_soati", "mp_chegirma_narxi"):
		name = frappe.db.get_value("Custom Field", {"dt": "Item", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
	if frappe.db.exists("DocType", "Baraban Chegirma"):
		frappe.delete_doc("DocType", "Baraban Chegirma", ignore_permissions=True, force=True)
	# delete_doc jadvalni o'chirmaydi — unda faqat mijozlarning chegirma taymerlari edi
	frappe.db.sql_ddl("drop table if exists `tabBaraban Chegirma`")
	frappe.db.delete("Scheduled Job Type", {"method": ["like", "marketplace.baraban.%"]})
