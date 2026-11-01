import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Kirimdagi "Kimdan olindi" oddiy matn edi (Stock Entry.mp_supplier, Item.mp_kirim_supplier), endi Kontragent'ga
	havola: Stock Entry.mp_kontragent va Item.mp_kirim_kontragent. Frappe Data/Autocomplete maydonini Link'ga
	aylantirmaydi, shuning uchun maydonlar yangi, eskilari o'chiriladi.
	Har bir do'kondagi har xil matndan bitta Kontragent yaratiladi va kirim hujjatlari unga bog'lanadi."""
	from marketplace.setup import CUSTOM_FIELDS

	# after_migrate'gacha kutmaymiz: ma'lumot yangi maydonga hozir ko'chiriladi
	create_custom_fields(
		{
			"Stock Entry": [f for f in CUSTOM_FIELDS["Stock Entry"] if f["fieldname"] == "mp_kontragent"],
			"Item": [f for f in CUSTOM_FIELDS["Item"] if f["fieldname"] == "mp_kirim_kontragent"],
		},
		update=True,
	)
	if frappe.db.has_column("Stock Entry", "mp_supplier"):
		shops = dict(frappe.get_all("Shop", fields=["warehouse", "name"], as_list=True))
		made = {}  # (do'kon, ism) -> Kontragent
		for se in frappe.get_all(
			"Stock Entry", filters={"mp_supplier": ["is", "set"]}, fields=["name", "mp_supplier", "to_warehouse"]
		):
			shop = shops.get(se.to_warehouse)
			if frappe.db.get_value("Kontragent", se.mp_supplier, "shop") == shop:
				kontragent = se.mp_supplier
			elif not shop:
				continue
			else:
				name = " ".join(se.mp_supplier.split())
				key = (shop, name.lower())
				if key not in made:
					made[key] = frappe.db.get_value("Kontragent", {"shop": shop, "kontragent_name": name}) or (
						frappe.get_doc({"doctype": "Kontragent", "kontragent_name": name, "shop": shop})
						.insert(ignore_permissions=True)
						.name
					)
				kontragent = made[key]
			frappe.db.set_value("Stock Entry", se.name, "mp_kontragent", kontragent, update_modified=False)

	# Eski matn maydonlari (saqlanmay qolgan kirim formasidagi matn ham shu bilan ketadi)
	for name in ("Stock Entry-mp_supplier", "Item-mp_kirim_supplier"):
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True)
