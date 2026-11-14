"""Har bir yozuvga `shop` ni server o'zi qo'yadi.

Sotuvchi formadan yoki API orqali boshqa do'kon nomini yuborsa ham, shu yerda
o'zining do'koni bilan almashtiriladi. Ro'yxatlarni filtrlashni esa Frappe'ning
User Permission mexanizmi bajaradi (Shop a'zosi qo'shilganda yaratiladi).
"""

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint


def is_admin(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool({"System Manager", "Marketplace Manager"} & set(frappe.get_roles(user)))


def get_user_shop(user=None):
	"""Foydalanuvchi a'zo bo'lgan do'kon. Admin uchun — "Do'kon paneliga kirish" bilan tanlangan do'kon
	(faqat o'z sessiyasida, admin_view_shop), aks holda None (barcha do'konlar)."""
	user = user or frappe.session.user
	if user == "Guest":
		return None
	if is_admin(user):
		return admin_view_shop() if user == frappe.session.user else None
	return frappe.db.get_value("Shop Member", {"user": user, "parenttype": "Shop"}, "parent")


# Yopiq tizim: admin bo'lmagan foydalanuvchining do'koni bo'lmasa (masalan User formasida qo'lda rol berilgan,
# lekin do'kon a'zolariga qo'shilmagan) — hech narsa ko'rinmaydi. Aks holda filtr umuman qo'yilmasdi va u
# barcha do'konlar ma'lumotini ko'rardi (User Permission ham faqat a'zoga yaratiladi).
NOTHING = "1=0"


def _no_shop_access(user=None):
	"""Admin emas va hech qaysi do'konga biriktirilmagan."""
	user = user or frappe.session.user
	return user != "Guest" and not is_admin(user) and not get_user_shop(user)


def shop_doc_has_permission(doc, ptype=None, user=None):
	"""`shop` maydoni bor yozuvlar (has_permission): do'kon a'zosi — faqat o'z do'koniniki; a'zo bo'lmagan — hech biri.
	Admin — standart qoidalar (hook faqat taqiqlay oladi)."""
	user = user or frappe.session.user
	if is_admin(user):
		return True
	shop = get_user_shop(user)
	if not shop:
		return False
	return doc.is_new() or doc.get("shop") == shop


def admin_view_shop():
	"""Admin hozir qaysi do'kon panelini ko'ryapti (sessiya ma'lumotida; fon vazifalariga ta'sir qilmaydi)."""
	session = getattr(frappe.local, "session", None)
	data = session.get("data") if session else None
	return (data or {}).get("mp_view_shop")


def member_shop(user=None):
	"""A'zo bo'lgan do'kon — admin roli bo'lsa ham (masalan QA akkaunti: Marketplace Manager + do'kon xodimi)."""
	return frappe.db.get_value("Shop Member", {"user": user or frappe.session.user, "parenttype": "Shop"}, "parent")


def shop_query(user=None, doctype=None):
	"""Do'konga bog'langan ro'yxatlar: sotuvchida User Permission bor, admin esa do'kon panelida bo'lsa
	faqat o'sha do'konni ko'radi."""
	if _no_shop_access(user):
		return NOTHING
	shop = get_user_shop(user)
	if not shop or not doctype:
		return ""
	return "`tab{0}`.shop = {1}".format(doctype, frappe.db.escape(shop))


def shop_list_query(user=None):
	"""Shop ro'yxati: admin — hammasi, a'zo — faqat o'z do'koni, a'zo bo'lmagan — hech biri."""
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	shop = get_user_shop(user)
	return "`tabShop`.name = {0}".format(frappe.db.escape(shop)) if shop else NOTHING


def shop_has_permission(doc, ptype=None, user=None):
	"""Do'kon kartasi ("Do'kon sozlamalari"): a'zo — faqat o'z do'koni, admin — hammasi."""
	user = user or frappe.session.user
	return is_admin(user) or doc.name == get_user_shop(user)


# Frappe "Desk User" roliga User bo'yicha "Select" beradi — u bilan User ro'yxati ham ochiladi va sotuvchi
# boshqa do'konlar a'zolarini, adminlarni ko'rardi. Do'kon a'zosi faqat o'z do'koni a'zolarini ko'radi
# (kuryer, menejer tanlash uchun shu yetarli), a'zo bo'lmagan (admin emas) — faqat o'zini.
def user_query(user=None):
	user = user or frappe.session.user
	if is_admin(user):
		return ""
	shop = get_user_shop(user)
	if not shop:
		return "`tabUser`.name = {0}".format(frappe.db.escape(user))
	return "`tabUser`.name in (select m.user from `tabShop Member` m where m.parenttype = 'Shop' and m.parent = {0})".format(
		frappe.db.escape(shop)
	)


def user_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if is_admin(user) or doc.name == user:
		return True
	shop = get_user_shop(user)
	return bool(shop) and bool(frappe.db.exists("Shop Member", {"parenttype": "Shop", "parent": shop, "user": doc.name}))


def item_query(user=None):
	return shop_query(user, "Item")


def kontragent_query(user=None):
	return shop_query(user, "Kontragent")


def telegram_mijoz_query(user=None):
	return shop_query(user, "Telegram Mijoz")


# Bu ro'yxatlarda sotuvchini User Permission cheklaydi, lekin admin "Do'kon paneli"da ham faqat o'sha do'kon ko'rinsin
def doimiy_mijoz_query(user=None):
	return shop_query(user, "Doimiy Mijoz")


def olcham_query(user=None):
	return shop_query(user, "Olcham")


def telefon_qongiroq_query(user=None):
	"""Do'kon qo'ng'iroqlari; notanish raqamli (24 soat kutayotgan) qo'ng'iroq — faqat uni qilgan menejerga."""
	cond = shop_query(user, "Telefon Qongiroq")
	if cond == NOTHING:
		return cond
	own = "(`tabTelefon Qongiroq`.notanish = 0 or `tabTelefon Qongiroq`.menejer = {0})".format(
		frappe.db.escape(user or frappe.session.user)
	)
	return f"{cond} and {own}" if cond else own


def telefon_qongiroq_has_permission(doc, ptype=None, user=None):
	if cint(doc.get("notanish")) and doc.get("menejer") != (user or frappe.session.user):
		return False
	return shop_doc_has_permission(doc, ptype, user)


def menejer_xulosasi_query(user=None):
	return shop_query(user, "Menejer Xulosasi")


def murojaat_query(user=None):
	return shop_query(user, "Murojaat")


def majburiy_tasdiq_query(user=None):
	return shop_query(user, "Majburiy Tasdiq")


def rang_query(user=None):
	return shop_query(user, "Rang")


def warehouse_query(user=None):
	"""Omborlar: do'kon a'zosi (va do'kon panelidagi admin) faqat o'z do'koni omborini ko'radi.
	User Permission bunga yetmaydi: ERPNext'ning Item Default/Item Group "Default Warehouse" maydonlari
	ignore_user_permissions bilan qidiradi va boshqa do'konlar omborlari ham chiqardi."""
	if _no_shop_access(user):
		return NOTHING
	shop = get_user_shop(user)
	if not shop:
		return ""
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	return "`tabWarehouse`.name = {0}".format(frappe.db.escape(warehouse)) if warehouse else NOTHING


def is_courier(user=None):
	"""Faqat kuryer (do'kon egasi/xodimi yoki admin emas)."""
	from marketplace.setup import COURIER_ROLE, SELLER_ROLE

	roles = set(frappe.get_roles(user or frappe.session.user))
	return COURIER_ROLE in roles and not roles & {SELLER_ROLE, "System Manager", "Marketplace Manager"}


def is_packer(user=None):
	"""Faqat upakovkachi (do'kon egasi/xodimi yoki admin emas) — Desk'da Upakovka sahifasi."""
	from marketplace.setup import PACKER_ROLE, SELLER_ROLE

	roles = set(frappe.get_roles(user or frappe.session.user))
	return PACKER_ROLE in roles and not roles & {SELLER_ROLE, "System Manager", "Marketplace Manager"}


PAID_STATUS = "To'langan"
# frappe.get_list(or_filters=...) uchun: kuryer/upakovkaga chiqqan buyurtma (courier_ready bilan bir xil)
COURIER_READY_OR = [["mp_aloqa_natija", "=", "Oladi"], ["payment_status", "=", PAID_STATUS]]


def courier_ready(so):
	"""Kuryer bilan yetkaziladigan buyurtma kuryer va upakovkachiga chiqadimi: menejer mijoz bilan gaplashib «Oladi»
	degan yoki mijoz onlayn oldindan to'lagan (to'lovning o'zi tasdiq — qo'ng'iroq kutilmaydi)."""
	return so.get("mp_aloqa_natija") == "Oladi" or so.get("payment_status") == PAID_STATUS


def is_supervisor(user=None):
	"""Faqat sotuv nazoratchisi (do'kon egasi/xodimi yoki admin emas) — Desk'da Sotuv nazorati sahifasi."""
	from marketplace.setup import SELLER_ROLE, SUPERVISOR_ROLE

	roles = set(frappe.get_roles(user or frappe.session.user))
	return SUPERVISOR_ROLE in roles and not roles & {SELLER_ROLE, "System Manager", "Marketplace Manager"}


def sales_order_query(user=None):
	"""Saytdagi buyurtma mijoz naqdni tanlamaguncha yoki to'lamaguncha do'konga ko'rinmaydi (orders.confirm_order).
	Kuryer — faqat kuryer bilan yetkaziladiganlar: hali hech kim olmagan yoki o'zi yetkazganlari."""
	user = user or frappe.session.user
	cond = shop_query(user, "Sales Order")
	if not cond:
		return ""
	cond += " and ifnull(`tabSales Order`.mp_placed, 1) = 1"
	if is_courier(user):
		# Kuryer — menejer "Oladi" deb tasdiqlagan yoki onlayn to'langan yetkazishlar (courier_ready)
		# va o'zi topshirganlari (tarix)
		cond += (
			" and `tabSales Order`.delivery_method = 'Kuryer'"
			" and (ifnull(`tabSales Order`.mp_courier, '') = {0}"
			" or (ifnull(`tabSales Order`.mp_courier, '') = ''"
			" and (`tabSales Order`.mp_aloqa_natija = 'Oladi' or `tabSales Order`.payment_status = {1})))"
		).format(frappe.db.escape(user), frappe.db.escape(PAID_STATUS))
	return cond


def sales_order_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not shop_doc_has_permission(doc, ptype, user):
		return False
	if not is_courier(user):
		return True
	if doc.get("delivery_method") != "Kuryer":
		return False
	if doc.get("mp_courier") == user:
		return True
	return not doc.get("mp_courier") and courier_ready(doc)


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
	# Yangi kategoriya — oxirgi kategoriya (tovar shunga biriktiriladi). Ichiga kategoriya qo'shilganda
	# papkaga aylanadi (add_category). ERPNext tovarni faqat papka bo'lmaganiga biriktiradi
	doc.is_group = 0
	# Ichma-ich kategoriya (Telefonlar → Xiaomi) faqat o'z do'konining papkasi ichida; aks holda — ildizga
	root = frappe.db.get_value("Item Group", {"lft": 1}, "name") or "All Item Groups"
	parent = doc.parent_item_group and frappe.db.get_value(
		"Item Group", doc.parent_item_group, ["shop", "is_group"], as_dict=True
	)
	if not (parent and parent.shop == shop and parent.is_group):
		doc.parent_item_group = root
	elif category_depth(doc.parent_item_group) >= MAX_CATEGORY_DEPTH:
		frappe.throw(_("Kategoriya ko'pi bilan {0} qavat bo'ladi (masalan: Kiyim › Kurtka › Zara)").format(MAX_CATEGORY_DEPTH))
	name = doc.mp_title = (doc.get("mp_title") or doc.item_group_name or "").strip()
	if frappe.db.exists("Item Group", {"mp_title": name, "shop": shop}) or frappe.db.exists("Item Group", {"item_group_name": name, "shop": shop}):
		frappe.throw(_("\"{0}\" kategoriyasi sizda allaqachon bor — ro'yxatdan tanlang").format(name))
	# Kategoriya ID'si butun tizimda bitta (ERPNext, item_group_name = ID), nomi (mp_title) esa har do'konda erkin:
	# boshqa do'konda "Kiyimlar" bo'lsa, bu do'konniki ID'da do'kon bilan ajratiladi — "Kiyimlar (clothes)".
	# Daraxt, tovar formasi, sayt, ombor va hisobotda nomi ko'rinadi (title_field, group_title)
	new = name
	if frappe.db.exists("Item Group", new):
		base = new = f"{name} ({shop})"
		n = 1
		while frappe.db.exists("Item Group", new):
			n += 1
			new = f"{base} {n}"
	doc.item_group_name = doc.name = new
	doc.flags.name_set = True


def group_title(name):
	"""Kategoriya ID'si -> ko'rinadigan nomi ("Kiyimlar (clothes)" -> "Kiyimlar"). So'rov davomida eslab qolinadi."""
	if not name:
		return name
	cache = getattr(frappe.local, "mp_group_titles", None)
	if cache is None:
		cache = frappe.local.mp_group_titles = {}
	if name not in cache:
		row = frappe.db.get_value("Item Group", name, ["mp_title", "item_group_name"], as_dict=True) or {}
		cache[name] = row.get("mp_title") or row.get("item_group_name") or name
	return cache[name]


MAX_CATEGORY_DEPTH = 3


def category_depth(name):
	"""Do'kon kategoriyasining qavati: bosh kategoriya — 1, uning ichidagisi — 2... Ildiz — 0."""
	lft, rgt = frappe.db.get_value("Item Group", name, ["lft", "rgt"]) or (None, None)
	if lft is None:
		return 0
	return frappe.db.count("Item Group", {"lft": ["<=", lft], "rgt": [">=", rgt], "shop": ["is", "set"]})


def _is_top_category(doc):
	return not frappe.db.get_value("Item Group", doc.parent_item_group, "shop") if doc.parent_item_group else True


@frappe.whitelist(methods=["POST"])
def add_category(parent: str, name: str, mxik_code: str | None = None, package_code: str | None = None,
                 items_to: str | None = None):
	"""Do'konchi daraxtida "+ Ichiga kategoriya": bosh kategoriya (parent — ildiz) yoki ichki kategoriya.
	MXIK faqat bosh kategoriyaga yoziladi, ichkilari undan oladi. Oxirgi kategoriya ichiga qo'shilsa — u papkaga
	aylanadi. Unda tovar bo'lsa (ERPNext papkada tovar saqlamaydi), tovarlar items_to'ga yoki yangi kategoriyaga o'tadi."""
	shop = get_user_shop()
	if not shop:
		frappe.throw(_("Avval do'kon panelida bo'ling"), frappe.PermissionError)
	root = frappe.db.get_value("Item Group", {"lft": 1}, "name")
	move = []
	if parent != root:
		owner, is_group = frappe.db.get_value("Item Group", parent, ["shop", "is_group"]) or (None, 0)
		if owner != shop:
			frappe.throw(_("Bu kategoriya sizning do'koningizniki emas"), frappe.PermissionError)
		if category_depth(parent) >= MAX_CATEGORY_DEPTH:
			frappe.throw(_("Kategoriya ko'pi bilan {0} qavat bo'ladi (masalan: Kiyim › Kurtka › Zara)").format(MAX_CATEGORY_DEPTH))
		if not is_group:
			move = frappe.get_all("Item", filters={"item_group": parent}, pluck="name")  # variantlari bilan
			if move and items_to:
				target = frappe.db.get_value("Item Group", items_to, ["shop", "is_group"], as_dict=True)
				if not target or target.shop != shop or target.is_group or items_to == parent:
					frappe.throw(_("Tovarlarni o'z do'koningizning oxirgi kategoriyasiga o'tkazing (papkaga emas)"))
			# Papkaga aylantiramiz (tovarlar pastda ko'chiriladi — hammasi bitta tranzaksiyada)
			frappe.db.set_value("Item Group", parent, "is_group", 1)
	doc = frappe.get_doc(
		{"doctype": "Item Group", "item_group_name": (name or "").strip(), "parent_item_group": parent, "is_group": 0,
		 "mxik_code": mxik_code if parent == root else None, "package_code": package_code if parent == root else None}
	)
	doc.insert()
	if move:
		target = items_to or doc.name
		mxik, package = group_fiscal_codes(target)
		values = {"item_group": target, **({"mxik_code": mxik, "package_code": package or None} if mxik else {})}
		for item in move:
			frappe.db.set_value("Item", item, values, update_modified=False)
		from marketplace.storefront import _cache_key

		frappe.cache.delete_value(_cache_key(shop))
	# Xabarda — tovarlar soni (variantlarsiz): "1 ta tovar o'tdi", "4 ta" emas
	moved = frappe.db.count("Item", {"name": ["in", move], "variant_of": ["is", "not set"]}) if move else 0
	return {"name": doc.name, "moved": moved or len(move), "moved_to": (items_to or doc.name) if move else None}


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


@frappe.whitelist()
def category_codes(name: str):
	"""Kategoriya formasi: ichki kategoriya qaysi MXIK / qadoq kodidan foydalanadi (eng yaqin kodli ajdod)."""
	if not frappe.has_permission("Item Group", "read", name):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	return group_fiscal_codes(name)


def item_group_validate(doc, method=None):
	"""Do'kon kategoriyasi: MXIK va qadoq kodi faqat BOSH kategoriyada majburiy — ichkilari (Telefonlar › Xiaomi)
	va ulardagi tovarlar uni bosh kategoriyadan oladi (group_fiscal_codes)."""
	doc.mxik_code = clean_mxik(doc.get("mxik_code"))
	doc.package_code = re.sub(r"\s", "", doc.get("package_code") or "")
	if not doc.is_new() and cint(doc.is_group) and doc.has_value_changed("is_group"):
		items = frappe.db.count("Item", {"item_group": doc.name, "variant_of": ["is", "not set"]}) or frappe.db.count("Item", {"item_group": doc.name})
		if items:
			frappe.throw(_("«{0}» da {1} ta tovar bor: papkaga aylantirib bo'lmaydi").format(doc.name, items))
	need = doc.get("shop") and _is_top_category(doc)
	if need and not doc.mxik_code:
		frappe.throw(_("Kategoriyaga MXIK kodini yozing (tasnif.soliq.uz) — tovarlar uni shu yerdan oladi"))
	if need and not doc.package_code:
		frappe.throw(_("Kategoriyaga qadoq kodini yozing (tasnif.soliq.uz da MXIK kodi ichida) — soliq chekida majburiy"))


def item_group_on_update(doc, method=None):
	"""Kategoriya kodi o'zgarsa, shu kategoriya va uning ichidagi barcha kategoriyalardagi tovarlar (variantlari ham)
	yangilanadi — har biri o'ziga eng yaqin kodni oladi."""
	if not (doc.has_value_changed("mxik_code") or doc.has_value_changed("package_code")):
		return
	for leaf in frappe.get_all("Item Group", filters={"lft": [">=", doc.lft], "rgt": ["<=", doc.rgt]}, pluck="name"):
		mxik, package = group_fiscal_codes(leaf)
		if not mxik:
			continue
		for name in frappe.get_all("Item", filters={"item_group": leaf}, pluck="name"):
			frappe.db.set_value("Item", name, {"mxik_code": mxik, "package_code": package or None}, update_modified=False)


def item_group_query(user=None):
	"""Sotuvchi faqat o'z do'koni kategoriyalarini (va daraxt ildizini) ko'radi."""
	if _no_shop_access(user):
		return "`tabItem Group`.lft = 1"
	shop = get_user_shop(user)
	if not shop:
		return ""
	return "(`tabItem Group`.shop = {0} or `tabItem Group`.lft = 1)".format(frappe.db.escape(shop))


@frappe.whitelist()
def item_group_tree(doctype: str, parent: str = "", include_disabled=False, **filters):
	"""Do'konchining "Kategoriyalar" daraxti (item_group_seller.js: get_tree_nodes). Ildiz "All Item Groups" hech
	qaysi do'konniki emas, shuning uchun qat'iy ruxsatda (apply_strict_user_permissions) do'konchiga ko'rinmaydi
	va butun daraxt bo'sh chiqadi. Ildizni shu yerda beramiz; ichidagilar odatdagidek — faqat o'z do'koniniki."""
	from frappe.desk.treeview import get_children

	if doctype == "Item Group" and not parent and get_user_shop():
		root = frappe.db.get_value("Item Group", {"lft": 1}, ["name", "mp_title", "item_group_name"], as_dict=True)
		return [{"value": root.name, "title": root.mp_title or root.item_group_name, "expandable": 1, "depth": 0}]
	nodes = get_children(doctype, parent, include_disabled, **filters)
	if doctype == "Item Group" and get_user_shop():
		# Daraxtda: qavati ("+ Ichiga qo'shish" 3-qavatgacha) va nechta tovari borligi
		depth = category_depth(parent) + 1 if parent else 1
		counts = dict(frappe.get_all("Item", filters={"item_group": ["in", [n.value for n in nodes] or [""]], "variant_of": ["is", "not set"]},
			fields=["item_group", {"COUNT": "*", "as": "n"}], group_by="item_group", as_list=True))
		for n in nodes:
			n["depth"] = depth
			n["items"] = counts.get(n.value, 0)
	return nodes


def item_group_has_permission(doc, ptype=None, user=None):
	if _no_shop_access(user):
		return ptype in ("read", "select") and doc.lft == 1
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
	# MXIK va qadoq kodi — kategoriyadan (kategoriyada yo'q bo'lsa, admin qo'ygan eski kod qoladi)
	group_mxik, group_package = group_fiscal_codes(doc.item_group) if doc.item_group else ("", "")
	if group_mxik:
		doc.mxik_code, doc.package_code = group_mxik, group_package or doc.package_code
	doc.mxik_code = clean_mxik(doc.mxik_code)
	if doc.shop and doc.is_published and not doc.mxik_code:
		frappe.throw(
			_("\"{0}\" kategoriyasiga MXIK kodi yozilmagan. Kategoriyani ochib, MXIK va qadoq kodini kiriting").format(
				doc.item_group
			)
		)


def customer_query(user=None):
	"""Sotuvchi faqat o'z do'konidan buyurtma qilgan mijozlarni ko'radi."""
	if _no_shop_access(user):
		return NOTHING
	shop = get_user_shop(user)
	if not shop:
		return ""
	return (
		"`tabCustomer`.name in (select so.customer from `tabSales Order` so where so.shop = {0})"
	).format(frappe.db.escape(shop))


def customer_has_permission(doc, ptype=None, user=None):
	if _no_shop_access(user):
		return False
	shop = get_user_shop(user)
	if not shop:
		return True  # admin: standart qoidalar (hook faqat taqiqlay oladi)
	return bool(frappe.db.exists("Sales Order", {"shop": shop, "customer": doc.name}))


def contact_query(user=None):
	if _no_shop_access(user):
		return NOTHING
	shop = get_user_shop(user)
	if not shop:
		return ""
	return (
		"`tabContact`.name in (select dl.parent from `tabDynamic Link` dl where dl.parenttype = 'Contact'"
		" and dl.link_doctype = 'Customer' and dl.link_name in"
		" (select so.customer from `tabSales Order` so where so.shop = {0}))"
	).format(frappe.db.escape(shop))


def contact_has_permission(doc, ptype=None, user=None):
	if _no_shop_access(user):
		return False
	shop = get_user_shop(user)
	if not shop:
		return True
	customers = [d.link_name for d in doc.get("links") or [] if d.link_doctype == "Customer"]
	return bool(customers) and bool(
		frappe.db.exists("Sales Order", {"shop": shop, "customer": ["in", customers]})
	)


def require_roles(*roles):
	"""Whitelisted funksiya boshida: foydalanuvchida shu rollardan biri bo'lsin (admin har doim o'tadi).
	Sahifa rollari (Page.roles) bilan bir xil bo'lsin — aks holda menyuda ko'rinmagan sahifa API orqali ochiq qoladi
	(masalan, kuryer upakovka belgisini qo'ya olar edi)."""
	if is_admin():
		return
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(_("Bu bo'lim sizning rolingiz uchun emas"), frappe.PermissionError)
