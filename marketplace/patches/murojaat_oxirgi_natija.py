"""Murojaat holati — menejerning OXIRGI natijasi bo'yicha. Avval «Buyurtma berdi» bir marta qo'yilsa, keyingi
«Olmaydi» / «Javob bermadi» / «Keyinroq» natijalari holatni o'zgartirmasdi (murojaat «Buyurtma berdi»da qolib ketardi).
Shunday qolib ketganlar oxirgi natijaga o'tkaziladi."""

import frappe


def execute():
	for lead in frappe.get_all("Murojaat", filters={"holat": "Buyurtma berdi"}, fields=["name", "buyurtma"]):
		last = frappe.get_all(
			"Menejer Xulosasi", filters={"murojaat": lead.name},
			fields=["natija", "buyurtma", "creation"], order_by="creation desc", limit=1,
		)
		if not last or last[0].buyurtma or last[0].natija in ("Oladi", None, ""):
			continue
		order_at = lead.buyurtma and frappe.db.get_value("Sales Order", lead.buyurtma, "creation")
		if order_at and order_at > last[0].creation:
			continue  # natijadan keyin buyurtma berilgan — «Buyurtma berdi» to'g'ri
		frappe.db.set_value("Murojaat", lead.name, "holat", last[0].natija, update_modified=False)
