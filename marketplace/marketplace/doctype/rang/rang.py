# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from marketplace.permissions import get_user_shop


class Rang(Document):
	"""Do'konning o'z ranglari: har do'kon faqat o'zinikini ko'radi, qo'shadi va o'chiradi. Yangi do'konga
	standart ranglar (setup.COLORS) o'zi qo'shiladi (Shop.after_insert).

	ID va nom: tovar formasidagi havolalar (Ranglar, kirim, galereya) Rang ID'sini saqlaydi, variantlar esa
	ERPNext'ning umumiy "Rang" atributidagi nom (rang_nomi) bilan yaratiladi. Ikki do'konda bir xil "Oq"
	bo'lishi mumkin: ID boshqa do'konda band bo'lsa "Oq (clothes)" bo'ladi, ko'rinishi baribir "Oq"
	(title_field). ID'dan nomga — color_names()."""

	def autoname(self):
		name = self.rang_nomi = " ".join((self.rang_nomi or "").split())
		self.name = name
		if frappe.db.exists("Rang", name):
			base = self.name = f"{name} ({self.shop})"
			n = 1
			while frappe.db.exists("Rang", self.name):
				n += 1
				self.name = f"{base} {n}"

	def before_insert(self):
		# autoname'dan oldin: ID do'kon nomi bilan yasaladi
		self.shop = get_user_shop() or self.shop
		if not self.shop:
			frappe.throw(_("Do'konni tanlang"))

	def validate(self):
		self.shop = self.shop or get_user_shop()
		if not self.shop:
			frappe.throw(_("Do'konni tanlang"))
		self.rang_nomi = " ".join((self.rang_nomi or "").split())
		if "," in self.rang_nomi or ";" in self.rang_nomi:
			frappe.throw(_("Bitta yozuv — bitta rang. «{0}» ni alohida ranglar qilib qo'shing").format(self.rang_nomi))
		if len(self.rang_nomi) > 30 or not re.fullmatch(r"[\w\s\-/.()‘'ʻ+]+", self.rang_nomi):
			frappe.throw(_("Rang nomi qisqa bo'lsin: harf, raqam, - / . belgilari (masalan Oq, To'q ko'k)"))
		other = frappe.db.get_value("Rang", {"shop": self.shop, "rang_nomi": self.rang_nomi, "name": ["!=", self.name]})
		if other:
			frappe.throw(_("«{0}» rangi ro'yxatingizda bor").format(self.rang_nomi))

	def on_update(self):
		sync_attribute_value(self.rang_nomi, self.hex)

	def on_trash(self):
		"""Faqat shu do'kon tovarlari tekshiriladi: boshqa do'kondagi bir xil nomli rang bunga to'sqinlik qilmaydi.
		Variantlari bo'lsa — o'chirib bo'lmaydi; variantsiz tovarlardagi belgisi (Ranglar, galereya) olib tashlanadi."""
		from marketplace.setup import COLOR_ATTR

		shop_items = frappe.get_all("Item", filters={"shop": self.shop}, pluck="name")
		used = frappe.get_all(
			"Item Variant Attribute",
			filters={"attribute": COLOR_ATTR, "attribute_value": self.rang_nomi, "parent": ["in", shop_items or [""]]},
			pluck="parent",
			limit=5,
		)
		if used:
			frappe.throw(_("«{0}» rangida tovar variantlari bor ({1}). Avval ularni o'chiring yoki sotuvdan oling").format(
				self.rang_nomi, ", ".join(used)
			))
		frappe.db.delete("Tovar Rangi", {"rang": self.name})
		frappe.db.set_value("Item Gallery", {"rang": self.name}, "rang", None, update_modified=False)
		# Umumiy atribut qiymati — boshqa do'kon ham, biror variant ham ishlatmasa
		if not frappe.db.exists("Rang", {"rang_nomi": self.rang_nomi, "name": ["!=", self.name]}) and not frappe.db.exists(
			"Item Variant Attribute", {"attribute": COLOR_ATTR, "attribute_value": self.rang_nomi}
		):
			frappe.db.delete("Item Attribute Value", {"parent": COLOR_ATTR, "attribute_value": self.rang_nomi})
			frappe.clear_cache(doctype="Item Attribute")


def sync_attribute_value(name, hex_=None):
	"""Variantlar uchun nom ERPNext'ning umumiy "Rang" atributida bo'lishi kerak. Rangi (hex) har do'konning
	o'z Rang yozuvidan olinadi (shop_hexes); atributdagisi — faqat zaxira."""
	from marketplace.setup import COLOR_ATTR

	attr = frappe.get_doc("Item Attribute", COLOR_ATTR)
	row = next((r for r in attr.item_attribute_values if r.attribute_value.lower() == name.lower()), None)
	if row:
		if hex_ and not row.get("color_hex"):
			frappe.db.set_value("Item Attribute Value", row.name, "color_hex", hex_)
		return
	abbrs = {r.abbr for r in attr.item_attribute_values}
	abbr = re.sub(r"[^A-Za-z0-9]", "", name).upper()[:6] or frappe.generate_hash(length=4).upper()
	while abbr in abbrs:
		abbr = abbr[:5] + frappe.generate_hash(length=1).upper()
	attr.append("item_attribute_values", {"attribute_value": name, "abbr": abbr, "color_hex": hex_})
	attr.flags.ignore_permissions = True
	attr.save()


def shop_colors(shop):
	"""Do'kon ranglari qo'shilgan tartibda: [{name, rang_nomi, hex}]."""
	if not shop:
		return []
	return frappe.get_all(
		"Rang", filters={"shop": shop}, fields=["name", "rang_nomi", "hex"], order_by="creation asc", ignore_permissions=True
	)


def color_names(ids):
	"""{Rang ID: nomi} — "Oq (clothes)" -> "Oq". Variant atributi va saytda nom ishlatiladi."""
	ids = [i for i in dict.fromkeys(ids) if i]
	if not ids:
		return {}
	found = dict(frappe.get_all("Rang", filters={"name": ["in", ids]}, fields=["name", "rang_nomi"], as_list=True))
	return {i: found.get(i) or i for i in ids}


def shop_hexes(shop):
	"""{nomi: hex}: do'konning o'z rangi, bo'lmasa umumiy atributdagisi (eski yoki /panel'dan kelgan nomlar)."""
	from marketplace.setup import COLOR_ATTR

	hexes = dict(
		frappe.get_all("Item Attribute Value", filters={"parent": COLOR_ATTR}, fields=["attribute_value", "color_hex"], as_list=True)
	)
	hexes.update({c.rang_nomi: c.hex for c in shop_colors(shop) if c.hex})
	return hexes


def remember_shop_colors(shop, colors):
	"""Do'kon ro'yxatida yo'q ranglar qo'shiladi: colors = [(nomi, hex)] yoki [nomi]."""
	if not shop:
		return
	have = {c.rang_nomi.lower() for c in shop_colors(shop)}
	for color in colors:
		name, hex_ = color if isinstance(color, (list, tuple)) else (color, None)
		if name and name.lower() not in have:
			have.add(name.lower())
			frappe.get_doc({"doctype": "Rang", "rang_nomi": name, "hex": hex_, "shop": shop}).insert(ignore_permissions=True)


def seed_shop_colors(shop):
	"""Yangi do'kon: standart ranglar (Oq, Qora, Bej...) — keraksizini do'konchi o'chiradi."""
	from marketplace.setup import COLORS

	remember_shop_colors(shop, [(name, hex_) for name, _abbr, hex_ in COLORS])
