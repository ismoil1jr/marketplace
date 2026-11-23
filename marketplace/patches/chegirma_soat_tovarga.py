"""Chegirma barabani olib tashlandi: Shop'dagi sozlama (baraban_tovar, baraban_narx, baraban_yutuq) tovarning o'ziga —
«Chegirma soat qo'shish» (Item.mp_chegirma_soat, mp_chegirma_soati, mp_chegirma_narxi). Masalan Pandoo: Panda books,
3 soat, 360 000 so'm — deploydan keyin ham saytda xuddi shunday ishlaydi.

Shop JSON'dan maydonlar olib tashlangan, lekin jadval ustunlari (Frappe ularni o'chirmaydi) qoladi — shulardan o'qiladi."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt

FIELDS = ("mp_chegirma_soat", "mp_chegirma_soati", "mp_chegirma_narxi")


def execute():
	if not frappe.db.has_column("Shop", "baraban_yoqilgan"):
		return
	# Maydonlarni setup.after_migrate yaratadi — u patch'lardan keyin ishlaydi, shuning uchun shu yerda oldinroq
	from marketplace.setup import CUSTOM_FIELDS

	create_custom_fields({"Item": [f for f in CUSTOM_FIELDS["Item"] if f["fieldname"] in FIELDS]}, update=True)

	rows = frappe.db.sql(
		"""select name, baraban_tovar, baraban_narx, baraban_yutuq from `tabShop`
		where baraban_yoqilgan = 1 and ifnull(baraban_tovar, '') != ''""",
		as_dict=True,
	)
	for r in rows:
		item = frappe.db.get_value("Item", r.baraban_tovar, ["shop", "variant_of"], as_dict=True)
		if not item or item.shop != r.name or item.variant_of or flt(r.baraban_narx) <= 0:
			continue
		frappe.db.set_value(
			"Item",
			r.baraban_tovar,
			{"mp_chegirma_soat": 1, "mp_chegirma_soati": cint(r.baraban_yutuq) or 3, "mp_chegirma_narxi": flt(r.baraban_narx)},
			update_modified=False,
		)
