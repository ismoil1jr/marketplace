"""App o'rnatilganda va har `bench migrate` da ishlaydi.

Standart ERPNext DocType'lariga qo'shiladigan maydonlar va sotuvchi roli shu yerda.
Kod orqali yaratilgani uchun har saytda bir xil bo'ladi va git'da saqlanadi.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

from marketplace.admin import setup_admin_workspace
from marketplace.seller_desk import setup_seller_workspace

SELLER_ROLE = "Shop Seller"
# Platforma xodimi: barcha do'konlarni boshqaradi, lekin tizim sozlamalariga (System Manager) kirmaydi
MANAGER_ROLE = "Marketplace Manager"

SHOP_FIELD = {
	"fieldname": "shop",
	"label": "Shop",
	"fieldtype": "Link",
	"options": "Shop",
	"search_index": 1,
	"in_standard_filter": 1,
}

CUSTOM_FIELDS = {
	"Item": [
		{**SHOP_FIELD, "insert_after": "item_group", "in_list_view": 1},
		{
			"fieldname": "is_published",
			"label": "Saytda ko'rsatish",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "shop",
		},
		{
			"fieldname": "variant_price",
			"label": "Sotish narxi (barcha variantlarga)",
			"fieldtype": "Currency",
			"insert_after": "standard_rate",
			"depends_on": "eval:doc.has_variants",
			"description": "Rang/o'lchamli tovarda narx har bir variantga shu yerdan avtomatik qo'yiladi",
		},
		{
			"fieldname": "ranglar",
			"label": "Ranglar",
			"fieldtype": "Table MultiSelect",
			"options": "Tovar Rangi",
			"insert_after": "variant_price",
			"depends_on": "eval:doc.has_variants",
			"description": "Ro'yxatdan tanlang. Yo'q rang bo'lsa, yozib \"+ Create a new Rang\" bosing",
		},
		{
			# Ichki: ranglar jadvalidan yig'iladi (seller_desk.item_default_attributes)
			"fieldname": "variant_colors",
			"label": "Ranglar (matn)",
			"fieldtype": "Small Text",
			"insert_after": "ranglar",
			"hidden": 1,
		},
		{
			"fieldname": "variant_sizes",
			"label": "O'lchamlar",
			"fieldtype": "Small Text",
			"insert_after": "variant_colors",
			"depends_on": "eval:doc.has_variants",
			"description": "Vergul bilan: S, M, L yoki 42, 44, 46 yoki 110 sm. Yangi nomlar avtomatik qo'shiladi",
		},
		{
			"fieldname": "variant_qty",
			"label": "Har bir variantdan nechta (omborga)",
			"fieldtype": "Int",
			"insert_after": "variant_sizes",
			"depends_on": "eval:doc.has_variants",
			"description": "Yangi yaratilgan har bir rang/o'lcham uchun omborga shuncha yoziladi. Keyin Ombor sahifasida alohida o'zgartirsa bo'ladi",
		},
		{
			"fieldname": "in_carousel",
			"label": "Karuselga qo'shish",
			"fieldtype": "Check",
			"insert_after": "is_published",
			"description": "Belgilansa, tovar do'kon sahifasi tepasidagi aylanadigan karuselda chiqadi",
		},
		{
			"fieldname": "carousel_label",
			"label": "Karusel yozuvi",
			"fieldtype": "Data",
			"insert_after": "in_carousel",
			"depends_on": "in_carousel",
			"description": "Ixtiyoriy, masalan: Yangi kolleksiya yoki −20% chegirma",
		},
		{
			"fieldname": "old_price",
			"label": "Eski narx (chegirmadan oldin)",
			"fieldtype": "Currency",
			"insert_after": "is_published",
			"description": "To'ldirilsa, sahifada chizilgan narx va −% belgisi chiqadi",
		},
		{
			"fieldname": "spec_line",
			"label": "Qisqa xususiyat (ro'yxat uchun)",
			"fieldtype": "Data",
			"insert_after": "old_price",
			"description": "Masalan: Laminat, 120×60 sm",
		},
		{
			"fieldname": "wholesale_price",
			"label": "Ulgurji narx",
			"fieldtype": "Currency",
			"insert_after": "spec_line",
			"description": "Bo'sh bo'lsa ulgurji narx yo'q",
		},
		{
			"fieldname": "wholesale_min_qty",
			"label": "Ulgurji: kamida (dona)",
			"fieldtype": "Int",
			"default": "10",
			"insert_after": "wholesale_price",
			"depends_on": "wholesale_price",
		},
		{
			"fieldname": "sb_gallery",
			"label": "Rasmlar",
			"fieldtype": "Section Break",
			"insert_after": "description",
		},
		{
			"fieldname": "gallery",
			"label": "Galereya",
			"fieldtype": "Table",
			"options": "Item Gallery",
			"insert_after": "sb_gallery",
			"description": "Birinchi rasm — asosiy. Yuklangan rasmlar avtomatik WebP'ga siqiladi.",
		},
		{
			"fieldname": "sb_fiscal",
			"label": "Fiskal (Payme/Click cheki uchun)",
			"fieldtype": "Section Break",
			"insert_after": "gallery",
			"collapsible": 0,
		},
		{
			"fieldname": "mxik_code",
			"label": "MXIK kodi",
			"fieldtype": "Data",
			"insert_after": "sb_fiscal",
			"description": "tasnif.soliq.uz dagi 17 xonali kod. Bo'sh qolsa, kategoriyadagi kod olinadi",
		},
		{
			"fieldname": "package_code",
			"label": "Qadoq kodi",
			"fieldtype": "Data",
			"insert_after": "mxik_code",
		},
	],
	"Item Price": [
		{**SHOP_FIELD, "insert_after": "item_code", "fetch_from": "item_code.shop", "read_only": 1},
	],
	"Warehouse": [
		{**SHOP_FIELD, "insert_after": "warehouse_name", "read_only": 1},
	],
	"Sales Order": [
		{**SHOP_FIELD, "insert_after": "customer", "in_list_view": 1},
		{
			"fieldname": "customer_phone",
			"label": "Mijoz telefoni",
			"fieldtype": "Data",
			"options": "Phone",
			"insert_after": "shop",
		},
		{
			"fieldname": "payment_method",
			"label": "To'lov turi",
			"fieldtype": "Select",
			"options": "\nPayme\nClick\nNaqd",
			"insert_after": "customer_phone",
		},
		{
			"fieldname": "payment_status",
			"label": "To'lov holati",
			"fieldtype": "Select",
			"options": "Kutilmoqda\nTo'langan\nBekor",
			"default": "Kutilmoqda",
			"insert_after": "payment_method",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "order_source",
			"label": "Manba",
			"fieldtype": "Select",
			"options": "\nInstagram\nTelegram\nWeb",
			"insert_after": "payment_status",
		},
	],
	"Delivery Note": [
		{**SHOP_FIELD, "insert_after": "customer"},
	],
	"Item Group": [
		{**SHOP_FIELD, "insert_after": "parent_item_group", "description": "Bo'sh bo'lsa, sotuvchilarga ko'rinmaydi"},
		{
			"fieldname": "mxik_code",
			"label": "MXIK kodi",
			"fieldtype": "Data",
			"insert_after": "shop",
			"description": "tasnif.soliq.uz dagi 17 xonali kod. Shu kategoriyadagi MXIK'siz tovarlarga o'zi qo'yiladi",
		},
		{
			"fieldname": "package_code",
			"label": "Qadoq kodi",
			"fieldtype": "Data",
			"insert_after": "mxik_code",
		},
	],
	"Customer": [
		{
			"fieldname": "mp_phone",
			"label": "Telefon (tasdiqlangan)",
			"fieldtype": "Data",
			"options": "Phone",
			"unique": 1,
			"search_index": 1,
			"read_only": 1,
			"insert_after": "customer_name",
			"description": "+998XXXXXXXXX. Mijoz shu raqam bilan Telegram kodi orqali kiradi",
		},
	],
}

# Rang namunasi (sotuvchi panelida va mahsulot sahifasida doiracha rangi)
CUSTOM_FIELDS["Item Attribute Value"] = [
	{"fieldname": "color_hex", "label": "Rang (HEX)", "fieldtype": "Color", "insert_after": "abbr", "in_list_view": 1},
]

# Platformadagi umumiy atributlar: har do'kon o'z "Rang"ini ochmasligi uchun bitta ro'yxat
COLOR_ATTR = "Rang"
SIZE_ATTR = "O'lcham"
COLORS = [
	("Oq", "OQ", "#F4F2EC"), ("Qora", "QOR", "#1F1F1F"), ("Bej", "BEJ", "#CDB89A"), ("Kulrang", "KUL", "#9A9A9A"),
	("Zaytun", "ZAY", "#7F9A86"), ("To'q ko'k", "TKK", "#2E3A55"), ("Ko'k", "KOK", "#4A7BD0"), ("Yashil", "YAS", "#3F8F5A"),
	("Qizil", "QIZ", "#C4372F"), ("Pushti", "PUS", "#E6A6B8"), ("Jigarrang", "JIG", "#7A4E33"), ("Sariq", "SAR", "#E8C547"),
]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]

CUSTOM_FIELDS["Sales Order"] += [
	{
		"fieldname": "delivery_method",
		"label": "Yetkazish usuli",
		"fieldtype": "Select",
		"options": "\nKuryer\nO'zim olaman",
		"insert_after": "order_source",
	},
	{
		"fieldname": "delivery_address",
		"label": "Manzil",
		"fieldtype": "Small Text",
		"insert_after": "delivery_method",
		"depends_on": "eval:doc.delivery_method=='Kuryer'",
	},
]

# Sotuvchi nima qila oladi. Qaysi do'kon ekanini User Permission cheklaydi.
SELLER_PERMISSIONS = {
	# O'z do'konini tahrirlaydi (logo, karusel, aloqa). Status, STIR, ombor — permlevel 1 (faqat ko'radi),
	# Payme/Click kalitlari — permlevel 2 (umuman ko'rmaydi)
	"Shop": ["read", "write"],
	# Faqat o'z do'konidan buyurtma qilgan mijozlar (permissions.customer_query)
	"Customer": ["read"],
	"Contact": ["read"],
	"Item": ["read", "write", "create"],
	"Item Price": ["read", "write", "create", "delete"],
	"Sales Order": ["read", "write"],
	"Delivery Note": ["read", "write", "create", "submit"],
	"Warehouse": ["read"],
	"Stock Reconciliation": ["read", "write", "create", "submit"],
	# Item va narx formalaridagi Link maydonlari uchun (faqat tanlash)
	"Price List": ["read"],
	"Brand": ["read"],
	"Item Attribute": ["read"],
	# O'z kategoriyalari: faqat o'z do'koninikini ko'radi (permissions.item_group_query)
	"Item Group": ["select", "read", "create", "write"],
	"Rang": ["read", "create"],
	"UOM": ["select"],
}


# permlevel > 0 dagi ruxsatlar: {doctype: {permlevel: [huquqlar]}}
SELLER_LEVEL_PERMISSIONS = {"Shop": {1: ["read"]}}
MANAGER_LEVEL_PERMISSIONS = {"Shop": {1: ["read", "write"], 2: ["read", "write"]}}


MANAGER_PERMISSIONS = {
	"Shop": ["read", "write", "create", "delete", "report", "export"],
	"Item": ["read", "write", "create", "report", "export"],
	"Item Price": ["read", "write", "create", "delete", "report"],
	"Item Group": ["read", "write", "create"],
	"Sales Order": ["read", "write", "create", "submit", "cancel", "report", "export"],
	"Delivery Note": ["read", "write", "create", "submit", "cancel", "report"],
	"Stock Reconciliation": ["read", "write", "create", "submit", "cancel"],
	"Warehouse": ["read", "report"],
	"Customer": ["read", "report"],
	"Price List": ["read"],
	"Brand": ["read", "write", "create"],
	"Item Attribute": ["read", "write", "create"],
	"UOM": ["read"],
	"User": ["read"],
}


def after_install():
	after_migrate()


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	setup_seller_role()
	setup_manager_role()
	# Strict: shop maydoni bo'sh yozuvlar ham sotuvchiga ko'rinmaydi
	frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 1)
	disable_perpetual_inventory()
	setup_variant_attributes()
	setup_uzs_currency()
	setup_seller_workspace()
	setup_admin_workspace()
	migrate_single_banner()
	setup_variant_fields()
	seed_colors()
	assign_item_groups_to_shops()
	# Tovar qo'shishda kichik dialog emas, to'liq (soddalashtirilgan) forma ochilsin
	if not frappe.db.exists("Property Setter", {"doc_type": "Item", "property": "quick_entry"}):
		make_property_setter("Item", None, "quick_entry", "0", "Check", for_doctype=True, validate_fields_for_doctype=False)


def setup_variant_attributes():
	if not frappe.db.exists("Item Attribute", COLOR_ATTR):
		attr = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": COLOR_ATTR})
		for name, abbr, hex_ in COLORS:
			attr.append("item_attribute_values", {"attribute_value": name, "abbr": abbr, "color_hex": hex_})
		attr.insert(ignore_permissions=True)
	if not frappe.db.exists("Item Attribute", SIZE_ATTR):
		attr = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": SIZE_ATTR})
		for size in SIZES:
			attr.append("item_attribute_values", {"attribute_value": size, "abbr": size})
		attr.insert(ignore_permissions=True)


def setup_uzs_currency():
	"""ERPNext'da UZS belgisi "лв" (bolgar levi) bo'lib keladi. So'm: 189 000 so‘m."""
	frappe.db.set_value(
		"Currency", "UZS",
		{"symbol": "so‘m", "symbol_on_right": 1, "number_format": "# ###.##", "smallest_currency_fraction_value": 1},
	)
	# So'mda tiyin amalda ishlatilmaydi: kasr qismini ko'rsatmaymiz
	frappe.db.set_single_value("System Settings", "currency_precision", "0")


def disable_perpetual_inventory():
	"""Do'konlar savdosi platforma kitoblariga yozilmaydi: ombor faqat qoldiqni yuritadi, GL yozuvi yo'q.

	Ombor harakati boshlangan Company'ga tegilmaydi — u yerda o'zgartirish hisobni buzadi.
	"""
	for company in frappe.get_all("Company", filters={"enable_perpetual_inventory": 1}, pluck="name"):
		if not frappe.db.exists("Stock Ledger Entry", {"company": company}):
			frappe.db.set_value("Company", company, "enable_perpetual_inventory", 0)


def setup_manager_role():
	if not frappe.db.exists("Role", MANAGER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": MANAGER_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	for doctype, rights in MANAGER_PERMISSIONS.items():
		add_permission(doctype, MANAGER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, MANAGER_ROLE, 0, right, 1, validate=False)
	set_level_permissions(MANAGER_ROLE, MANAGER_LEVEL_PERMISSIONS)


def setup_seller_role():
	if not frappe.db.exists("Role", SELLER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": SELLER_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	for doctype, rights in SELLER_PERMISSIONS.items():
		add_permission(doctype, SELLER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, SELLER_ROLE, 0, right, 1, validate=False)
	set_level_permissions(SELLER_ROLE, SELLER_LEVEL_PERMISSIONS)


def set_level_permissions(role, levels):
	for doctype, by_level in levels.items():
		for level, rights in by_level.items():
			add_permission(doctype, role, level)
			for right in rights:
				update_permission_property(doctype, role, level, right, 1, validate=False)


def migrate_single_banner():
	"""Eski bitta banner (banner_title/banner_image) karuselning birinchi slaydiga ko'chadi."""
	for shop in frappe.get_all("Shop", filters={"banner_image": ["is", "set"]}, pluck="name"):
		if frappe.db.exists("Shop Banner", {"parent": shop, "parenttype": "Shop"}):
			continue
		doc = frappe.get_doc("Shop", shop)
		doc.append(
			"banners",
			{"image": doc.banner_image, "label": doc.banner_label, "title": doc.banner_title, "item_group": doc.banner_group},
		)
		doc.flags.ignore_permissions = True
		doc.save()


# Variant yaratilganda andozadan (template) ko'chiriladigan maydonlar (ERPNext: Item Variant Settings)
VARIANT_COPY_FIELDS = (
	"shop", "is_published", "item_group", "mxik_code", "package_code", "old_price", "spec_line",
	"wholesale_price", "wholesale_min_qty", "variant_price", "description",
)


def setup_variant_fields():
	settings = frappe.get_single("Item Variant Settings")
	have = {d.field_name for d in settings.fields}
	missing = [f for f in VARIANT_COPY_FIELDS if f not in have]
	if missing:
		for f in missing:
			settings.append("fields", {"field_name": f})
		settings.flags.ignore_permissions = True
		settings.save()


def seed_colors():
	"""ERPNext "Rang" atributidagi mavjud qiymatlar Rang ro'yxatiga ko'chadi (bir marta)."""
	for v in frappe.get_all("Item Attribute Value", filters={"parent": COLOR_ATTR}, fields=["attribute_value", "color_hex"]):
		if not frappe.db.exists("Rang", v.attribute_value):
			frappe.get_doc({"doctype": "Rang", "rang_nomi": v.attribute_value, "hex": v.color_hex}).insert(ignore_permissions=True)


def assign_item_groups_to_shops():
	"""Hali do'konga bog'lanmagan kategoriyalar: faqat bitta do'kon tovarlari ishlatsa, o'sha do'konniki bo'ladi.
	Ota kategoriya (masalan Kiyim) — barcha bolalari bitta do'konniki bo'lsa, o'sha do'konga."""
	used = {}
	for r in frappe.get_all("Item", filters={"shop": ["is", "set"]}, fields=["item_group", "shop"]):
		used.setdefault(r.item_group, set()).add(r.shop)
	# Avval barglar (eng ichki kategoriyalar), keyin ularning otalari
	groups = sorted(
		frappe.get_all("Item Group", fields=["name", "lft", "rgt", "is_group", "shop"]), key=lambda g: g.rgt - g.lft
	)
	owner = {}
	for g in groups:
		shops = set(used.get(g.name, set()))
		if g.is_group:
			for child in groups:
				if g.lft < child.lft and child.rgt < g.rgt and owner.get(child.name):
					shops.add(owner[child.name])
		if len(shops) == 1 and g.lft != 1:
			owner[g.name] = shops.pop()
	for name, shop in owner.items():
		if not frappe.db.get_value("Item Group", name, "shop"):
			frappe.db.set_value("Item Group", name, "shop", shop, update_modified=False)
