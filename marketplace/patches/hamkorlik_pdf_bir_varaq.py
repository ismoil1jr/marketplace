import frappe


def execute():
	"""Shartnoma shabloni 1 varaqqa qisqartirildi (2026-11-22) — avval yaratilgan PDF'lar yangi shablon bilan qayta."""
	from marketplace.marketplace.doctype.hamkorlik.hamkorlik import attach_pdf

	for name in frappe.get_all("Hamkorlik", pluck="name"):
		attach_pdf(frappe.get_doc("Hamkorlik", name))
