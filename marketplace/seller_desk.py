"""Sotuvchining oddiy ERPNext Desk'dagi joyi.

* Desktop'da faqat o'z do'koni ikonkasi (nomi va logosi bilan) chiqadi, ERPNext ikonkasi yashiriladi.
* Ikonka "Do'konim" workspace'ini ochadi: balans kartalari va tovar qo'shish, buyurtmalar tugmalari.
* Workspace va kartalar hamma sotuvchiga bitta. Har kim faqat o'z do'koni raqamlarini ko'radi,
  chunki kartalar va ro'yxatlar User Permission (Shop / Warehouse) bilan filtrlanadi.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from marketplace.permissions import get_user_shop

WORKSPACE = "Dokonim"
SELLER_ROLE = "Shop Seller"

# Workspace'dagi raqamli kartalar: (nom, doctype, funksiya, maydon, filtrlar, rang)
NUMBER_CARDS = [
	("Do'kon: To'langan summa", "Sales Order", "Sum", "grand_total",
		[["docstatus", "=", 1], ["payment_status", "=", "To'langan"]], "#16a34a"),
	("Do'kon: To'lov kutilmoqda", "Sales Order", "Count", None,
		[["docstatus", "=", 1], ["payment_status", "=", "Kutilmoqda"]], "#d97706"),
	("Do'kon: Bekor qilingan", "Sales Order", "Count", None,
		[["payment_status", "=", "Bekor"]], "#dc2626"),
	("Do'kon: Tovarlar", "Item", "Count", None,
		[["disabled", "=", 0], ["variant_of", "is", "not set"]], "#2563eb"),
]


def boot_session(bootinfo):
	"""Desktop va do'kon paneli (load_desktop_data'dan keyin ishlaydi).

	* Sotuvchi: Desktop'da faqat o'z do'koni ikonkasi.
	* Admin: "Marketplace" (hisobotlar) va "Do'konlar" (do'konlar paneli) ikonkalari. "Do'kon paneliga
	  kirish"dan keyin esa sotuvchi panelini o'sha do'kon bo'yicha ko'radi (admin_view).
	"""
	from marketplace.permissions import admin_view_shop

	is_seller = SELLER_ROLE in frappe.get_roles() and not ({"System Manager", "Marketplace Manager"} & set(frappe.get_roles()))
	is_seller = is_seller and frappe.session.user != "Administrator"
	shop = get_user_shop()
	if not is_seller:
		add_shops_tile(bootinfo)
		if not shop:
			hide_seller_shell(bootinfo)
			return
	elif not shop:
		return

	shop = frappe.get_cached_doc("Shop", shop)
	bootinfo.marketplace_shop = {
		"name": shop.name,
		"shop_name": shop.shop_name,
		"url": f"/s/{shop.name}",
		# Tovar formasi do'kon shabloniga moslanadi (item_seller.js): vitrina / story / katalog
		"layout": shop.layout_style or "vitrina",
		"admin_view": int(not is_seller and bool(admin_view_shop())),
	}
	if not is_seller:
		return

	# Workspace hali yaratilmagan bo'lsa (migrate qilinmagan), ikonkani o'zgartirmaymiz
	if not frappe.db.exists("Workspace", WORKSPACE):
		return
	for app in bootinfo.get("app_data") or []:
		if app.get("app_name") == "marketplace":
			app.update(
				app_title=shop.shop_name,
				app_logo_url=shop.logo or app.get("app_logo_url"),
				app_route=f"/desk/{frappe.scrub(WORKSPACE).replace('_', '-')}",
				on_apps_screen=True,
			)
		else:
			# ERPNext va boshqa ilovalar ikonkasi sotuvchiga kerak emas
			app["on_apps_screen"] = False


def add_shops_tile(bootinfo):
	"""Admin Desktop'ida Marketplace yonida ikkinchi ikonka: "Do'konlar" -> do'konlar paneli."""
	apps = bootinfo.get("app_data") or []
	base = next((a for a in apps if a.get("app_name") == "marketplace" and a.get("on_apps_screen")), None)
	if not base or any(a.get("app_name") == "marketplace-shops" for a in apps):
		return
	apps.append(
		{
			**base,
			"app_name": "marketplace-shops",
			"app_title": "Do'konlar",
			"app_route": "/desk/shops-overview",
			"sequence_id": (base.get("sequence_id") or 100) + 0.5,
			"dock": [],
		}
	)


def hide_seller_shell(bootinfo):
	"""Admin (Administrator'da hamma rollar bor) "Do'konim"ni ko'rmasin: unga Marketplace yetarli."""
	(bootinfo.get("module_sidebars") or {}).pop("Dokon", None)
	workspaces = bootinfo.get("workspaces") or {}
	if workspaces.get("pages"):
		workspaces["pages"] = [p for p in workspaces["pages"] if p.get("name") != WORKSPACE]


@frappe.whitelist()
def set_item_stock(item_code: str, qty: float):
	"""Tovar qoldig'ini yangi songa tenglaydi (ERPNext Stock Reconciliation orqali, do'kon omboriga)."""
	if not frappe.has_permission("Item", "write", item_code):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	qty = flt(qty)
	if qty < 0:
		frappe.throw(_("Soni manfiy bo'lishi mumkin emas"))

	item = frappe.get_doc("Item", item_code)
	if item.has_variants:
		frappe.throw(_("Variantli tovarda qoldiq har bir variantga (rang/o'lcham) alohida kiritiladi"))
	if not item.is_stock_item:
		frappe.throw(_("Bu tovar omborda hisoblanmaydi"))
	warehouse = frappe.db.get_value("Shop", item.shop, "warehouse")
	if not warehouse:
		frappe.throw(_("Do'kon ombori topilmadi"))

	current = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))
	if current == qty:
		return {"qty": qty, "changed": False}

	company = frappe.db.get_value("Warehouse", warehouse, "company")
	reco = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"company": company,
			"purpose": "Stock Reconciliation",
			"items": [
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"qty": qty,
					"valuation_rate": flt(item.valuation_rate),
					"allow_zero_valuation_rate": 1,
				}
			],
		}
	)
	if not frappe.db.exists("Stock Ledger Entry", {"item_code": item_code, "is_cancelled": 0}):
		reco.purpose = "Opening Stock"
		reco.expense_account = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Temporary", "is_group": 0}
		)
	reco.insert()
	reco.submit()
	return {"qty": qty, "changed": True, "reconciliation": reco.name}


def notify_new_order(doc, method=None):
	"""Sales Order submit bo'lganda do'kon a'zolariga xabar."""
	if doc.get("shop"):
		amount = frappe.utils.fmt_money(doc.grand_total, currency=doc.currency)
		notify_shop(doc, _("Yangi buyurtma {0}: {1} — {2}").format(doc.name, doc.customer_name, amount))


def notify_shop(doc, subject):
	"""Do'kon a'zolariga: qo'ng'iroqcha (Notification Log) + ochiq Desk'da ovoz va ekrandagi xabar."""
	users = set(frappe.get_all("Shop Member", filters={"parent": doc.shop, "parenttype": "Shop"}, pluck="user"))
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Sales Order",
				"document_name": doc.name,
				"subject": subject,
			}
		).insert(ignore_permissions=True)
		frappe.publish_realtime(
			"marketplace_new_order", {"name": doc.name, "subject": subject}, user=user, after_commit=True
		)


SITE_BLOCK = "Mening saytim"

SITE_BLOCK_HTML = """
<div class="site">
	<div>
		<div class="label">Mening saytim</div>
		<a class="url" target="_blank" rel="noopener"></a>
		<div class="hint">Shu havolani Instagram profilingizga (bio) qo'ying</div>
	</div>
	<div class="actions">
		<button class="copy" type="button">Nusxalash</button>
		<a class="open" target="_blank" rel="noopener">Saytni ochish ↗</a>
	</div>
</div>
"""

SITE_BLOCK_CSS = """
.site { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
	padding: 16px 20px; border-radius: 12px; background: var(--subtle-fg, #f3f5f7); }
.label { font-size: 12px; color: var(--text-muted, #6b7280); }
.url { display: block; font-size: 18px; font-weight: 600; color: var(--text-color, #111); word-break: break-all; }
.hint { font-size: 12px; color: var(--text-muted, #6b7280); margin-top: 2px; }
.actions { display: flex; gap: 8px; }
.copy, .open { height: 34px; padding: 0 14px; border-radius: 8px; font-size: 13px; cursor: pointer; text-decoration: none;
	display: inline-flex; align-items: center; border: 1px solid var(--border-color, #d1d5db); background: var(--fg-color, #fff); color: var(--text-color, #111); }
.open { background: #171717; color: #fff; border-color: #171717; }
"""

SITE_BLOCK_JS = """
const shop = frappe.boot.marketplace_shop;
const url = shop ? location.origin + shop.url : "";
root_element.querySelector(".url").textContent = url || "Do'kon biriktirilmagan";
root_element.querySelector(".url").href = url;
root_element.querySelector(".open").href = url;
root_element.querySelector(".copy").addEventListener("click", () => {
	frappe.utils.copy_to_clipboard(url);
});
"""


def setup_site_block():
	"""Workspace tepasidagi "Mening saytim" bloki: har bir sotuvchiga o'z do'koni havolasi."""
	doc = frappe.get_doc("Custom HTML Block", SITE_BLOCK) if frappe.db.exists("Custom HTML Block", SITE_BLOCK) else frappe.new_doc("Custom HTML Block")
	doc.update({"html": SITE_BLOCK_HTML, "style": SITE_BLOCK_CSS, "script": SITE_BLOCK_JS, "private": 0})
	doc.set("roles", [{"role": r} for r in (SELLER_ROLE, "System Manager", "Marketplace Manager")])
	if doc.is_new():
		doc.name = SITE_BLOCK
		doc.flags.name_set = True
	doc.save(ignore_permissions=True)


def setup_seller_workspace():
	"""Number Card'lar va "Do'konim" workspace'ini yaratadi yoki yangilaydi (after_migrate)."""
	for name, doctype, function, field, filters, color in NUMBER_CARDS:
		card = frappe.get_doc("Number Card", name) if frappe.db.exists("Number Card", name) else frappe.new_doc("Number Card")
		card.update(
			{
				"label": name,
				"type": "Document Type",
				"document_type": doctype,
				"function": function,
				"aggregate_function_based_on": field or "",
				"filters_json": json.dumps(filters),
				"is_public": 1,
				"is_standard": 0,
				"module": "Marketplace",
				"color": color,
				"show_percentage_stats": 0,
				"currency": "UZS" if function == "Sum" else None,
			}
		)
		if card.is_new():
			card.name = name
			card.flags.name_set = True
		card.save(ignore_permissions=True)

	shortcuts = [
		# (yorliq, turi, link_to, ko'rinish, filtr, rang, url)
		("Tovar qo'shish", "DocType", "Item", "New", None, "Green", None),
		("Tovarlarim", "DocType", "Item", "List", {"variant_of": ["is", "not set"]}, "Blue", None),
		("Ombor", "Page", "ombor", None, None, "Orange", None),
		("Hisobot", "Page", "hisobot", None, None, "Purple", None),
		("Buyurtmalar", "DocType", "Sales Order", "List", None, "Blue", None),
		("Sotuvlar", "DocType", "Sales Order", "List", {"payment_status": "To'langan"}, "Green", None),
		("Do'kon sozlamalari", "DocType", "Shop", "List", None, "Grey", None),
	]

	ws = frappe.get_doc("Workspace", WORKSPACE) if frappe.db.exists("Workspace", WORKSPACE) else frappe.new_doc("Workspace")
	ws.update(
		{
			"label": WORKSPACE,
			"title": "Do'konim",
			# O'z moduli: yon menyuda sotuvchiga kerakli bo'limlar (dokon/sidebar/dokon)
			"module": "Dokon",
			"icon": "store",
			"public": 1,
			"standard": 0,
			"is_hidden": 0,
			"for_user": "",
		}
	)
	ws.set("roles", [{"role": r} for r in (SELLER_ROLE, "System Manager", "Marketplace Manager")])
	ws.set("number_cards", [{"number_card_name": c[0], "label": c[0].split(": ", 1)[1]} for c in NUMBER_CARDS])
	ws.set(
		"shortcuts",
		[
			{
				"label": label,
				"type": type_,
				"link_to": link_to,
				"doc_view": view or "",
				"stats_filter": json.dumps(flt_) if flt_ else None,
				"color": color,
				"url": url,
			}
			for label, type_, link_to, view, flt_, color, url in shortcuts
		],
	)

	def block(type_, data):
		return {"id": frappe.generate_hash(length=10), "type": type_, "data": data}

	setup_site_block()
	ws.set("custom_blocks", [{"custom_block_name": SITE_BLOCK, "label": "Mening saytim"}])
	content = [block("custom_block", {"custom_block_name": SITE_BLOCK, "col": 12})]
	content.append(block("header", {"text": "<span class=\"h4\"><b>Balans</b></span>", "col": 12}))
	content += [block("number_card", {"number_card_name": c[0], "col": 3}) for c in NUMBER_CARDS]
	content.append(block("spacer", {"col": 12}))
	content.append(block("header", {"text": "<span class=\"h4\"><b>Tezkor amallar</b></span>", "col": 12}))
	content += [block("shortcut", {"shortcut_name": s[0], "col": 3}) for s in shortcuts]
	ws.content = json.dumps(content)

	if ws.is_new():
		ws.name = WORKSPACE
		ws.flags.name_set = True
	ws.flags.ignore_permissions = True
	ws.save(ignore_permissions=True)


@frappe.whitelist()
def get_item_stock(item_code: str):
	"""Tovarning do'kon omboridagi hozirgi soni (sotuvchida Bin'ga to'g'ridan-to'g'ri ruxsat yo'q)."""
	if not frappe.has_permission("Item", "read", item_code):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	shop = frappe.db.get_value("Item", item_code, "shop")
	warehouse = shop and frappe.db.get_value("Shop", shop, "warehouse")
	if not warehouse:
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def item_template_price(doc, method=None):
	"""Item validate: andozaga (has_variants) ERPNext narx qo'yishga ruxsat bermaydi.

	Sotuvchi "Sotish narxi"ni yozsa, u variant_price'ga o'tadi va variantlarga tarqatiladi."""
	if doc.has_variants and doc.standard_rate:
		doc.variant_price = doc.variant_price or doc.standard_rate
		doc.standard_rate = 0


def item_default_attributes(doc, method=None):
	"""Item before_validate: variant turlari jadvali bo'sh bo'lsa, Rang va O'lcham qo'yiladi
	(ERPNext uni validate'da majburiy qiladi; variant oynasi keyin tanlanganiga moslaydi)."""
	if doc.has_variants and doc.get("ranglar") is not None and (doc.get("ranglar") or not doc.get("variant_colors")):
		# Ranglar jadvali (Table MultiSelect) -> ichki matn maydoni
		doc.variant_colors = ", ".join(r.rang for r in doc.get("ranglar") or [])
	if doc.has_variants and not (not doc.is_new() and frappe.db.exists("Item", {"variant_of": doc.name})):
		# Variantlari hali yo'q andoza: turlari "Ranglar"/"O'lchamlar" maydonlariga qarab
		color_attr, size_attr = _attr_names()
		wanted = [a for a, v in ((color_attr, doc.get("variant_colors")), (size_attr, doc.get("variant_sizes"))) if _split(v)]
		if wanted and [a.attribute for a in doc.get("attributes") or []] != wanted:
			doc.set("attributes", [{"attribute": a} for a in wanted])
	if doc.has_variants and not doc.get("attributes"):
		doc.variant_based_on = "Item Attribute"
		for attr in _attr_names():
			doc.append("attributes", {"attribute": attr})
	# Yangi variant nomi: "Paxta shim (Oq · 42)" — ERPNext'ning "Paxta shim-OQ-42" o'rniga
	if doc.is_new() and doc.variant_of and doc.get("attributes"):
		base = frappe.db.get_value("Item", doc.variant_of, "item_name")
		values = " · ".join(a.attribute_value for a in doc.attributes if a.attribute_value)
		if base and values:
			doc.item_name = f"{base} ({values})"[:140]


def item_after_insert(doc, method=None):
	"""Yangi variant: narxi andozadagi variant_price'dan."""
	if doc.variant_of:
		price = flt(frappe.db.get_value("Item", doc.variant_of, "variant_price"))
		if price:
			_set_price(doc.name, price)


def _split(value):
	return list(dict.fromkeys(x.strip() for x in re.split(r"[,\n]", value or "") if x.strip()))


def item_on_update(doc, method=None):
	"""Andozada narx o'zgarsa, barcha variantlar narxi yangilanadi.
	"Ranglar"/"O'lchamlar" maydonlaridagi yangi kombinatsiyalar uchun variantlar yaratiladi."""
	if doc.has_variants and (doc.get("variant_colors") or doc.get("variant_sizes")) and not frappe.flags.mp_creating_variants:
		if doc.is_new() or doc.has_value_changed("variant_colors") or doc.has_value_changed("variant_sizes") or doc.flags.in_insert:
			frappe.flags.mp_creating_variants = True
			try:
				_create_variants(doc.name, _split(doc.variant_colors), _split(doc.variant_sizes), cint(doc.get("variant_qty")))
			finally:
				frappe.flags.mp_creating_variants = False
	if doc.has_variants and doc.has_value_changed("variant_price") and flt(doc.variant_price):
		for code in frappe.get_all("Item", filters={"variant_of": doc.name}, pluck="name"):
			_set_price(code, flt(doc.variant_price))


def _set_price(item_code, price):
	from marketplace.storefront import _selling_price_list

	price_list = _selling_price_list()
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if name:
		doc = frappe.get_doc("Item Price", name)
		doc.price_list_rate = price
		doc.save()
	else:
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": price}
		).insert()


@frappe.whitelist()
def get_variants_stock(template: str):
	"""Andozaning variantlari va do'kon omboridagi soni (Qoldiq dialogi uchun)."""
	if not frappe.has_permission("Item", "read", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	variants = frappe.get_list(
		"Item", filters={"variant_of": template, "disabled": 0}, fields=["name", "item_name"], order_by="name"
	)
	return [{"item_code": v.name, "item_name": v.item_name, "qty": get_item_stock(v.name)} for v in variants]


@frappe.whitelist()
def set_variants_stock(rows):
	"""[{item_code, qty}] — har bir variant qoldig'ini yangilaydi."""
	changed = 0
	for row in frappe.parse_json(rows):
		changed += bool(set_item_stock(row["item_code"], row["qty"]).get("changed"))
	return changed


def _seller_order(name):
	if not frappe.has_permission("Sales Order", "write", name):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	so = frappe.get_doc("Sales Order", name)
	if so.docstatus != 1:
		frappe.throw(_("Buyurtma faol emas"))
	return so


@frappe.whitelist()
def mark_cash_received(order: str):
	"""Naqd to'lov: sotuvchi pulni olganini belgilaydi."""
	so = _seller_order(order)
	if so.payment_method != "Naqd":
		frappe.throw(_("Bu buyurtma naqd emas"))
	if so.payment_status != "To'langan":
		so.db_set("payment_status", "To'langan")
		so.add_comment("Info", _("Naqd pul olindi"))
	return so.payment_status


@frappe.whitelist()
def mark_delivered(order: str):
	"""Mijozga topshirildi: ERPNext Delivery Note yaratib submit qiladi — tovar ombordan ayriladi."""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	so = _seller_order(order)
	if so.payment_status == "Bekor":
		frappe.throw(_("Bekor qilingan buyurtma"))
	if so.payment_method in ("Payme", "Click") and so.payment_status != "To'langan":
		frappe.throw(_("Onlayn to'lov hali kelmagan. To'lovdan keyin topshiring."))
	if not so.payment_method and so.payment_status != "To'langan":
		frappe.throw(_("Mijoz hali to'lov usulini tanlamagan. Tanlagandan keyin topshiring."))
	if flt(so.per_delivered) >= 100:
		return None
	from marketplace.orders import as_system

	# Ruxsat yuqorida tekshirildi. ERPNext ichida hisob (Account) o'qiladi, sotuvchida unga ruxsat yo'q
	with as_system():
		dn = make_delivery_note(so.name)
		dn.insert()
		dn.submit()
	so.add_comment("Info", _("Mijozga topshirildi: {0}").format(dn.name))
	return dn.name


@frappe.whitelist()
def cancel_order(order: str, reason: str | None = None):
	"""Sotuvchi buyurtmani bekor qiladi (to'lanmagan bo'lsa). Zaxira bo'shaydi, mijozga "Bekor" ko'rinadi."""
	so = _seller_order(order)
	if so.payment_status == "To'langan" and so.payment_method in ("Payme", "Click"):
		frappe.throw(_("Onlayn to'langan buyurtma Payme/Click kabinetidan pul qaytarish orqali bekor qilinadi"))
	if flt(so.per_delivered):
		frappe.throw(_("Topshirilgan buyurtmani bekor qilib bo'lmaydi"))
	from marketplace.orders import as_system

	so.db_set("payment_status", "Bekor")
	so.add_comment("Info", _("Sotuvchi bekor qildi") + (f": {reason}" if reason else ""))
	with as_system():
		so.cancel()
	return "Bekor"


def _attr_names():
	from marketplace.setup import COLOR_ATTR, SIZE_ATTR

	return COLOR_ATTR, SIZE_ATTR


@frappe.whitelist()
def get_variant_options(template: str | None = None):
	"""Variant oynasi uchun: mavjud ranglar/o'lchamlar va shu tovarda allaqachon borlari."""
	if template and frappe.db.exists("Item", template) and not frappe.has_permission("Item", "read", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	color_attr, size_attr = _attr_names()
	values = lambda attr: frappe.get_all(  # noqa: E731
		"Item Attribute Value", filters={"parent": attr}, pluck="attribute_value", order_by="idx", ignore_permissions=True
	)
	used = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", frappe.get_all("Item", filters={"variant_of": template}, pluck="name")]},
		fields=["attribute", "attribute_value"],
		ignore_permissions=True,
	)
	return {
		"colors": values(color_attr),
		"sizes": values(size_attr),
		"used_colors": sorted({u.attribute_value for u in used if u.attribute == color_attr}),
		"used_sizes": sorted({u.attribute_value for u in used if u.attribute == size_attr}),
	}


@frappe.whitelist()
def create_variants(template: str, colors=None, sizes=None):
	"""Tanlangan rang × o'lcham uchun variantlar. Yangi rang/o'lcham nomlari avtomatik qo'shiladi."""
	if not frappe.has_permission("Item", "write", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	clean = lambda xs: list(dict.fromkeys(x.strip() for x in frappe.parse_json(xs or "[]") if x and x.strip()))  # noqa: E731
	return _create_variants(template, clean(colors), clean(sizes))


def _create_variants(template, colors, sizes, qty=0):
	from erpnext.controllers.item_variant import create_multiple_variants

	color_attr, size_attr = _attr_names()
	if not colors and not sizes:
		frappe.throw(_("Kamida bitta rang yoki o'lcham tanlang"))
	for v in colors + sizes:
		if len(v) > 30 or not re.fullmatch(r"[\w\s\-/.,()‘'ʻ+]+", v):
			frappe.throw(_("Noto'g'ri nom: {0}").format(v))

	colors = _ensure_values(color_attr, colors)
	sizes = _ensure_values(size_attr, sizes)

	item = frappe.get_doc("Item", template)
	if not item.has_variants:
		frappe.throw(_("Avval \"Rang / o'lcham variantlari bor\" belgisini qo'yib saqlang"))
	wanted = [a for a, vals in ((color_attr, colors), (size_attr, sizes)) if vals]
	current = [a.attribute for a in item.attributes]
	if current != wanted:
		if frappe.db.exists("Item", {"variant_of": template}):
			# Variantlar bor: tuzilmani o'zgartirib bo'lmaydi, yetishmayotgan turdagi qiymat so'raladi
			missing = [a for a in current if a not in wanted]
			if missing:
				frappe.throw(_("Bu tovarda {0} ham tanlanishi kerak").format(", ".join(missing)))
		else:
			item.set("attributes", [{"attribute": a} for a in wanted])
			item.save()

	args = {a: vals for a, vals in ((color_attr, colors), (size_attr, sizes)) if vals}
	before = set(frappe.get_all("Item", filters={"variant_of": template}, pluck="name"))
	count = create_multiple_variants(template, json.dumps(args))
	if qty > 0:
		# Faqat yangi yaratilganlariga: mavjud variantlar qoldig'i o'zgarmaydi
		for code in set(frappe.get_all("Item", filters={"variant_of": template}, pluck="name")) - before:
			set_item_stock(code, qty)
	frappe.clear_cache(doctype="Item")
	return count


def _ensure_values(attr, values):
	"""Yangi nomlarni Item Attribute'ga qo'shadi. Qaytaradi: bazadagi yozilishidagi nomlar ("oq" -> "Oq")."""
	if not values:
		return []
	known = {
		v.lower(): v
		for v in frappe.get_all("Item Attribute Value", filters={"parent": attr}, pluck="attribute_value", ignore_permissions=True)
	}
	new = [v for v in values if v.lower() not in known]
	if new:
		doc = frappe.get_doc("Item Attribute", attr)
		abbrs = {r.abbr for r in doc.item_attribute_values}
		for v in new:
			abbr = re.sub(r"[^A-Za-z0-9]", "", v).upper()[:6] or frappe.generate_hash(length=4).upper()
			while abbr in abbrs:
				abbr = abbr[:5] + frappe.generate_hash(length=1).upper()
			abbrs.add(abbr)
			doc.append("item_attribute_values", {"attribute_value": v, "abbr": abbr})
			known[v.lower()] = v
		doc.flags.ignore_permissions = True
		doc.save()
	return list(dict.fromkeys(known[v.lower()] for v in values))
