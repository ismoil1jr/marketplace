"""Mijoz sahifalari uchun ma'lumot: do'kon, katalog, mahsulot.

Mijozlar ko'p, sotuvchilar tovarni kam o'zgartiradi. Shuning uchun katalog
Redis'da keshlanadi va tovar yoki narx o'zgarganda o'sha do'kon keshi tozalanadi.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from marketplace.marketplace.doctype.rang.rang import color_names, shop_hexes
from marketplace.permissions import group_title

CACHE_TTL = 300  # 5 daqiqa; tovar/narx o'zgarsa darhol tozalanadi


def get_shop(slug):
	"""Faol do'kon yoki 404."""
	shop = frappe.db.get_value(
		"Shop",
		{"name": slug, "status": "Active"},
		[
			"name", "shop_name", "tagline", "city", "logo", "cover_image", "brand_color", "layout_style",
			"instagram", "phone", "pickup_address", "pickup_hours", "pickup_map",
			"delivery_info", "delivery_short", "banner_label", "banner_title", "banner_image",
			"banner_group", "enable_payme", "enable_click", "enable_cod", "enable_pickup", "warehouse",
		],
		as_dict=True,
	)
	if not shop:
		raise frappe.DoesNotExistError(_("Do'kon topilmadi"))

	shop.initials = "".join(w[0] for w in shop.shop_name.split()[:2]).upper()
	shop.payment_label = " · ".join(
		label for flag, label in ((shop.enable_payme, "Payme"), (shop.enable_click, "Click"), (shop.enable_cod, "Naqd")) if flag
	)
	shop.instagram_handle = (shop.instagram or "").lstrip("@")
	# Karusel slaydlari (sotuvchi Shop formasida o'zi yangilaydi)
	shop.banners = frappe.get_all(
		"Shop Banner",
		filters={"parent": shop.name, "parenttype": "Shop", "enabled": 1},
		fields=["image", "label", "title", "item_group", "item", "button_label"],
		order_by="idx",
	)
	_link_banner_items(shop.name, shop.banners)
	shop.banners += _carousel_items(shop.name)
	for b in shop.banners:
		b.item_group = group_title(b.get("item_group"))  # saytda kategoriya kaliti — nomi (_category_tree)
	shop.layout = resolve_layout(shop)
	return shop


LAYOUTS = ("vitrina", "story", "katalog")


def resolve_layout(shop):
	"""Do'kon shabloni. ?layout=story — faqat ko'rib chiqish: sozlamani o'zgartirmaydi va
	faqat shu havola bo'ylab yuradi (JS ichki havolalarga ?layout= qo'shadi).
	Parametrsiz havola har doim do'konning haqiqiy shablonini ochadi.
	"""
	_forget_old_preview_cookie(shop)
	requested = frappe.form_dict.get("layout")
	shop.preview = requested if requested in LAYOUTS and requested != shop.layout_style else None
	return shop.preview or shop.layout_style or "vitrina"


def _forget_old_preview_cookie(shop):
	# Avvalgi versiya ko'rib chiqishni cookie'da saqlardi va u "yopishib" qolardi
	request = getattr(frappe, "request", None)
	cookies = getattr(frappe.local, "cookie_manager", None)
	name = f"sf_layout_{shop.name}"
	if request and cookies and request.cookies.get(name):
		cookies.delete_cookie(name)


def get_catalog(shop):
	key = _cache_key(shop.name)
	data = frappe.cache.get_value(key, expires=True)
	if data is None:
		data = _build_catalog(shop)
		frappe.cache.set_value(key, data, expires_in_sec=CACHE_TTL)
	return data


def _build_catalog(shop):
	items = frappe.get_all(
		"Item",
		filters={"shop": shop.name, "is_published": 1, "disabled": 0, "variant_of": ["is", "not set"]},
		fields=[
			"name", "item_name", "item_group", "image", "old_price", "is_stock_item", "creation",
			"spec_line", "wholesale_price", "wholesale_min_qty", "has_variants", "mp_tez_kunda",
			"variant_price", "standard_rate",
		],
		order_by="creation desc",
	)
	if not items:
		return {"items": [], "groups": []}

	codes = [i.name for i in items]
	prices = _get_prices(codes)
	varying = _varying_prices([i.name for i in items if i.has_variants])
	stock = _get_stock(codes, shop.warehouse)
	stock.update(_get_variant_stock([i.name for i in items if i.has_variants], shop.warehouse))
	thumbs = _get_thumbnails(codes)
	gallery = _get_gallery(codes)

	result = []
	for i in items:
		price = prices.get(i.name)
		if price is None and not i.mp_tez_kunda:
			continue  # narxsiz tovar sotuvga chiqmaydi ("tez kunda" — narxsiz ham ko'rinadi)
		price = price or (_soon_price(i) if i.mp_tez_kunda else 0)
		old = flt(i.old_price)
		result.append(
			{
				"code": i.name,
				"name": i.item_name,
				"group": i.item_group,
				"price": price,
				# Rang/o'lchamlar narxi har xil: kartada "100 000 so'mdan" (price — eng arzoni)
				"price_from": i.name in varying,
				"old_price": old if old > price > 0 else None,
				"discount": round((1 - price / old) * 100) if old > price > 0 else None,
				"thumb": thumbs.get(i.name) or i.image,
				"images": gallery.get(i.name) or ([i.image] if i.image else []),
				# "Tez kunda": ko'rinadi, sevimlilarga qo'shiladi, lekin sotilmaydi (savatga tugma chiqmaydi)
				"coming_soon": cint(i.mp_tez_kunda),
				"in_stock": False if i.mp_tez_kunda else (stock.get(i.name, 0) > 0) if (i.is_stock_item or i.has_variants) else True,
				"stock_qty": None if i.mp_tez_kunda else cint(stock.get(i.name, 0)) if (i.is_stock_item or i.has_variants) else None,
				"has_variants": cint(i.has_variants),
				"created": str(i.creation),
				"is_new": False,
				"spec": i.spec_line,
				**_wholesale(i, price),
			}
		)

	# "Yangi" — eng oxirgi 4 ta (katalog kichik bo'lsa belgi ma'nosiz)
	if len(result) > 6:
		for r in result[:4]:
			r["is_new"] = True

	groups, tree = _category_tree(shop, result)
	return {"items": result, "groups": groups, "tree": tree}


def _category_tree(shop, items):
	"""Ustma-ust kategoriyalar (Telefonlar › Xiaomi): har tovarga yo'li ("Telefonlar|Xiaomi") — saytda bosh kategoriya
	tanlansa, uning ichidagi barcha tovarlar chiqadi. Qaytaradi: bosh kategoriyalar (daraxt tartibida) va
	{papka: [ichidagi kategoriyalar]} — faqat tovari borlari."""
	used = {r["group"] for r in items if r.get("group")}
	if not used:
		return [], {}
	rows = frappe.get_all("Item Group", fields=["name", "mp_title", "item_group_name", "lft", "rgt", "shop", "parent_item_group"], order_by="lft asc")
	by_name = {r.name: r for r in rows}
	paths = {}
	for leaf in used:
		node, path = by_name.get(leaf), []
		# Yuqoriga — do'konning o'z kategoriyalari bo'ylab (ildiz va boshqa do'konlarniki kirmaydi)
		while node and (node.shop == shop.name or node.name == leaf):
			path.insert(0, node.name)
			node = by_name.get(node.parent_item_group)
		paths[leaf] = path or [leaf]
	# Bosh qavatda bitta papka bo'lsa (masalan, faqat "Mebel") — xaridor ortiqcha bosmasin: ichidagilari bosh qavat
	while paths and len({p[0] for p in paths.values()}) == 1 and all(len(p) > 1 for p in paths.values()):
		paths = {leaf: p[1:] for leaf, p in paths.items()}
	for r in items:
		r["groups"] = "|".join(paths.get(r.get("group"), [r.get("group") or ""]))
	order = {r.name: r.lft for r in rows}
	tops = sorted({p[0] for p in paths.values()}, key=lambda n: order.get(n, 0))
	tree = {}
	for path in paths.values():
		for parent, child in zip(path, path[1:]):
			tree.setdefault(parent, set()).add(child)
	# Saytda kalit ham, yozuv ham — kategoriya nomi (ID emas: "Kiyimlar (clothes)" -> "Kiyimlar"); do'kon ichida
	# nomlar takrorlanmaydi (permissions.item_group_before_insert)
	title = lambda n: (by_name.get(n) or {}).get("mp_title") or (by_name.get(n) or {}).get("item_group_name") or n
	for r in items:
		r["groups"] = "|".join(title(n) for n in r["groups"].split("|"))
		r["group"] = title(r.get("group")) if r.get("group") else r.get("group")
	return [title(n) for n in tops], {title(k): [title(c) for c in sorted(v, key=lambda n: order.get(n, 0))] for k, v in tree.items()}


def get_highlights(catalog):
	"""B shablon: Instagram "highlights" doirachalari — Yangi, Chegirma va kategoriyalar."""
	items = catalog["items"]
	out = []
	specials = (("__new", "Yangi", lambda r: r["is_new"]), ("__sale", "Chegirma", lambda r: r["discount"]))
	for key, label, test in specials:
		first = next((r for r in items if test(r)), None)
		if first:
			out.append({"key": key, "label": label, "thumb": first["thumb"], "accent": True})
	for g in catalog["groups"]:
		first = next((r for r in items if g in (r.get("groups") or r["group"]).split("|")), None)
		out.append({"key": g, "label": g, "thumb": first["thumb"] if first else None, "accent": False})
	return out


def get_product(shop, code):
	if not frappe.db.exists("Item", {"name": code, "shop": shop.name, "is_published": 1, "disabled": 0}):
		raise frappe.DoesNotExistError(_("Mahsulot topilmadi"))

	item = frappe.get_doc("Item", code)
	price = _get_prices([code]).get(code)
	# Narxi yo'q tovar (sotuvchi hali qo'ymagan): katalogda chiqmaydi, lekin sahifasi ochiladi — "Narx qo'yilmagan",
	# sotib bo'lmaydi. Avval 404 berardi, sotuvchi "Saytda ko'rish"da xato ko'rardi
	no_price = price is None and not item.get("mp_tez_kunda")
	# "Tez kunda": variantlari hali yo'q bo'lsa ham formadagi narx ko'rinadi (yoki narx hali qo'yilmagan — 0)
	price = price or (_soon_price(item) if item.get("mp_tez_kunda") or no_price else 0)

	# Rasm rangga bog'langan bo'lsa (galereyadagi "Rang" ustuni), saytda o'sha rang tanlanganda faqat u chiqadi
	# src — sahifadagi o'rta o'lcham, full — bosganda ochiladigan asl rasm, thumb — chapdagi kichik rasmcha.
	# Galereyada Rang ID ("Oq (clothes)"), variantda nomi ("Oq") — saytga nomi beriladi
	names = color_names([g.get("rang") for g in item.get("gallery") or []])
	gallery = []
	for g in item.get("gallery") or []:
		color = names.get(g.get("rang"), "")
		poster = g.thumbnail or g.medium or g.image or ""
		if g.get("video"):
			gallery.append({"type": "video", "src": g.video, "full": g.video, "thumb": poster, "poster": g.medium or g.image or "", "color": color})
		elif g.image:
			gallery.append({"type": "image", "src": g.medium or g.image, "full": g.image or g.medium, "thumb": poster, "color": color})
	# Video — Uzum'dagidek eng boshida, qolganlari sotuvchi tartibida
	gallery.sort(key=lambda g: g["type"] != "video")
	if not gallery and item.image:
		gallery = [{"type": "image", "src": item.image, "full": item.image, "thumb": item.image, "color": ""}]
	images = [g["src"] for g in gallery if g["type"] == "image"]
	options = get_variant_options(item, shop.warehouse) if item.has_variants else None
	qty = sum(v["qty"] for v in options["variants"].values()) if options else _get_stock([code], shop.warehouse).get(code, 0)
	old = flt(item.old_price)
	return frappe._dict(
		options=options,
		code=item.name,
		name=item.item_name,
		group=group_title(item.item_group),
		description=_plain_text(item.description),
		price=price,
		# Variantlar narxi har xil: tanlanmaguncha "…so'mdan", tanlanganda — o'sha variant narxi (storefront.js)
		price_from=bool(options) and len({v["price"] for v in options["variants"].values() if v["price"]}) > 1,
		list_price=old,
		old_price=old if old > price > 0 else None,
		discount=round((1 - price / old) * 100) if old > price > 0 else None,
		images=images,
		gallery=gallery,
		thumb=_get_thumbnails([code]).get(code) or (images[0] if images else None),
		coming_soon=cint(item.get("mp_tez_kunda")),
		no_price=no_price,
		in_stock=False if (item.get("mp_tez_kunda") or no_price) else (qty > 0) if (item.is_stock_item or options) else True,
		max_qty=cint(qty) if item.is_stock_item else 99,
	)


def get_related(shop, product, limit=12):
	"""Mahsulot sahifasi pastidagi "O'xshash mahsulotlar": shu do'konning shu kategoriyasidan,
	avval sotuvda borlari. Katalog keshidan olinadi (qo'shimcha so'rov yo'q)."""
	same = [p for p in get_catalog(shop)["items"] if p["group"] == product.group and p["code"] != product.code]
	same.sort(key=lambda p: not p["in_stock"])
	return same[:limit]


def get_variant_options(template, warehouse):
	"""{'colors': [{value, hex}], 'sizes': [..], 'variants': {'Oq|M': {code, qty, price}}} — faqat faol variantlar.
	price — variantning o'z narxi (rang/o'lcham bo'yicha har xil bo'lishi mumkin)."""
	from marketplace.setup import COLOR_ATTR, SIZE_ATTR

	variants = frappe.get_all(
		"Item", filters={"variant_of": template.name, "disabled": 0}, pluck="name"
	)
	attrs = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", variants or [""]], "parenttype": "Item"},
		fields=["parent", "attribute", "attribute_value"],
	)
	stock = _get_stock(variants, warehouse) if variants else {}
	by_variant = {}
	for a in attrs:
		by_variant.setdefault(a.parent, {})[a.attribute] = a.attribute_value

	order = {}
	for attr in (COLOR_ATTR, SIZE_ATTR):
		order[attr] = frappe.get_all(
			"Item Attribute Value", filters={"parent": attr}, fields=["attribute_value", "color_hex"], order_by="idx asc"
		)
	used_colors = {v.get(COLOR_ATTR) for v in by_variant.values()}
	used_sizes = {v.get(SIZE_ATTR) for v in by_variant.values()}
	# Rang namunasi rasmi: galereyada shu rangga bog'langan birinchi rasm, bo'lmasa (eski usul) variantning rasmi
	tagged = {}
	names = color_names([g.get("rang") for g in template.get("gallery") or []])
	for g in template.get("gallery") or []:
		if g.get("rang"):
			tagged.setdefault(names[g.rang], g.medium or g.image)
	# Doiracha rangi — do'konning o'z Rang yozuvidan (ikki do'konda "Oq" har xil bo'lishi mumkin)
	hexes = shop_hexes(template.shop)
	pictures = {
		g.parent: g.medium or g.image
		for g in frappe.get_all(
			"Item Gallery", filters={"parent": ["in", variants or [""]], "parenttype": "Item", "idx": 1},
			fields=["parent", "medium", "image"],
		)
	}
	color_image = {}
	for code, v in by_variant.items():
		if pictures.get(code) and v.get(COLOR_ATTR):
			color_image.setdefault(v[COLOR_ATTR], pictures[code])
	colors = [
		{"value": r.attribute_value, "hex": hexes.get(r.attribute_value) or "#ccc", "image": tagged.get(r.attribute_value) or color_image.get(r.attribute_value)}
		for r in order[COLOR_ATTR]
		if r.attribute_value in used_colors
	]
	# Raqamli o'lchamlar (36, 41, 42.5) — o'sish tartibida, harfli (S, M, L) — platforma ro'yxati tartibida
	from marketplace.seller_desk import shop_sizes

	own = shop_sizes(template.shop)
	rank = {v: i for i, v in enumerate(own or [r.attribute_value for r in order[SIZE_ATTR]])}
	sizes = sorted((s for s in used_sizes if s), key=lambda s: _size_key(s, rank))

	prices = _get_prices(variants) if variants else {}
	variants_map = {
		f"{v.get(COLOR_ATTR) or ''}|{v.get(SIZE_ATTR) or ''}": {
			"code": code, "qty": max(cint(stock.get(code, 0)), 0), "price": prices.get(code),
		}
		for code, v in by_variant.items()
	}
	return {"colors": colors, "sizes": sizes, "variants": variants_map}


def _size_key(size, rank):
	"""Do'kon ro'yxatidagi tartib; ro'yxatda yo'qlari — raqamlilari o'sish tartibida, keyin qolganlari."""
	if size in rank:
		return (0, rank[size], 0, size)
	try:
		return (1, 0, float(size.replace(",", ".")), size)
	except ValueError:
		return (2, 0, 0, size)


def get_cart_lines(shop, lines, held=None):
	"""Savatdagi tovarlarning HOZIRGI narxi va qoldig'i. Brauzerdagi narxga ishonilmaydi.
	held: {kod: soni} — mijozning o'z to'lanmagan buyurtmasi zaxiralagani (qayta rasmiylashtirganda bo'shaydi),
	shuning uchun savatda "tugagan" bo'lib ko'rinmasin."""
	qty_by_code = {}
	for line in lines or []:
		code, qty = line.get("code"), cint(line.get("qty"))
		if code and qty > 0:
			qty_by_code[code] = min(qty_by_code.get(code, 0) + qty, 99)

	if not qty_by_code:
		return []

	items = frappe.get_all(
		"Item",
		filters={"name": ["in", list(qty_by_code)], "shop": shop.name, "is_published": 1, "disabled": 0, "has_variants": 0},
		fields=["name", "item_name", "image", "is_stock_item", "wholesale_price", "wholesale_min_qty", "variant_of", "mp_tez_kunda",
		        "old_price"],
	)
	codes = [i.name for i in items]
	prices = _get_prices(codes)
	stock = _get_stock(codes, shop.warehouse)
	templates = {i.variant_of for i in items if i.variant_of}
	thumbs = _get_thumbnails(codes + list(templates))
	tpl = {
		t.name: t
		for t in frappe.get_all(
			"Item", filters={"name": ["in", list(templates) or [""]]},
			fields=["name", "item_name", "image", "wholesale_price", "wholesale_min_qty", "mp_tez_kunda", "old_price"],
		)
	}
	labels = variant_labels([i.name for i in items if i.variant_of])
	color_thumbs = _color_thumbs([i.name for i in items if i.variant_of])

	out = []
	for i in items:
		if i.name not in prices:
			continue
		base = tpl.get(i.variant_of) or i
		if base.mp_tez_kunda:
			continue  # "Tez kunda" — sotilmaydi: savatga tushmaydi, buyurtma ham bo'lmaydi
		available = cint(stock.get(i.name, 0) + (held or {}).get(i.name, 0)) if i.is_stock_item else 99
		qty = min(qty_by_code[i.name], available)
		if qty <= 0:
			continue  # tugagan tovar savatdan tushib qoladi
		ws = _wholesale(base, prices[i.name])
		price = unit_price(prices[i.name], ws, qty)
		# Chegirmasiz narx (saytdagi chizilgan eski narx, bo'lmasa oddiy narx) — savatda "Chegirma: −X so'm" shundan
		old = flt(base.old_price)
		out.append(
			{
				"code": i.name,
				"name": base.item_name,
				"variant": labels.get(i.name),
				"template": i.variant_of,
				"price": price,
				"retail_price": prices[i.name],
				"is_wholesale": price != prices[i.name],
				"list_price": old if old > prices[i.name] else prices[i.name],
				"qty": qty,
				"max_qty": available,
				"thumb": color_thumbs.get(i.name) or thumbs.get(i.name) or thumbs.get(i.variant_of) or base.image or i.image,
				"amount": price * qty,
				**ws,
			}
		)
	return out


def _color_thumbs(variants):
	"""{variant: rasm} — andoza galereyasida variant rangiga bog'langan birinchi rasm (savatda qora tanlangan bo'lsa, qora)."""
	from marketplace.setup import COLOR_ATTR

	if not variants:
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", variants]}, fields=["name", "variant_of"]
	)
	colors = dict(
		frappe.get_all(
			"Item Variant Attribute",
			filters={"parent": ["in", variants], "parenttype": "Item", "attribute": COLOR_ATTR},
			fields=["parent", "attribute_value"],
			as_list=True,
		)
	)
	gallery = frappe.get_all(
		"Item Gallery",
		filters={"parent": ["in", list({r.variant_of for r in rows}) or [""]], "parenttype": "Item", "rang": ["is", "set"]},
		fields=["parent", "rang", "thumbnail", "image"],
		order_by="idx asc",
	)
	# Galereyada Rang ID ("Oq (clothes)"), variantda nomi ("Oq")
	names = color_names([g.rang for g in gallery])
	pics = {}
	for g in gallery:
		pics.setdefault((g.parent, names[g.rang]), g.thumbnail or g.image)
	return {r.name: pics.get((r.variant_of, colors.get(r.name))) for r in rows if pics.get((r.variant_of, colors.get(r.name)))}


def variant_labels(codes):
	"""{'kod': 'Oq · M'} — atributlar platforma tartibida (avval rang, keyin o'lcham)."""
	from marketplace.setup import COLOR_ATTR, SIZE_ATTR

	# Qiymati bo'sh qator — variantsiz tovardagi (yoki hali to'ldirilmagan) atribut, yorliqqa kirmaydi
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", codes or [""]], "parenttype": "Item", "attribute_value": ["is", "set"]},
		fields=["parent", "attribute", "attribute_value"],
	)
	rank = {COLOR_ATTR: 0, SIZE_ATTR: 1}
	parts = {}
	for r in sorted(rows, key=lambda r: rank.get(r.attribute, 9)):
		if r.attribute_value:
			parts.setdefault(r.parent, []).append(r.attribute_value)
	return {k: " · ".join(v) for k, v in parts.items()}


def _get_variant_stock(templates, warehouse):
	"""Asosiy mahsulot qoldig'i = faol variantlari qoldig'i yig'indisi."""
	if not templates:
		return {}
	variants = frappe.get_all("Item", filters={"variant_of": ["in", templates], "disabled": 0}, fields=["name", "variant_of"])
	stock = _get_stock([v.name for v in variants], warehouse) if variants else {}
	out = {}
	for v in variants:
		out[v.variant_of] = out.get(v.variant_of, 0) + max(stock.get(v.name, 0), 0)
	return out


def _wholesale(item, retail):
	price = flt(item.get("wholesale_price"))
	if not price or price >= retail:
		return {"wholesale_price": None, "wholesale_min": None}
	return {"wholesale_price": price, "wholesale_min": cint(item.get("wholesale_min_qty")) or 10}


def unit_price(retail, ws, qty):
	"""Bitta qoida hamma joyda (savat, buyurtma): soni ulgurji chegaraga yetsa — ulgurji narx."""
	if ws.get("wholesale_price") and qty >= ws["wholesale_min"]:
		return ws["wholesale_price"]
	return retail


def clear_catalog_cache(doc, method=None):
	"""Item / Item Price hook: o'sha do'kon katalogini keshdan o'chiradi."""
	shop = doc.get("shop")
	if not shop and doc.doctype == "Item Price":
		shop = frappe.db.get_value("Item", doc.item_code, "shop")
	if shop:
		frappe.cache.delete_value(_cache_key(shop))


def _cache_key(shop_name):
	# Tuzilma o'zgarsa versiyani oshiring: eski kesh avtomatik e'tiborsiz qoladi
	return f"marketplace:catalog:v5:{shop_name}"


def _selling_price_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"


def _soon_price(item):
	""""Tez kunda" tovar: narx ro'yxatida (Item Price) narxi yo'q — variantlari hali yaratilmagan bo'lishi mumkin.
	Saytda formadagi narx ko'rinadi: "Sotish narxi (barcha variantlarga)" yoki oddiy tovar narxi. Sotilmaydi."""
	return flt(item.get("variant_price")) or flt(item.get("standard_rate"))


def _get_prices(codes):
	rows = frappe.get_all(
		"Item Price",
		filters={"item_code": ["in", codes], "price_list": _selling_price_list(), "selling": 1},
		fields=["item_code", "price_list_rate"],
		order_by="valid_from desc",
	)
	prices = {}
	for r in rows:
		prices.setdefault(r.item_code, flt(r.price_list_rate))
	missing = [c for c in codes if c not in prices]
	if missing:
		# Variantli mahsulot (template): narx variantlarda turadi — eng kichigini olamiz
		children = frappe.get_all("Item", filters={"variant_of": ["in", missing], "disabled": 0}, fields=["name", "variant_of"])
		if children:
			child_prices = _get_prices([c.name for c in children])
			for c in children:
				if c.name in child_prices:
					prices[c.variant_of] = min(prices.get(c.variant_of, child_prices[c.name]), child_prices[c.name])
	return prices


def _varying_prices(templates):
	"""Variantlari har xil narxdagi andozalar (Desk'da rang/o'lcham bo'yicha alohida narx qo'yilgan)."""
	children = frappe.get_all("Item", filters={"variant_of": ["in", templates or [""]], "disabled": 0}, fields=["name", "variant_of"])
	prices = _get_prices([c.name for c in children]) if children else {}
	seen = {}
	for c in children:
		if c.name in prices:
			seen.setdefault(c.variant_of, set()).add(prices[c.name])
	return {t for t, values in seen.items() if len(values) > 1}


def _get_stock(codes, warehouse):
	if not warehouse:
		return {}
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": ["in", codes], "warehouse": warehouse},
		fields=["item_code", "actual_qty", "reserved_qty"],
	)
	return {r.item_code: flt(r.actual_qty) - flt(r.reserved_qty) for r in rows}


def _link_banner_items(shop, banners):
	"""Reklama slaydi: tanlangan tovar shu do'konniki va saytda bo'lsa — tugma uning sahifasini ochadi.

	Tovar yashirilsa yoki o'chirilsa slayd qoladi, tugma kategoriyaga (yoki umuman yo'q) qaytadi."""
	codes = {b.item for b in banners if b.get("item")}
	if not codes:
		return
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", list(codes)], "shop": shop, "is_published": 1, "disabled": 0},
		fields=["name", "variant_of"],
	)
	live = {r.name: r.variant_of or r.name for r in rows}
	for b in banners:
		code = live.get(b.get("item"))
		if code:
			b.url = f"/s/{shop}/p/{code}"
			b.button = b.button_label or "Tovarni ko‘rish"


def _carousel_items(shop):
	"""Sotuvchi tovar formasida "Karuselga qo'shish" belgilagan tovarlar: rasm + nom + havola."""
	items = frappe.get_all(
		"Item",
		filters={"shop": shop, "in_carousel": 1, "is_published": 1, "disabled": 0, "variant_of": ["is", "not set"]},
		fields=["name", "item_name", "image", "carousel_label"],
		order_by="modified desc",
		limit=6,
	)
	gallery = _get_gallery([i.name for i in items]) if items else {}
	return [
		frappe._dict(
			image=(gallery.get(i.name) or [i.image])[0],
			label=i.carousel_label,
			title=i.item_name,
			url=f"/s/{shop}/p/{i.name}",
			is_item=1,
		)
		for i in items
		if (gallery.get(i.name) or [i.image])[0]
	]


def _get_gallery(codes):
	rows = frappe.get_all(
		"Item Gallery",
		filters={"parent": ["in", codes], "parenttype": "Item"},
		fields=["parent", "medium", "image"],
		order_by="idx asc",
	)
	out = {}
	for r in rows:
		if r.medium or r.image:  # faqat video bo'lgan qator kartaga chiqmaydi
			out.setdefault(r.parent, []).append(r.medium or r.image)
	return out


def _get_thumbnails(codes):
	rows = frappe.get_all(
		"Item Gallery",
		filters={"parent": ["in", codes], "parenttype": "Item"},
		fields=["parent", "thumbnail", "image", "idx"],
		order_by="idx asc",
	)
	out = {}
	for r in rows:
		if r.thumbnail or r.image:
			out.setdefault(r.parent, r.thumbnail or r.image)
	return out


def fmt_sum(value):
	"""189000 -> '189 000 so‘m' (Jinja'da: {{ fmt_sum(price) }})"""
	return f"{flt(value):,.0f}".replace(",", " ") + " so‘m"


def asset_version():
	"""CSS/JS o'zgarganda brauzer eski nusxani keshdan olmasligi uchun (?v=...)."""
	import os

	public = frappe.get_app_path("marketplace", "public")
	return int(
		max(
			os.path.getmtime(os.path.join(public, p))
			for p in ("css/storefront.css", "js/storefront.js", "css/panel.css", "js/panel.js")
			if os.path.exists(os.path.join(public, p))
		)
	)


def _plain_text(html):
	"""Desk'dagi Text Editor HTML saqlaydi; mijozga faqat toza matn (qator ko'chirishlari bilan)."""
	import re

	from frappe.utils import strip_html

	if not html:
		return ""
	text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
	return re.sub(r"\n{3,}", "\n\n", strip_html(text)).strip()
