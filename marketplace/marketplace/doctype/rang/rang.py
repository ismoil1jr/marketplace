# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document


class Rang(Document):
	"""Ranglar ro'yxati. Har bir rang ERPNext'ning "Rang" Item Attribute qiymatiga ham yoziladi —
	variantlar o'sha orqali yaratiladi, saytda esa hex rangi doiracha bo'lib chiqadi."""

	def validate(self):
		self.rang_nomi = (self.rang_nomi or "").strip()

	def on_update(self):
		sync_attribute_value(self.rang_nomi, self.hex)


def sync_attribute_value(name, hex_=None):
	from marketplace.setup import COLOR_ATTR

	attr = frappe.get_doc("Item Attribute", COLOR_ATTR)
	row = next((r for r in attr.item_attribute_values if r.attribute_value.lower() == name.lower()), None)
	if row:
		if hex_ and row.get("color_hex") != hex_:
			frappe.db.set_value("Item Attribute Value", row.name, "color_hex", hex_)
		return
	abbrs = {r.abbr for r in attr.item_attribute_values}
	abbr = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:6] or frappe.generate_hash(length=4).upper()
	while abbr in abbrs:
		abbr = abbr[:5] + frappe.generate_hash(length=1).upper()
	attr.append("item_attribute_values", {"attribute_value": name, "abbr": abbr, "color_hex": hex_})
	attr.flags.ignore_permissions = True
	attr.save()
