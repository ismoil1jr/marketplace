"""Sotuvchi paneli (/panel) API: telefondan tovar qo'shish, rasm, narx, rang/o'lcham va qoldiq.

Sotuvchi ERPNext tushunchalarini (Item, Variant, Item Price, Stock Reconciliation) ko'rmaydi:
u bitta forma to'ldiradi, bu yerda esa shularning hammasi yaratiladi.

Xavfsizlik: har funksiya avval foydalanuvchining do'konini aniqlaydi va tovar shu do'konga
tegishli ekanini tekshiradi; yozish esa tekshiruvlardan keyin tizim nomidan bajariladi.
"""

import json
import re
import secrets

import frappe
from frappe import _
from frappe.utils import cint, flt

from marketplace import storefront
from marketplace.orders import as_system
from marketplace.permissions import clean_mxik, get_user_shop, group_fiscal_codes
from marketplace.setup import COLOR_ATTR, SIZE_ATTR

MANAGER_ROLES = {"System Manager", "Marketplace Manager"}
LOW_STOCK = 3


def panel_shop(shop=None):
	"""Sotuvchi — o'z do'koni; platforma xodimi — ?shop= bilan istalgan do'kon."""
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(_("Avval tizimga kiring"))
	own = get_user_shop()
	if own:
		return own
	if MANAGER_ROLES & set(frappe.get_roles()) or frappe.session.user == "Administrator":
		if shop and frappe.db.exists("Shop", shop):
			return shop
		first = frappe.db.get_value("Shop", {}, "name", order_by="creation asc")
		if first:
			return first
	raise frappe.PermissionError(_("Siz hech qaysi do'konga a'zo emassiz"))


@frappe.whitelist()
def bootstrap(shop=None):
	shop = panel_shop(shop)
	s = frappe.db.get_value("Shop", shop, ["name", "shop_name", "brand_color", "logo", "status"], as_dict=True)
	s.initials = "".join(w[0] for w in s.shop_name.split()[:2]).upper()
	s.url = f"/s/{shop}"
	groups = frappe.get_all("Item Group", filters={"is_group": 0, "name": ["not in", ["Services", "Raw Material", "Sub Assemblies", "Consumable", "Products"]]}, fields=["name", "parent_item_group"], order_by="lft")
	colors = frappe.get_all("Item Attribute Value", filters={"parent": COLOR_ATTR}, fields=["attribute_value as value", "color_hex as hex"], order_by="idx")
	sizes = frappe.get_all("Item Attribute Value", filters={"parent": SIZE_ATTR}, pluck="attribute_value", order_by="idx")
	return {
		"shop": s,
		"groups": groups,
		"colors": colors,
		"sizes": sizes,
		"is_manager": not get_user_shop(),
		"shops": frappe.get_all("Shop", fields=["name", "shop_name"], order_by="shop_name") if not get_user_shop() else [],
	}


@frappe.whitelist()
def list_products(shop=None):
	shop = panel_shop(shop)
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	items = frappe.get_all(
		"Item",
		filters={"shop": shop, "variant_of": ["is", "not set"], "disabled": 0, "item_code": ["not like", "%smoke-test%"]},
		fields=["name", "item_name", "item_group", "image", "is_published", "has_variants", "mxik_code", "modified"],
		order_by="modified desc",
	)
	codes = [i.name for i in items]
	prices = storefront._get_prices(codes) if codes else {}
	thumbs = storefront._get_thumbnails(codes) if codes else {}
	stock = _stock_with_reserved(codes, warehouse)
	templates = [i.name for i in items if i.has_variants]
	variants = frappe.get_all("Item", filters={"variant_of": ["in", templates or [""]], "disabled": 0}, fields=["name", "variant_of"])
	vstock = _stock_with_reserved([v.name for v in variants], warehouse)
	vcount = {}
	for v in variants:
		agg = stock.setdefault(v.variant_of, {"actual": 0, "reserved": 0})
		agg["actual"] += vstock.get(v.name, {}).get("actual", 0)
		agg["reserved"] += vstock.get(v.name, {}).get("reserved", 0)
		vcount[v.variant_of] = vcount.get(v.variant_of, 0) + 1

	out = []
	for i in items:
		st = stock.get(i.name, {"actual": 0, "reserved": 0})
		free = st["actual"] - st["reserved"]
		out.append(
			{
				"code": i.name,
				"name": i.item_name,
				"group": i.item_group,
				"thumb": thumbs.get(i.name) or i.image,
				"price": prices.get(i.name),
				"published": i.is_published,
				"actual": st["actual"],
				"reserved": st["reserved"],
				"free": free,
				"variants": vcount.get(i.name, 0),
				"status": "out" if free <= 0 else ("low" if free <= LOW_STOCK else "ok"),
				"problems": [p for p, bad in (("Narx yo'q", i.name not in prices), ("MXIK yo'q", not i.mxik_code)) if bad],
			}
		)
	return out


@frappe.whitelist()
def get_product(code, shop=None):
	shop = panel_shop(shop)
	item = _own_item(code, shop)
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	data = {
		"code": item.name,
		"name": item.item_name,
		"group": item.item_group,
		"price": storefront._get_prices([item.name]).get(item.name),
		"old_price": item.old_price or None,
		"wholesale_price": item.wholesale_price or None,
		"wholesale_min": item.wholesale_min_qty or 10,
		"spec": item.spec_line,
		"description": storefront._plain_text(item.description),
		"mxik": item.mxik_code,
		"package_code": item.package_code,
		"published": item.is_published,
		"images": [{"image": g.image, "thumb": g.thumbnail or g.image} for g in item.get("gallery") or []],
		"has_variants": item.has_variants,
		"colors": [],
		"sizes": [],
		"stock": {},
	}
	if item.has_variants:
		attrs = {a.attribute for a in item.attributes}
		variants = frappe.get_all("Item", filters={"variant_of": item.name, "disabled": 0}, pluck="name")
		labels = _variant_attrs(variants)
		st = _stock_with_reserved(variants, warehouse)
		for code_, a in labels.items():
			c, s = a.get(COLOR_ATTR, ""), a.get(SIZE_ATTR, "")
			if c and c not in data["colors"]:
				data["colors"].append(c)
			if s and s not in data["sizes"]:
				data["sizes"].append(s)
			data["stock"][f"{c}|{s}"] = st.get(code_, {"actual": 0, "reserved": 0})
		data["dims"] = {"color": COLOR_ATTR in attrs, "size": SIZE_ATTR in attrs}
	else:
		data["stock"]["|"] = _stock_with_reserved([item.name], warehouse).get(item.name, {"actual": 0, "reserved": 0})
	return data


@frappe.whitelist(methods=["POST"])
def save_product(data, shop=None):
	shop = panel_shop(shop)
	data = frappe._dict(json.loads(data) if isinstance(data, str) else data)
	_validate(data)
	colors, sizes = data.get("colors") or [], data.get("sizes") or []
	has_variants = bool(colors or sizes)

	with as_system():
		item = _own_item(data.code, shop) if data.get("code") else None
		if item and cint(item.has_variants) != int(has_variants):
			frappe.throw(_("Rang/o'lcham bor-yo'qligini keyin o'zgartirib bo'lmaydi. Yangi tovar sifatida qo'shing."))
		if item and has_variants:
			dims = {a.attribute for a in item.attributes}
			if (COLOR_ATTR in dims) != bool(colors) or (SIZE_ATTR in dims) != bool(sizes):
				frappe.throw(_("Rang yoki o'lcham turini olib tashlab/qo'shib bo'lmaydi. Yangi tovar sifatida qo'shing."))

		_ensure_attribute_values(colors, sizes)
		item = _upsert_template(item, data, shop, colors, sizes)
		warehouse = frappe.db.get_value("Shop", shop, "warehouse")

		stock = data.get("stock") or {}
		if has_variants:
			# ERPNext template'ga narx qo'yishga ruxsat bermaydi — narx har variantda (hammasida bir xil)
			targets = _sync_variants(item, colors, sizes)
			for code in targets.values():
				_upsert_price(code, flt(data.price))
			wanted = {targets[k]: cint(v) for k, v in stock.items() if k in targets}
		else:
			_upsert_price(item.name, flt(data.price))
			wanted = {item.name: cint(stock.get("|", 0))}
		_set_stock(wanted, warehouse)

	frappe.cache.delete_value(storefront._cache_key(shop))
	return {"code": item.name}


@frappe.whitelist(methods=["POST"])
def set_published(code, published, shop=None):
	shop = panel_shop(shop)
	item = _own_item(code, shop)
	if cint(published) and not item.mxik_code:
		frappe.throw(_("Saytga chiqarish uchun MXIK kodi kerak"))
	with as_system():
		for name in [item.name] + frappe.get_all("Item", filters={"variant_of": item.name}, pluck="name"):
			frappe.db.set_value("Item", name, "is_published", cint(published))
	frappe.cache.delete_value(storefront._cache_key(shop))


@frappe.whitelist(methods=["POST"])
def archive_product(code, shop=None):
	"""O'chirmaymiz (buyurtmalar tarixi saqlanadi) — tovar va variantlari o'chiriladi (disabled)."""
	shop = panel_shop(shop)
	item = _own_item(code, shop)
	with as_system():
		for name in [item.name] + frappe.get_all("Item", filters={"variant_of": item.name}, pluck="name"):
			frappe.db.set_value("Item", name, {"disabled": 1, "is_published": 0})
	frappe.cache.delete_value(storefront._cache_key(shop))


# ---------------------------------------------------------------- ichki


def _own_item(code, shop):
	item = frappe.get_doc("Item", code)
	if item.shop != shop or item.variant_of:
		raise frappe.PermissionError(_("Bu tovar sizning do'koningizga tegishli emas"))
	return item


def _validate(d):
	if len((d.get("name") or "").strip()) < 2:
		frappe.throw(_("Tovar nomini yozing"))
	if not d.get("group") or not frappe.db.exists("Item Group", {"name": d.group, "is_group": 0}):
		frappe.throw(_("Kategoriyani tanlang"))
	if flt(d.get("price")) <= 0:
		frappe.throw(_("Narxni kiriting"))
	if flt(d.get("old_price")) and flt(d.old_price) <= flt(d.price):
		frappe.throw(_("Eski narx hozirgi narxdan katta bo'lishi kerak (chegirma uchun)"))
	if flt(d.get("wholesale_price")) and flt(d.wholesale_price) >= flt(d.price):
		frappe.throw(_("Ulgurji narx chakana narxdan kichik bo'lishi kerak"))
	mxik = clean_mxik(d.get("mxik"))
	if not mxik:
		mxik, group_package = group_fiscal_codes(d.group)
		d.package_code = d.get("package_code") or group_package
	if cint(d.get("published")) and not mxik:
		frappe.throw(_("Saytga chiqarish uchun MXIK kodi kerak (fiskal chek uchun)"))
	d.mxik = mxik
	for size in d.get("sizes") or []:
		if not re.fullmatch(r"[\w\-/.]{1,10}", size or ""):
			frappe.throw(_("O'lcham noto'g'ri: {0}").format(size))
	if len(d.get("images") or []) > 10:
		frappe.throw(_("Ko'pi bilan 10 ta rasm"))
	for qty in (d.get("stock") or {}).values():
		if cint(qty) < 0 or cint(qty) > 100000:
			frappe.throw(_("Qoldiq soni noto'g'ri"))


def _ensure_attribute_values(colors, sizes):
	known = set(frappe.get_all("Item Attribute Value", filters={"parent": COLOR_ATTR}, pluck="attribute_value"))
	unknown = [c for c in colors if c not in known]
	if unknown:
		frappe.throw(_("Noma'lum rang: {0}").format(", ".join(unknown)))
	known_sizes = set(frappe.get_all("Item Attribute Value", filters={"parent": SIZE_ATTR}, pluck="attribute_value"))
	new_sizes = [s for s in sizes if s not in known_sizes]
	if new_sizes:
		attr = frappe.get_doc("Item Attribute", SIZE_ATTR)
		for s in new_sizes:
			attr.append("item_attribute_values", {"attribute_value": s, "abbr": s.upper()})
		attr.save(ignore_permissions=True)


def _upsert_template(item, d, shop, colors, sizes):
	fields = {
		"item_name": d.name.strip(),
		"item_group": d.group,
		"old_price": flt(d.get("old_price")) or 0,
		"wholesale_price": flt(d.get("wholesale_price")) or 0,
		"wholesale_min_qty": cint(d.get("wholesale_min")) or 10,
		"spec_line": (d.get("spec") or "").strip(),
		"description": frappe.utils.escape_html(d.get("description") or "").replace("\n", "<br>"),
		"mxik_code": d.mxik,
		"package_code": (d.get("package_code") or "").strip(),
		"is_published": cint(d.get("published")),
	}
	if not item:
		item = frappe.new_doc("Item")
		item.update(fields)
		item.update({"item_code": _make_code(d.name), "shop": shop, "stock_uom": "Nos", "is_stock_item": 1})
		if colors or sizes:
			item.has_variants = 1
			item.variant_based_on = "Item Attribute"
			for attr, used in ((COLOR_ATTR, colors), (SIZE_ATTR, sizes)):
				if used:
					item.append("attributes", {"attribute": attr})
	else:
		item.update(fields)

	# Rasmlar: mavjud qatorlarni (siqilgan nusxalari bilan) saqlab, tartibni formadagidek qilamiz
	old_rows = {g.image: g for g in item.get("gallery") or []}
	item.set("gallery", [])
	for img in d.get("images") or []:
		url = img.get("image") if isinstance(img, dict) else img
		row = old_rows.get(url)
		item.append("gallery", {"image": url, "medium": row.medium if row else None, "thumbnail": row.thumbnail if row else None, "processed_image": row.processed_image if row else None})
	item.save() if not item.is_new() else item.insert()
	_attach_files(item)
	return item


def _attach_files(item):
	for g in item.get("gallery") or []:
		frappe.db.set_value("File", {"file_url": g.image, "attached_to_name": ["is", "not set"]}, {"attached_to_doctype": "Item", "attached_to_name": item.name})


def _make_code(name):
	slug = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("‘", "").replace("'", "").replace("ʻ", "")).strip("-")[:32] or "tovar"
	return f"{slug}-{secrets.token_hex(2)}"


def _upsert_price(code, price):
	pl = storefront._selling_price_list()
	name = frappe.db.get_value("Item Price", {"item_code": code, "price_list": pl})
	if name:
		frappe.db.set_value("Item Price", name, "price_list_rate", price)
	else:
		frappe.get_doc({"doctype": "Item Price", "item_code": code, "price_list": pl, "price_list_rate": price}).insert()


def _sync_variants(template, colors, sizes):
	"""Har rang × o'lcham uchun variant. Olib tashlanganlari o'chiriladi (disabled), tarix saqlanadi.
	Qaytaradi: {'Oq|M': 'variant kodi'}"""
	existing = frappe.get_all("Item", filters={"variant_of": template.name}, fields=["name", "disabled"])
	attrs = _variant_attrs([e.name for e in existing])
	by_key = {f"{a.get(COLOR_ATTR, '')}|{a.get(SIZE_ATTR, '')}": code for code, a in attrs.items()}
	abbr = dict(frappe.get_all("Item Attribute Value", filters={"parent": ["in", [COLOR_ATTR, SIZE_ATTR]]}, fields=["attribute_value", "abbr"], as_list=True))

	wanted = {}
	for c in colors or [""]:
		for s in sizes or [""]:
			wanted[f"{c}|{s}"] = (c, s)

	result = {}
	for key, (c, s) in wanted.items():
		label = " · ".join(x for x in (c, s) if x)
		common = {
			"item_name": f"{template.item_name} ({label})",
			"is_published": template.is_published,
			"mxik_code": template.mxik_code,
			"package_code": template.package_code,
			"item_group": template.item_group,
			"disabled": 0,
		}
		if key in by_key:
			frappe.db.set_value("Item", by_key[key], common)
			result[key] = by_key[key]
			continue
		suffix = "-".join(re.sub(r"[^a-z0-9]+", "", abbr.get(x, x).lower()) for x in (c, s) if x)
		variant = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"{template.name}-{suffix}",
				"variant_of": template.name,
				"variant_based_on": "Item Attribute",
				"shop": template.shop,
				"stock_uom": template.stock_uom,
				"is_stock_item": 1,
				"attributes": [{"attribute": a, "attribute_value": v} for a, v in ((COLOR_ATTR, c), (SIZE_ATTR, s)) if v],
				**common,
			}
		)
		variant.insert()
		result[key] = variant.name

	for key, code in by_key.items():
		if key not in wanted:
			frappe.db.set_value("Item", code, {"disabled": 1, "is_published": 0})
	return result


def _set_stock(wanted, warehouse):
	"""Sotuvchi "omborda nechta bor" deb yozadi — farq bo'lsa Stock Reconciliation qilinadi."""
	current = _stock_with_reserved(list(wanted), warehouse)
	rows = []
	for code, qty in wanted.items():
		have = current.get(code, {}).get("actual", 0)
		if qty == have or (qty == 0 and code not in current):
			continue
		rows.append({"item_code": code, "warehouse": warehouse, "qty": qty, "valuation_rate": 1})
	if rows:
		sr = frappe.get_doc(
			{"doctype": "Stock Reconciliation", "company": frappe.defaults.get_global_default("company"), "purpose": "Stock Reconciliation", "items": rows}
		)
		sr.insert()
		sr.submit()


def _stock_with_reserved(codes, warehouse):
	if not codes or not warehouse:
		return {}
	rows = frappe.get_all("Bin", filters={"item_code": ["in", codes], "warehouse": warehouse}, fields=["item_code", "actual_qty", "reserved_qty"])
	return {r.item_code: {"actual": cint(r.actual_qty), "reserved": cint(r.reserved_qty)} for r in rows}


def _variant_attrs(codes):
	rows = frappe.get_all(
		"Item Variant Attribute", filters={"parent": ["in", codes or [""]], "parenttype": "Item"},
		fields=["parent", "attribute", "attribute_value"],
	)
	out = {}
	for r in rows:
		out.setdefault(r.parent, {})[r.attribute] = r.attribute_value
	return out
