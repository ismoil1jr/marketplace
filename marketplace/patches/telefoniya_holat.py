import frappe
from frappe.utils import cint


def execute():
	"""Telefon Qongiroq'ning yangi maydonlari (Munisa opaning telefoniyasidagi kabi) — eski yozuvlar uchun to'ldiriladi:
	natija (davomiyligi 0 — javob yo'q), yozuv bor/yo'q, fayl hajmi, holat va manba."""
	for c in frappe.get_all("Telefon Qongiroq", fields=["name", "davomiyligi", "yozuv", "holat"]):
		size = None
		if c.yozuv:
			size = frappe.db.get_value("File", {"file_url": c.yozuv}, "file_size")
		frappe.db.set_value(
			"Telefon Qongiroq",
			c.name,
			{
				"natija": "Javob berildi" if cint(c.davomiyligi) > 0 else "Javob yo'q",
				"yozuv_bor": 1 if c.yozuv else 0,
				"fayl_hajmi": cint(size) or None,
				"holat": c.holat if c.holat not in (None, "", "Yangi") else ("Yozuv bor" if c.yozuv else "Yangi"),
				"manba": "Android",
			},
			update_modified=False,
		)
