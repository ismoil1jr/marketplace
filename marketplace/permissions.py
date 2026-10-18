"""Har bir yozuvga `shop` ni server o'zi qo'yadi.

Sotuvchi formadan yoki API orqali boshqa do'kon nomini yuborsa ham, shu yerda
o'zining do'koni bilan almashtiriladi. Ro'yxatlarni filtrlashni esa Frappe'ning
User Permission mexanizmi bajaradi (Shop a'zosi qo'shilganda yaratiladi).
"""

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname


def get_user_shop(user=None):
	"""Foydalanuvchi a'zo bo'lgan do'kon. Admin uchun — "Do'kon paneliga kirish" bilan tanlangan do'kon
	(faqat o'z sessiyasida, admin_view_shop), aks holda None (barcha do'konlar)."""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	roles = frappe.get_roles(user)
	if user == "Administrator" or "System Manager" in roles or "Marketplace Manager" in roles:
		return admin_view_shop() if user == frappe.session.user else None
	return frappe.db.get_value("Shop Member", {"user": user, "parenttype": "Shop"}, "parent")


def admin_view_shop():
	"""Admin hozir qaysi do'kon panelini ko'ryapti (sessiya ma'lumotida; fon vazifalariga ta'sir qilmaydi)."""
	session = getattr(frappe.local, "session", None)
	data = session.get("data") if session else None
	return (data or {}).get("mp_view_shop")


def shop_query(user=None, doctype=None):
	"""Do'konga bog'langan ro'yxatlar: sotuvchida User Permission bor, admin esa do'kon panelida bo'lsa
	faqat o'sha do'konni ko'radi."""
	shop = get_user_shop(user)
	if not shop or not doctype:
		return ""
	return "`tab{0}`.shop = {1}".format(doctype, frappe.db.escape(shop))


def item_query(user=None):
	return shop_query(user, "Item")


def sales_order_query(user=None):
	return shop_query(user, "Sales Order")


def delivery_note_query(user=None):
	return shop_query(user, "Delivery Note")


def item_price_query(user=None):
	return shop_query(user, "Item Price")


def set_shop(doc, method=None):
	shop = get_user_shop()
	if shop:
		doc.shop = shop
	elif not doc.get("shop") and doc.doctype == "Item Price":
		doc.shop = frappe.db.get_value("Item", doc.item_code, "shop")


def item_before_insert(doc, method=None):
	set_shop(doc)
	if not doc.shop:
		return
	# Item nomi butun saytda unikal: kodni do'kon slug'i bilan boshlaymiz,
	# shunda ikki do'kon bir xil "futbolka-01" kiritsa ham to'qnashmaydi.
	set_shop_warehouse(doc)
	prefix = f"{doc.shop}-"
	if not doc.item_code:
		# Kod nomdan yasaladi: "Kuzgi kurtka" -> nafis-tekstil-kuzgi-kurtka (band bo'lsa -2, -3 ...)
		doc.item_code = _unique_code(prefix + _slug(doc.item_name)) if _slug(doc.item_name) else make_autoname(f"{prefix}.#####")
	elif not doc.item_code.startswith(prefix):
		doc.item_code = prefix + doc.item_code


def _slug(text):
	text = (text or "").lower()
	for a, b in (("o‘", "o"), ("g‘", "g"), ("o'", "o"), ("g'", "g"), ("ʻ", ""), ("‘", ""), ("'", "")):
		text = text.replace(a, b)
	return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60]


def _unique_code(code):
	candidate, n = code, 1
	while frappe.db.exists("Item", candidate):
		n += 1
		candidate = f"{code}-{n}"
	return candidate


def item_group_before_insert(doc, method=None):
	"""Sotuvchi o'zi kategoriya qo'shadi: u faqat shu do'konga tegishli bo'ladi va boshqalarga ko'rinmaydi."""
	shop = get_user_shop()
	if not shop:
		return
	doc.shop = shop
	doc.is_group = 0
	doc.parent_item_group = frappe.db.get_value("Item Group", {"lft": 1}, "name") or "All Item Groups"
	name = (doc.item_group_name or "").strip()
	existing = frappe.db.get_value("Item Group", {"item_group_name": name}, ["name", "shop"], as_dict=True)
	if existing:
		if existing.shop == shop:
			frappe.throw(_("\"{0}\" kategoriyasi sizda allaqachon bor — ro'yxatdan tanlang").format(name))
		frappe.throw(_("\"{0}\" nomi boshqa do'konda band. Aniqroq nom bering (masalan, \"Ayollar kurtkasi\")").format(name))


def clean_mxik(code):
	"""Bo'shliq va chiziqchalarsiz 17 ta raqam (bo'sh bo'lsa bo'sh)."""
	code = re.sub(r"\D", "", code or "")
	if code and len(code) != 17:
		frappe.throw(_("MXIK kodi 17 ta raqamdan iborat (tasnif.soliq.uz)"))
	return code


def group_fiscal_codes(item_group):
	"""Kategoriya yoki uning eng yaqin ota kategoriyasidagi (MXIK, qadoq kodi)."""
	lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return "", ""
	row = frappe.get_all(
		"Item Group",
		filters={"lft": ["<=", lft], "rgt": [">=", rgt], "mxik_code": ["is", "set"]},
		fields=["mxik_code", "package_code"],
		order_by="lft desc",
		limit=1,
	)
	return (row[0].mxik_code, row[0].package_code or "") if row else ("", "")


def item_group_validate(doc, method=None):
	doc.mxik_code = clean_mxik(doc.get("mxik_code"))
	doc.package_code = (doc.get("package_code") or "").strip()


def item_group_on_update(doc, method=None):
	"""Kategoriyaga MXIK yozilganda, shu kategoriyadagi MXIK'siz tovarlar ham to'ldiriladi."""
	if not doc.mxik_code:
		return
	for name in frappe.get_all("Item", filters={"item_group": doc.name, "mxik_code": ["is", "not set"]}, pluck="name"):
		frappe.db.set_value(
			"Item", name, {"mxik_code": doc.mxik_code, "package_code": doc.package_code or None}, update_modified=False
		)


def item_group_query(user=None):
	"""Sotuvchi faqat o'z do'koni kategoriyalarini (va daraxt ildizini) ko'radi."""
	shop = get_user_shop(user)
	if not shop:
		return ""
	return "(`tabItem Group`.shop = {0} or `tabItem Group`.lft = 1)".format(frappe.db.escape(shop))


def item_group_has_permission(doc, ptype=None, user=None):
	shop = get_user_shop(user)
	if not shop:
		return True
	if ptype in ("read", "select") and doc.lft == 1:
		return True
	return doc.get("shop") == shop or doc.is_new()


def set_shop_warehouse(doc):
	"""Tovar qoldig'i (opening_stock) do'konning o'z omboriga yozilsin."""
	warehouse, company = frappe.db.get_value("Shop", doc.shop, "warehouse"), None
	if warehouse:
		company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not company:
		return
	doc.set("item_defaults", [d for d in doc.get("item_defaults") or [] if d.company != company])
	doc.append("item_defaults", {"company": company, "default_warehouse": warehouse})
	if doc.opening_stock and doc.valuation_rate is None:
		doc.valuation_rate = 0


def item_validate(doc, method=None):
	shop = get_user_shop()
	if shop and doc.item_group and frappe.db.get_value("Item Group", doc.item_group, "shop") not in (shop, None, ""):
		frappe.throw(_("Bu kategoriya boshqa do'konniki. O'z kategoriyangizni tanlang"))
	doc.mxik_code = clean_mxik(doc.mxik_code)
	if not doc.mxik_code and doc.item_group:
		doc.mxik_code, group_package = group_fiscal_codes(doc.item_group)
		doc.package_code = doc.package_code or group_package
	if doc.shop and doc.is_published and not doc.mxik_code:
		frappe.throw(_("Saytda ko'rsatiladigan tovar uchun MXIK kodi majburiy (fiskal chek uchun)"))


def customer_query(user=None):
	"""Sotuvchi faqat o'z do'konidan buyurtma qilgan mijozlarni ko'radi."""
	shop = get_user_shop(user)
	if not shop:
		return ""
	return (
		"`tabCustomer`.name in (select so.customer from `tabSales Order` so where so.shop = {0})"
	).format(frappe.db.escape(shop))


def customer_has_permission(doc, ptype=None, user=None):
	shop = get_user_shop(user)
	if not shop:
		return True  # admin: standart qoidalar (hook faqat taqiqlay oladi)
	return bool(frappe.db.exists("Sales Order", {"shop": shop, "customer": doc.name}))


def contact_query(user=None):
	shop = get_user_shop(user)
	if not shop:
		return ""
	return (
		"`tabContact`.name in (select dl.parent from `tabDynamic Link` dl where dl.parenttype = 'Contact'"
		" and dl.link_doctype = 'Customer' and dl.link_name in"
		" (select so.customer from `tabSales Order` so where so.shop = {0}))"
	).format(frappe.db.escape(shop))


def contact_has_permission(doc, ptype=None, user=None):
	shop = get_user_shop(user)
	if not shop:
		return True
	customers = [d.link_name for d in doc.get("links") or [] if d.link_doctype == "Customer"]
	return bool(customers) and bool(
		frappe.db.exists("Sales Order", {"shop": shop, "customer": ["in", customers]})
	)
