"""Platforma admini uchun: barcha mijoz do'konlari bir sahifada (Desk → Do'konlar paneli)."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, today


@frappe.whitelist()
def get_shops_overview():
	frappe.only_for(("System Manager", "Marketplace Manager"))

	shops = frappe.get_all(
		"Shop",
		fields=[
			"name", "shop_name", "status", "logo", "cover_image", "brand_color", "layout_style",
			"city", "instagram", "phone", "enable_payme", "enable_click", "enable_cod", "creation",
		],
		order_by="creation desc",
	)
	if not shops:
		return {"shops": [], "totals": {}}

	names = [s.name for s in shops]
	items = _count_by("Item", names, {"disabled": 0, "is_published": 1})
	orders = _count_by("Sales Order", names, {"docstatus": ["<", 2]})
	orders_week = _count_by("Sales Order", names, {"docstatus": ["<", 2], "transaction_date": [">=", add_days(today(), -7)]})
	revenue = {
		r.shop: flt(r.total)
		for r in frappe.get_all(
			"Sales Order",
			filters={"shop": ["in", names], "docstatus": 1, "payment_status": "To'langan"},
			fields=["shop", {"SUM": "grand_total", "as": "total"}],
			group_by="shop",
		)
	}
	members = {}
	for m in frappe.get_all("Shop Member", filters={"parent": ["in", names], "parenttype": "Shop"}, fields=["parent", "user", "role"]):
		members.setdefault(m.parent, []).append({"user": m.user, "role": m.role})

	for s in shops:
		s.update(
			{
				"url": f"/s/{s.name}",
				"items": items.get(s.name, 0),
				"orders": orders.get(s.name, 0),
				"orders_week": orders_week.get(s.name, 0),
				"revenue": revenue.get(s.name, 0),
				"members": members.get(s.name, []),
				"payments": [p for flag, p in ((s.enable_payme, "Payme"), (s.enable_click, "Click"), (s.enable_cod, "Naqd")) if flag],
				"initials": "".join(w[0] for w in s.shop_name.split()[:2]).upper(),
			}
		)

	totals = {
		"shops": len(shops),
		"active": sum(1 for s in shops if s.status == "Active"),
		"items": sum(items.values()),
		"orders_week": sum(orders_week.values()),
	}
	return {"shops": shops, "totals": totals}


def _count_by(doctype, shops, filters):
	rows = frappe.get_all(
		doctype,
		filters={"shop": ["in", shops], **filters},
		fields=["shop", {"COUNT": "*", "as": "cnt"}],
		group_by="shop",
	)
	return {r.shop: r.cnt for r in rows}


def has_app_permission():
	"""Desk bosh ekranidagi ikonka: admin va sotuvchiga (sotuvchida u o'z do'koni nomi bilan chiqadi)."""
	return bool({"System Manager", "Marketplace Manager", "Shop Seller"} & set(frappe.get_roles()))


@frappe.whitelist()
def enter_shop_panel(shop: str):
	"""Admin o'z akkauntida qolgan holda do'kon panelini ochadi: menyu, tovarlar, ombor, hisobot —
	hammasi shu do'kon bo'yicha. Sotuvchiga hech narsa yuborilmaydi. Belgi faqat shu sessiyada turadi."""
	frappe.only_for(("System Manager", "Marketplace Manager"))
	if not frappe.db.exists("Shop", shop):
		frappe.throw(_("Do'kon topilmadi"))
	_set_view_shop(shop)
	return "/desk/dokonim"


@frappe.whitelist()
def leave_shop_panel():
	frappe.only_for(("System Manager", "Marketplace Manager"))
	_set_view_shop(None)
	return "/desk/shops-overview"


def _set_view_shop(shop):
	session = frappe.local.session_obj
	session.data.data.mp_view_shop = shop
	session.update(force=True)
	frappe.clear_cache(user=frappe.session.user)


ADMIN_WORKSPACE = "Marketplace"

# (nom, doctype, funksiya, maydon, filtrlar, dinamik filtrlar, rang)
ADMIN_CARDS = [
	("Marketplace: Faol do'konlar", "Shop", "Count", None, [["status", "=", "Active"]], None, "#2563eb"),
	("Marketplace: Bugungi buyurtmalar", "Sales Order", "Count", None, [["docstatus", "=", 1]],
		[["Sales Order", "transaction_date", "=", "frappe.datetime.get_today()"]], "#7c3aed"),
	("Marketplace: Tushum (to'langan)", "Sales Order", "Sum", "grand_total",
		[["docstatus", "=", 1], ["payment_status", "=", "To'langan"]], None, "#16a34a"),
	("Marketplace: To'lov kutilmoqda", "Sales Order", "Count", None,
		[["docstatus", "=", 1], ["payment_status", "=", "Kutilmoqda"]], None, "#d97706"),
]


def setup_admin_workspace():
	"""Desktop'dagi "Marketplace" ikonkasi ochadigan sahifa: umumiy raqamlar va hisobotlar (after_migrate)."""
	import json

	for name, doctype, function, field, filters, dynamic, color in ADMIN_CARDS:
		card = frappe.get_doc("Number Card", name) if frappe.db.exists("Number Card", name) else frappe.new_doc("Number Card")
		card.update(
			{
				"label": name,
				"type": "Document Type",
				"document_type": doctype,
				"function": function,
				"aggregate_function_based_on": field or "",
				"filters_json": json.dumps(filters),
				"dynamic_filters_json": json.dumps(dynamic) if dynamic else None,
				"is_public": 1,
				"is_standard": 0,
				"module": "Marketplace",
				"color": color,
				"currency": "UZS" if function == "Sum" else None,
			}
		)
		if card.is_new():
			card.name = name
			card.flags.name_set = True
		card.save(ignore_permissions=True)

	shortcuts = [
		("Do'konlar paneli", "Page", "shops-overview", None, "Blue"),
		("Savdo hisoboti", "Report", "Marketplace Savdo Hisoboti", None, "Green"),
		("Buyurtmalar", "DocType", "Sales Order", "List", "Orange"),
		("To'lovlar (Payme/Click)", "DocType", "Payment Transaction", "List", "Purple"),
		("Tovarlar", "DocType", "Item", "List", "Grey"),
		("Marketplace sozlamalari", "DocType", "Marketplace Settings", None, "Grey"),
	]
	ws = frappe.get_doc("Workspace", ADMIN_WORKSPACE) if frappe.db.exists("Workspace", ADMIN_WORKSPACE) else frappe.new_doc("Workspace")
	ws.update({"label": ADMIN_WORKSPACE, "title": ADMIN_WORKSPACE, "module": "Marketplace", "icon": "store",
		"public": 1, "standard": 0, "is_hidden": 0, "for_user": ""})
	ws.set("roles", [{"role": "System Manager"}, {"role": "Marketplace Manager"}])
	ws.set("number_cards", [{"number_card_name": c[0], "label": c[0].split(": ", 1)[1]} for c in ADMIN_CARDS])
	ws.set(
		"shortcuts",
		[
			{"label": label, "type": type_, "link_to": link_to, "doc_view": view or "", "color": color,
				"report_ref_doctype": "Sales Order" if type_ == "Report" else None}
			for label, type_, link_to, view, color in shortcuts
		],
	)

	def block(type_, data):
		return {"id": frappe.generate_hash(length=10), "type": type_, "data": data}

	content = [block("header", {"text": '<span class="h4"><b>Umumiy holat</b></span>', "col": 12})]
	content += [block("number_card", {"number_card_name": c[0], "col": 3}) for c in ADMIN_CARDS]
	content.append(block("spacer", {"col": 12}))
	content.append(block("header", {"text": '<span class="h4"><b>Hisobotlar va boshqaruv</b></span>', "col": 12}))
	content += [block("shortcut", {"shortcut_name": s[0], "col": 4}) for s in shortcuts]
	ws.content = json.dumps(content)
	if ws.is_new():
		ws.name = ADMIN_WORKSPACE
		ws.flags.name_set = True
	ws.save(ignore_permissions=True)
