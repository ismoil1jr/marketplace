"""Bir martalik: Google jadvaldagi eski qatorlar qayta yuborilganda (14-11) bir xil mijoz ikkinchi marta «Yangi»
murojaat bo'lib yozilgan, menejer natijasi esa birinchi yozuvda turibdi. «Yangi» takror murojaatga shu raqamning
OLDINROQ yaratilgan (30 kun ichida) murojaatidagi oxirgi menejer natijasi beriladi — faqat ochiq natijalar
(Keyinroq / Javob bermadi / Oladi). «Olmaydi» va buyurtma ko'chirilmaydi: bu haqiqiy yangi qiziqish bo'lishi mumkin.
Hech narsa o'chirilmaydi."""

import frappe
from frappe.utils import add_days

from marketplace.sotuv.murojaat import _same_item

ADOPT = ("Keyinroq", "Javob bermadi", "Oladi")


def execute():
	rows = frappe.get_all(
		"Murojaat", filters={"holat": "Yangi", "normal_telefon": ["is", "set"]},
		fields=["name", "shop", "normal_telefon", "tovar", "izoh", "creation"],
	)
	for row in rows:
		earlier = [
			o.name
			for o in frappe.get_all(
				"Murojaat",
				filters={"shop": row.shop, "normal_telefon": row.normal_telefon, "name": ["!=", row.name],
				         "creation": ["between", [add_days(row.creation, -30), row.creation]]},
				fields=["name", "tovar"],
			)
			if _same_item(row.tovar, o.tovar)
		]
		if not earlier:
			continue
		log = frappe.get_all(
			"Menejer Xulosasi",
			filters={"shop": row.shop, "murojaat": ["in", earlier], "bekor_qilindi": 0},
			fields=["murojaat", "natija", "keyingi_qongiroq", "menejer", "creation", "buyurtma"],
			order_by="creation desc, name desc", limit=1,
		)
		if not log or log[0].natija not in ADOPT or log[0].buyurtma:
			continue
		log = log[0]
		izoh = f"Takroriy murojaat (asl: {log.murojaat})." + (f" {row.izoh}" if row.izoh else "")
		frappe.db.set_value(
			"Murojaat", row.name,
			{"holat": log.natija, "keyingi_qongiroq": log.keyingi_qongiroq, "menejer": log.menejer,
			 "aloqa_vaqt": log.creation, "izoh": izoh[:2000]},
			update_modified=False,
		)
