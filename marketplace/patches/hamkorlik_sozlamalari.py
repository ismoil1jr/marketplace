import frappe

DEFAULTS = {
	"hamkor_kompaniya": "«ORANGE TEAM» MChJ",
	"hamkor_rahbar": "Uchqunov A.",
	"hamkor_obuna": 50000,
	"hamkor_komissiya": 2,
}


def execute():
	"""Hamkorlik shartnomasi: Single'da maydon defaulti bazaga yozilmaydi — formada 0/bo'sh ko'rinib, admin
	sozlamani saqlasa 0 yozilib qolardi. Bir marta haqiqiy qiymat qo'yamiz (2026-11-22)."""
	for field, value in DEFAULTS.items():
		if not frappe.db.get_single_value("Marketplace Settings", field):
			frappe.db.set_single_value("Marketplace Settings", field, value)
