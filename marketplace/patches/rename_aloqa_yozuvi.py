import frappe


def execute():
	"""«Aloqa Yozuvi» -> «Menejer Xulosasi»: nom chalkashtirardi (audio yozuv deb o'ylashardi). Jadval, ruxsatlar,
	bog'lanishlar Frappe rename_doc bilan ko'chadi. pre_model_sync: sinxronlashdan OLDIN, aks holda bo'sh yangi jadval ochilardi."""
	if frappe.db.exists("DocType", "Aloqa Yozuvi") and not frappe.db.exists("DocType", "Menejer Xulosasi"):
		frappe.rename_doc("DocType", "Aloqa Yozuvi", "Menejer Xulosasi", force=True, show_alert=False)
		frappe.db.commit()
