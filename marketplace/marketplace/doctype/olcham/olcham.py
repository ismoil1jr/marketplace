# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from marketplace.permissions import get_user_shop


class Olcham(Document):
	"""Do'konning o'z o'lchamlari: kiyimga XL, oyoq kiyimga 42, telefonga 128GB. Tovar kirimida
	shu ro'yxat chiqadi; kirimda yangisi yozilsa, bu yerga o'zi qo'shiladi (seller_desk.remember_shop_sizes)."""

	def validate(self):
		self.shop = get_user_shop() or self.shop
		if not self.shop:
			frappe.throw(_("Do'konni tanlang"))
		self.olcham = " ".join((self.olcham or "").split())
		if len(self.olcham) > 30 or not re.fullmatch(r"[\w\s\-/.,()×x+%‘'ʻ]+", self.olcham):
			frappe.throw(_("O'lcham nomi qisqa bo'lsin: harf, raqam, / . , - belgilari (masalan 42, XL, 128GB)"))
		if not self.tartib:
			# "max(tartib)" Frappe v16'da taqiqlangan (SQL funksiyasi matn sifatida): eng kattasini tartiblab olamiz
			last = frappe.db.get_value("Olcham", {"shop": self.shop, "name": ["!=", self.name]}, "tartib", order_by="tartib desc")
			self.tartib = (last or 0) + 1
		other = frappe.db.get_value(
			"Olcham", {"shop": self.shop, "olcham": self.olcham, "name": ["!=", self.name]}, "name"
		)
		if other:
			frappe.throw(_("\"{0}\" o'lchami ro'yxatda bor").format(self.olcham))
