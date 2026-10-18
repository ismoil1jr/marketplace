# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

# nafis-tekstil, shop2, a-b-c  ✓     Nafis Tekstil, -shop, shop--x, do'kon  ✗
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Shop(Document):
	def validate(self):
		self.slug = (self.slug or "").strip().lower()
		if not SLUG_RE.match(self.slug):
			frappe.throw(
				_("Slug faqat kichik lotin harflari, raqam va chiziqchadan iborat bo'lishi kerak (masalan: nafis-tekstil)")
			)

		owners = [m for m in self.members if m.role == "Ega"]
		if len(owners) > 1:
			frappe.throw(_("Do'konda faqat bitta Ega bo'lishi mumkin"))

		for m in self.members:
			other = frappe.db.get_value(
				"Shop Member", {"user": m.user, "parenttype": "Shop", "parent": ["!=", self.name]}, "parent"
			)
			if other:
				frappe.throw(_("{0} allaqachon {1} do'koniga a'zo").format(m.user, other))

	def after_insert(self):
		# Har bir do'konga o'z ombori: qoldiq shu yerda yuritiladi
		if not self.warehouse:
			self.db_set("warehouse", self.create_warehouse())

	def on_update(self):
		self.sync_member_permissions()

	def on_trash(self):
		if self.warehouse and frappe.db.exists("Stock Ledger Entry", {"warehouse": self.warehouse}):
			frappe.throw(_("Do'konda ombor harakati bor. O'chirish o'rniga Status'ni Suspended qiling."))

		self.members = []
		self.sync_member_permissions()

		if self.warehouse:
			# Ombor va do'kon bir-biriga bog'langan: avval bog'lanishni uzib, keyin omborni o'chiramiz
			warehouse, self.warehouse = self.warehouse, None
			self.db_set("warehouse", None)
			frappe.delete_doc("Warehouse", warehouse, ignore_permissions=True)

	def sync_member_permissions(self):
		"""A'zolar ro'yxatiga qarab User Permission va rolni qo'shadi yoki olib tashlaydi.

		User Permission (Shop = shu do'kon) bo'lgan foydalanuvchi `shop` maydoni bor
		har qanday DocType'da faqat shu do'kon yozuvlarini ko'radi.
		"""
		from marketplace.setup import SELLER_ROLE

		current = {m.user for m in self.members}
		existing = set(
			frappe.get_all("User Permission", filters={"allow": "Shop", "for_value": self.name}, pluck="user")
		)

		for user in current - existing:
			for allow, value in (("Shop", self.name), ("Warehouse", self.warehouse)):
				if value:
					frappe.get_doc(
						{
							"doctype": "User Permission",
							"user": user,
							"allow": allow,
							"for_value": value,
							"is_default": 1,
						}
					).insert(ignore_permissions=True)
			frappe.get_doc("User", user).add_roles(SELLER_ROLE)

		for user in existing - current:
			for allow, value in (("Shop", self.name), ("Warehouse", self.warehouse)):
				frappe.db.delete("User Permission", {"user": user, "allow": allow, "for_value": value})
			frappe.get_doc("User", user).remove_roles(SELLER_ROLE)

		frappe.clear_cache()

	def create_warehouse(self):
		company = frappe.defaults.get_global_default("company")
		if not company:
			frappe.throw(_("Avval Global Defaults'da standart Company'ni belgilang"))

		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": self.slug,
				"company": company,
				"parent_warehouse": get_shops_group_warehouse(company),
				"shop": self.name,
			}
		)
		warehouse.insert(ignore_permissions=True)
		return warehouse.name


def get_shops_group_warehouse(company):
	"""Barcha do'kon omborlari daraxtda bitta "Do'konlar" guruhi ichida turadi."""
	name = frappe.db.get_value("Warehouse", {"warehouse_name": "Do'konlar", "company": company, "is_group": 1})
	if name:
		return name

	root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1, "parent_warehouse": ["in", ["", None]]})
	group = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": "Do'konlar",
			"company": company,
			"is_group": 1,
			"parent_warehouse": root,
		}
	)
	group.insert(ignore_permissions=True)
	return group.name
