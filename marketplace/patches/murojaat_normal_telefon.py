import frappe

from marketplace.sotuv.doctype.murojaat.murojaat import lead_phone
from marketplace.sotuv.telefoniya import pretty_phone


def execute():
	"""Desk formasida qo'lda yaratilgan murojaatlarda normal_telefon bo'sh qolgan (faqat API to'ldirar edi) — to'ldiriladi.
	Shunda majburiy tovar tarixi ko'rinadi, menejer buyurtma yarata oladi va saytdagi buyurtma murojaatga ulanadi."""
	for r in frappe.get_all(
		"Murojaat", filters={"normal_telefon": ["is", "not set"]}, fields=["name", "telefon", "ism", "familiya", "mijoz_ismi"],
		limit_page_length=0,
	):
		normal = lead_phone(r.telefon)
		if not normal:
			continue
		vals = {"normal_telefon": normal, "telefon": pretty_phone(r.telefon)}
		if not r.mijoz_ismi:
			vals["mijoz_ismi"] = " ".join(x for x in (r.ism, r.familiya) if x).strip() or vals["telefon"]
		frappe.db.set_value("Murojaat", r.name, vals, update_modified=False)
	# Qo'lda tanlangan tovarning nomi ro'yxatda ko'rinsin ("Tovar ko'rsatilmagan" emas)
	for r in frappe.get_all("Murojaat", filters={"tovar": ["is", "set"], "tovar_nomi": ["is", "not set"]}, fields=["name", "tovar"], limit_page_length=0):
		name = frappe.db.get_value("Item", r.tovar, "item_name")
		if name:
			frappe.db.set_value("Murojaat", r.name, "tovar_nomi", name, update_modified=False)
