"""Click / Payme orqali to'langan buyurtma menejer panelida «Yangi»da qo'ng'iroq kutib turardi (natija bo'sh).
To'lovning o'zi tasdiq: ularga «Oladi» qo'yiladi — panelda «To'langan · Oladi», upakovkachi va kuryerga avvalgidek."""

import frappe


def execute():
	so = frappe.qb.DocType("Sales Order")
	(
		frappe.qb.update(so)
		.set(so.mp_aloqa_natija, "Oladi")
		.set(so.mp_aloqa_vaqt, so.modified)
		.where(so.docstatus == 1)
		.where(so.payment_status == "To'langan")
		.where(so.payment_method.isin(["Click", "Payme"]))
		.where(so.mp_aloqa_natija.isnull() | (so.mp_aloqa_natija == ""))
	).run()
