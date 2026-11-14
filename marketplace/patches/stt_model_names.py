import frappe

OLD = {"gemini-3.8-flash-lite": "gemini-3.5-flash-lite"}


def execute():
	"""Zaxira model standarti noto'g'ri edi: «gemini-3.8-flash-lite» Google'da yo'q (Flash-Lite — gemini-3.5-flash-lite).
	Saqlangan qiymat eski standart bo'lsa — to'g'risiga; «modeli topilmadi» bilan yiqilganlar qayta navbatga."""
	from marketplace.sotuv.stt import retry_failed

	for field in ("gemini_model", "zaxira_model"):
		value = (frappe.db.get_single_value("Telefoniya Sozlamalari", field) or "").strip()
		if value in OLD:
			frappe.db.set_single_value("Telefoniya Sozlamalari", field, OLD[value])
	frappe.clear_document_cache("Telefoniya Sozlamalari", "Telefoniya Sozlamalari")
	retry_failed()
