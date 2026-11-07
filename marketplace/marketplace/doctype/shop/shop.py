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

		self.validate_telegram_ids()
		self.clean_links()
		self.validate_banner_items()

		owners = [m for m in self.members if m.role == "Ega"]
		if len(owners) > 1:
			frappe.throw(_("Do'konda faqat bitta Ega bo'lishi mumkin"))

		for m in self.members:
			other = frappe.db.get_value(
				"Shop Member", {"user": m.user, "parenttype": "Shop", "parent": ["!=", self.name]}, "parent"
			)
			if other:
				frappe.throw(_("{0} allaqachon {1} do'koniga a'zo").format(m.user, other))

	def validate_banner_items(self):
		from marketplace.storefront import BANNER_URL_RE

		for b in self.banners:
			if b.item and frappe.db.get_value("Item", b.item, "shop") != self.name:
				frappe.throw(_("Slayd {0}: «{1}» bu do'kon tovari emas").format(b.idx, b.item))
			b.url = (b.url or "").strip() or None
			if b.url and not BANNER_URL_RE.match(b.url):
				frappe.throw(_("Slayd {0}: havola https:// yoki / bilan boshlanishi kerak (masalan, /s/{1}/p/tovar-kodi)").format(b.idx, self.name))

	def clean_links(self):
		# Xarita havolasi uzun bo'ladi (Google/Yandex 200–600 belgi), maydon cheklanmagan — faqat http(s) havola qabul qilinadi
		self.pickup_map = (self.pickup_map or "").strip() or None
		if self.pickup_map and not re.match(r"^https?://\S+$", self.pickup_map):
			frappe.throw(_("Xaritadagi havola https:// bilan boshlanishi kerak: Yandex yoki Google xaritada «Ulashish» → havolani nusxalang"))
		# Instagram: "@nafis", "nafis" yoki to'liq havola (…instagram.com/nafis?igsh=…) — saytda @nafis bo'lib chiqadi
		insta = (self.instagram or "").strip()
		found = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", insta)
		self.instagram = (found.group(1) if found else insta.lstrip("@").split("?")[0].strip("/ ")) or None

	def validate_telegram_ids(self):
		"""Egasining Telegram ID'si (ixtiyoriy): kiritilsa — faqat raqam va faqat shu do'konniki (bot Ombor'ni shu ID bo'yicha ochadi)."""
		from marketplace.telegram_bot import _ids

		ids = _ids(self.telegram_ids)
		if not ids:
			self.telegram_ids = ""
			return
		for chat_id in ids:
			if not re.fullmatch(r"-?\d{5,15}", chat_id):
				frappe.throw(_("Telegram ID faqat raqamlardan iborat bo'ladi: {0}").format(chat_id))
		for other in frappe.get_all(
			"Shop", filters={"name": ["!=", self.name], "telegram_ids": ["is", "set"]}, fields=["shop_name", "telegram_ids"]
		):
			taken = set(ids) & set(_ids(other.telegram_ids))
			if taken:
				frappe.throw(_("Telegram ID {0} allaqachon {1} do'koniga biriktirilgan").format(", ".join(taken), other.shop_name))
		self.telegram_ids = ", ".join(ids)

	def after_insert(self):
		from marketplace.marketplace.doctype.rang.rang import seed_shop_colors
		from marketplace.seller_desk import remember_shop_sizes
		from marketplace.setup import SIZES

		# Har bir do'konga o'z ombori: qoldiq shu yerda yuritiladi
		if not self.warehouse:
			self.db_set("warehouse", self.create_warehouse())
		# Standart o'lchamlar (XS…3XL) va ranglar (Oq, Qora...) — do'konning o'z ro'yxati, keraksizini do'konchi o'chiradi
		remember_shop_sizes(self.name, SIZES)
		seed_shop_colors(self.name)
		# Instagram murojaatlari (lead-forma) shu kalit bilan keladi
		from marketplace.sotuv.murojaat import ensure_key

		ensure_key(self.name)

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
		from marketplace.setup import COURIER_ROLE, PACKER_ROLE, SALES_ROLE, SELLER_ROLE

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

		# Kuryer — faqat yetkazish va mijozlar anketasi; Sotuv menejer — faqat Sotuv paneli;
		# qolgan a'zolar — sotuvchi (do'kon paneli)
		roles = (SELLER_ROLE, COURIER_ROLE, SALES_ROLE, PACKER_ROLE)
		for m in self.members:
			user = frappe.get_doc("User", m.user)
			want = member_role(m.role)
			have = set(frappe.get_roles(m.user))
			other = [r for r in roles if r != want and r in have]
			if other:
				user.remove_roles(*other)
			if want not in have:
				user.add_roles(want)
			block_erpnext_modules(m.user)

		for user in existing - current:
			for allow, value in (("Shop", self.name), ("Warehouse", self.warehouse)):
				frappe.db.delete("User Permission", {"user": user, "allow": allow, "for_value": value})
			frappe.get_doc("User", user).remove_roles(SELLER_ROLE, COURIER_ROLE, SALES_ROLE, PACKER_ROLE)

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


def block_erpnext_modules(user):
	"""Do'kon a'zosiga Desk'da faqat Marketplace, Dokon va Sotuv modullari: ERPNext menyulari (Selling, Stock...) ko'rinmaydi.
	Keyin qo'shilgan modul (Sotuv) avval yopilgan bo'lsa — ochiladi."""
	keep = {"Marketplace", "Dokon", "Sotuv"}
	modules = set(frappe.get_all("Module Def", pluck="name")) - keep
	blocked = set(frappe.get_all("Block Module", filters={"parent": user, "parenttype": "User"}, pluck="module"))
	missing = modules - blocked
	if not missing and not blocked & keep:
		return
	doc = frappe.get_doc("User", user)
	doc.set("block_modules", [b for b in doc.block_modules if b.module not in keep])
	for module in sorted(missing):
		doc.append("block_modules", {"module": module})
	doc.flags.ignore_permissions = True
	doc.save()


def member_role(shop_role):
	"""Do'kon a'zosi roli (Shop Member.role) -> tizim roli."""
	from marketplace.setup import COURIER_ROLE, PACKER_ROLE, SALES_ROLE, SELLER_ROLE

	return {"Kuryer": COURIER_ROLE, "Sotuv menejer": SALES_ROLE, "Upakovkachi": PACKER_ROLE}.get(shop_role, SELLER_ROLE)


def user_validate(doc, method=None):
	"""User formasida rollar qo'lda o'zgartirilsa ham (Select All / Unselect All) do'kon a'zosi o'z rolida qoladi.
	Do'kon a'zosiga admin roli berilmaydi: u bilan foydalanuvchi do'konsiz, admin bo'lib ko'radi."""
	from marketplace.setup import COURIER_ROLE, PACKER_ROLE, SALES_ROLE, SELLER_ROLE

	if doc.name in ("Administrator", "Guest"):
		return
	roles = {r.role for r in doc.get("roles") or []}
	before = None if doc.is_new() else doc.get_doc_before_save()
	old = {r.role for r in before.get("roles") or []} if before else set()
	member = None if doc.is_new() else frappe.db.get_value(
		"Shop Member", {"user": doc.name, "parenttype": "Shop"}, ["parent", "role"], as_dict=True
	)
	if not member:
		# Do'kon rollari faqat do'kon a'zolari orqali: qo'lda berilsa foydalanuvchi do'konsiz qoladi va hech narsa
		# ko'rmaydi (permissions.NOTHING) — shuning uchun darhol to'g'ri yo'lni aytamiz
		shop_roles = sorted((roles - old) & {SELLER_ROLE, COURIER_ROLE, SALES_ROLE, PACKER_ROLE})
		if shop_roles and not frappe.is_setup_complete():
			# Sozlash ustasi birinchi foydalanuvchiga barcha rollarni beradi — u platforma admini: do'kon rollari
			# olib tashlanadi (ular bilan admin do'konsiz sotuvchi bo'lib, hech narsa ko'rmay qolardi)
			doc.set("roles", [r for r in doc.get("roles") if r.role not in shop_roles])
			return
		if shop_roles:
			frappe.throw(
				_("{0} roli shu yerda belgilanmaydi — foydalanuvchini do'konga biriktiring: User formasidagi «Do'konga biriktirish» "
				  "tugmasi yoki Do'kon formasi → A'zolar jadvali. Rolni o'sha yerda tanlaysiz: Ega / Menejer / Xodim — do'kon paneli, "
				  "Kuryer — yetkazish, Sotuv menejer — sotuv paneli, Upakovkachi — upakovka. Tizim roli, ruxsatlar va menyular o'zi qo'yiladi.").format(", ".join(shop_roles)),
				title=_("Avval do'konga biriktiring"),
			)
		return
	# Faqat shu saqlashda qo'shilgan admin roli: avvaldan admin bo'lgan a'zolarga (QA akkaunti) tegilmaydi
	admin = sorted((roles - old) & {"System Manager", "Marketplace Manager"})
	if admin:
		frappe.throw(
			_("{0} — «{1}» do'koni a'zosi ({2}). Do'kon a'zosiga {3} roli berilmaydi: u admin bo'lib qoladi va do'konini ko'rmaydi. "
			  "Admin qilmoqchi bo'lsangiz, avval do'kon a'zolaridan olib tashlang.").format(
				doc.name, frappe.db.get_value("Shop", member.parent, "shop_name"), member.role, ", ".join(admin)
			)
		)
	want = member_role(member.role)
	if want not in roles:
		doc.append("roles", {"role": want})


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
