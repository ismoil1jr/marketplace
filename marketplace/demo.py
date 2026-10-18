"""Demo ma'lumot: Nafis Tekstil do'koni uchun PDF dizayndagi 8 ta tovar.

Ishga tushirish (qayta ishga tushirsa ham xavfsiz — bor narsani qayta yaratmaydi):
    bench --site marketplace.local execute marketplace.demo.seed
"""

import frappe
from frappe.utils.file_manager import save_file

SHOP = "nafis-tekstil"

GROUPS = ["Ko‘ylaklar", "Futbolkalar", "Shimlar", "Kurtkalar", "Sviterlar", "Bolalar"]

# (kod, nom, kategoriya, narx, eski narx, qoldiq, shakl, fon, kiyim rangi, tavsif)
PRODUCTS = [
	("zigir-koylak-oq", "Zig‘ir ko‘ylak, oq", "Ko‘ylaklar", 189000, 0, 14, "shirt", "#E7E2D6", "#FBFAF5",
	 "100% zig‘ir mato, erkin bichim.\n30°C da mashinada yuvish mumkin."),
	("paxta-futbolka", "Paxta futbolka", "Futbolkalar", 89000, 119000, 40, "tshirt", "#DCE5DF", "#7F9A86",
	 "Yumshoq 100% paxta, 180 g/m².\nYuvilganda kirishmaydi."),
	("klassik-shim", "Klassik shim", "Shimlar", 245000, 0, 9, "pants", "#E2E0EA", "#4B4F63",
	 "Klassik to‘g‘ri bichim, kostyum matosi.\nOfis va kundalik kiyim uchun."),
	("bolalar-kurtkasi", "Bolalar kurtkasi", "Bolalar", 310000, 0, 3, "jacket", "#EFE0D8", "#C9775A",
	 "Yengil, suv o‘tkazmaydigan.\n4–10 yosh uchun."),
	("jun-sviter", "Jun sviter", "Sviterlar", 275000, 0, 11, "sweater", "#E6E1D4", "#9C8A6A",
	 "Merinos juni aralash, issiq va yengil."),
	("zigir-shim", "Zig‘ir shim", "Shimlar", 199000, 0, 17, "pants", "#DFE3E6", "#C8B79A",
	 "Yozgi zig‘ir shim, belida rezinka."),
	("paxta-pijama", "Paxta pijama", "Bolalar", 165000, 0, 22, "pajama", "#EAE0E6", "#B98AA2",
	 "Bolalar uchun yumshoq paxta pijama."),
	("trikotaj-kardigan", "Trikotaj kardigan", "Sviterlar", 229000, 0, 0, "cardigan", "#E4E6DA", "#7C8461",
	 "Trikotaj kardigan, yog‘och tugmalar."),
]


def seed():
	frappe.flags.in_demo = True
	setup_groups()
	shop = setup_shop()
	created = [make_item(p) for p in PRODUCTS]
	order_like_design(created)
	add_stock(shop, created)
	frappe.db.commit()
	frappe.cache.delete_value(f"marketplace:catalog:v4:{SHOP}")
	print(f"Tayyor: /s/{SHOP} — {len(created)} ta tovar")


def setup_groups():
	if not frappe.db.exists("Item Group", "Kiyim"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "Kiyim", "parent_item_group": "All Item Groups", "is_group": 1}).insert()
	for g in GROUPS:
		if not frappe.db.exists("Item Group", g):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": g, "parent_item_group": "Kiyim"}).insert()


def setup_shop():
	shop = frappe.get_doc("Shop", SHOP)
	shop.update(
		{
			"status": "Active",
			"tagline": "Tabiiy matolardan kundalik kiyimlar",
			"city": "Toshkent",
			"instagram": "nafis.tekstil",
			"delivery_short": "1–2 kunda yetkazish",
			"delivery_info": "Toshkent bo‘ylab 1–2 kunda yetkaziladi",
			"banner_label": "Yangi kolleksiya",
			"banner_title": "Kuzgi ko‘ylaklar",
			"banner_group": "Ko‘ylaklar",
			"enable_payme": 1,
			"enable_click": 1,
			"enable_cod": 1,
		}
	)
	if not shop.cover_image:
		shop.cover_image = _save_svg("cover-nafis.svg", banner_svg(bg="#3A4A40"), "Shop", shop.name)
	if not shop.banner_image:
		shop.banner_image = _save_svg("banner-kuzgi-koylaklar.svg", banner_svg(), "Shop", shop.name)
	shop.save()
	return shop


def make_item(p):
	code, name, group, price, old, qty, shape, bg, fg, desc = p
	item_code = f"{SHOP}-{code}"
	if frappe.db.exists("Item", item_code):
		return frappe.get_doc("Item", item_code), qty

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": name,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"shop": SHOP,
			"is_published": 1,
			"mxik_code": "06109100001000000",
			"old_price": old,
			"description": desc.replace("\n", "<br>"),
		}
	)
	item.insert()
	alt_bg = _mix(bg, fg, 0.18)
	for i, (b, zoom) in enumerate(((bg, False), (alt_bg, True))):
		url = _save_svg(f"{code}-{i + 1}.svg", garment_svg(shape, b, fg, zoom), "Item", item.name)
		item.append("gallery", {"image": url})
	item.save()

	frappe.get_doc(
		{"doctype": "Item Price", "item_code": item.name, "price_list": "Standard Selling", "price_list_rate": price}
	).insert()
	return item, qty


def order_like_design(created):
	"""Katalog "Yangilari" bo'yicha saralanadi: PDF'dagi birinchi tovar eng yangi bo'lsin."""
	from frappe.utils import add_to_date, now_datetime

	base = now_datetime()
	for i, (item, _qty) in enumerate(created):
		frappe.db.set_value("Item", item.name, "creation", add_to_date(base, minutes=-i), update_modified=False)


def add_stock(shop, created):
	rows = [
		{"item_code": item.name, "warehouse": shop.warehouse, "qty": qty, "valuation_rate": 1}
		for item, qty in created
		if qty and not frappe.db.exists("Bin", {"item_code": item.name, "warehouse": shop.warehouse})
	]
	if rows:
		frappe.get_doc(
			{"doctype": "Stock Reconciliation", "company": frappe.defaults.get_global_default("company"),
			 "purpose": "Stock Reconciliation", "items": rows}
		).submit()


def _save_svg(fname, svg, dt, dn):
	return save_file(fname, svg.encode(), dt, dn, is_private=0).file_url


# ---------------- SVG rasmlar ----------------

SHAPES = {
	"tshirt": "M140 112 L104 124 L58 172 L94 212 L124 188 L124 404 L276 404 L276 188 L306 212 L342 172 L296 124 L260 112 Q200 152 140 112 Z",
	"long": "M140 112 L104 124 L72 182 L52 334 L88 340 L112 218 L124 204 L124 404 L276 404 L276 204 L288 218 L312 340 L348 334 L328 182 L296 124 L260 112 Q200 152 140 112 Z",
	"pants": "M136 104 L264 104 L284 412 L224 412 L200 196 L176 412 L116 412 Z",
}


def garment_svg(shape, bg, fg, zoom=False):
	shade = _mix(fg, "#000000", 0.18)
	line = f'stroke="{shade}" stroke-width="3" fill="none" stroke-linecap="round"'
	body = SHAPES["pants"] if shape == "pants" else SHAPES["tshirt"] if shape in ("tshirt", "pajama") else SHAPES["long"]
	extra = ""
	if shape == "shirt":
		extra = (
			f'<path d="M140 112 L176 168 L200 140 L224 168 L260 112" {line}/>'
			f'<path d="M200 140 L200 404" {line}/>'
			+ "".join(f'<circle cx="208" cy="{y}" r="4" fill="{shade}"/>' for y in (186, 230, 274, 318, 362))
		)
	elif shape == "pants":
		extra = f'<path d="M136 128 L264 128" {line}/><path d="M200 128 L200 196" {line}/>'
	elif shape == "jacket":
		extra = (
			f'<path d="M200 140 L200 404" {line}/>'
			+ "".join(f'<path d="M124 {y} L276 {y}" {line} opacity=".55"/>' for y in (190, 240, 290, 340))
			+ f'<path d="M150 112 Q200 70 250 112" {line}/>'
		)
	elif shape == "sweater":
		extra = f'<path d="M124 384 L276 384" {line}/><path d="M60 318 L90 324 M310 324 L340 318" {line}/>'
	elif shape == "cardigan":
		extra = (
			f'<path d="M140 112 L200 220 L260 112" {line}/><path d="M200 220 L200 404" {line}/>'
			+ "".join(f'<circle cx="210" cy="{y}" r="5" fill="{shade}"/>' for y in (250, 300, 350))
		)
	elif shape == "pajama":
		extra = "".join(f'<path d="M124 {y} L276 {y}" stroke="#fff" stroke-width="7" opacity=".45"/>' for y in (200, 250, 300, 350))
	elif shape == "tshirt":
		extra = f'<path d="M150 116 Q200 150 250 116" {line}/>'

	view = "90 90 220 275" if zoom else "0 0 400 500"
	return (
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" width="800" height="1000" preserveAspectRatio="xMidYMid slice">'
		f'<rect x="-200" y="-200" width="800" height="900" fill="{bg}"/>'
		f'<ellipse cx="200" cy="430" rx="120" ry="12" fill="#000" opacity=".06"/>'
		f'<path d="{body}" fill="{fg}" stroke="{shade}" stroke-width="2" stroke-linejoin="round"/>'
		f"{extra}</svg>"
	)


def banner_svg(bg="#C9D8CF"):
	items = [("shirt", "#FBFAF5", -150), ("shirt", "#C8B79A", 150), ("shirt", "#7F9A86", 450)]
	groups = ""
	for shape, fg, x in items:
		inner = garment_svg(shape, "none", fg).split(">", 1)[1].rsplit("</svg>", 1)[0]
		inner = inner.replace('fill="none"/>', 'fill="none" opacity="0"/>', 1)
		groups += f'<g transform="translate({x + 300} 20) scale(.9)">{inner}</g>'
	return (
		'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 560" width="1200" height="560">'
		f'<rect width="1200" height="560" fill="{bg}"/>{groups}</svg>'
	)


def _mix(a, b, t):
	a, b = a.lstrip("#"), b.lstrip("#")
	ca = [int(a[i : i + 2], 16) for i in (0, 2, 4)]
	cb = [int(b[i : i + 2], 16) for i in (0, 2, 4)]
	return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb, strict=True))


# ---------------- C shablon demo: Bunyod Mebel (ulgurji katalog) ----------------

MEBEL_SHOP = "bunyod-mebel"
MEBEL_GROUPS = ["Stollar", "Stullar", "Shkaflar", "Ofis to‘plami"]

# (kod, nom, kategoriya, narx, ulgurji, qoldiq, xususiyat, shakl, fon)
MEBEL = [
	("ofis-stoli-prime", "Ofis stoli Prime", "Stollar", 1450000, 1290000, 34, "Laminat, 120×60 sm", "desk", "#E6EAF1"),
	("kompyuter-stoli-lite", "Kompyuter stoli Lite", "Stollar", 890000, 790000, 58, "LDSP, 100×55 sm", "desk", "#EEEAE3"),
	("ofis-stuli-ergo", "Ofis stuli Ergo", "Stullar", 720000, 640000, 120, "To‘r, gaz-lift", "chair", "#E3ECE8"),
	("kitob-javoni", "Kitob javoni", "Shkaflar", 640000, 570000, 12, "LDSP, 80×30×180 sm", "shelf", "#F0E8E2"),
	("mehmon-stuli", "Mehmon stuli", "Stullar", 310000, 275000, 200, "Metall karkas", "stool", "#E9E7EF"),
	("hujjat-shkafi", "Hujjat shkafi", "Shkaflar", 1180000, 1050000, 0, "LDSP, 2 eshikli, 90×40×200 sm", "cabinet", "#E8EBE4"),
	("rahbar-toplami", "Rahbar to‘plami", "Ofis to‘plami", 6900000, 6200000, 5, "Stol + kreslo + tumba", "desk", "#E4E9F0"),
]


def seed_mebel():
	frappe.flags.in_demo = True
	if not frappe.db.exists("Item Group", "Mebel"):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": "Mebel", "parent_item_group": "All Item Groups", "is_group": 1}).insert()
	for g in MEBEL_GROUPS:
		if not frappe.db.exists("Item Group", g):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": g, "parent_item_group": "Mebel"}).insert()

	shop = frappe.get_doc("Shop", MEBEL_SHOP)
	shop.update({
		"status": "Active", "layout_style": "katalog", "brand_color": "#2B4A7A",
		"tagline": "Ishlab chiqaruvchi", "city": "Namangan", "instagram": "bunyod.mebel",
		"delivery_short": "O‘zbekiston bo‘ylab", "delivery_info": "O‘zbekiston bo‘ylab 3–5 kunda, Namanganda 1 kunda",
		"enable_payme": 1, "enable_click": 1, "enable_cod": 1,
	})
	shop.save()
	frappe.db.set_value("Item", {"shop": MEBEL_SHOP, "name": ["like", "%futbolka%"]}, "disabled", 1)

	created = []
	for i, (code, name, group, price, ws, qty, spec, shape, bg) in enumerate(MEBEL):
		item_code = f"{MEBEL_SHOP}-{code}"
		if frappe.db.exists("Item", item_code):
			created.append((frappe.get_doc("Item", item_code), qty))
			continue
		item = frappe.get_doc({
			"doctype": "Item", "item_code": code, "item_name": name, "item_group": group, "stock_uom": "Nos",
			"is_stock_item": 1, "shop": MEBEL_SHOP, "is_published": 1, "mxik_code": "09403300001000000",
			"spec_line": spec, "wholesale_price": ws, "wholesale_min_qty": 10,
		}).insert()
		url = _save_svg(f"{code}.svg", furniture_svg(shape, bg, "#3B4A63"), "Item", item.name)
		item.append("gallery", {"image": url})
		item.save()
		frappe.get_doc({"doctype": "Item Price", "item_code": item.name, "price_list": "Standard Selling", "price_list_rate": price}).insert()
		created.append((item, qty))
	order_like_design(created)
	add_stock(shop, created)
	frappe.db.commit()
	frappe.cache.delete_value(f"marketplace:catalog:v4:{MEBEL_SHOP}")
	print(f"Tayyor: /s/{MEBEL_SHOP} — {len(created)} ta tovar (C shablon)")


def furniture_svg(shape, bg, fg):
	wood = "#B98B5E"
	parts = {
		"desk": f'<rect x="70" y="190" width="260" height="22" rx="4" fill="{wood}"/>'
		f'<rect x="88" y="212" width="14" height="140" fill="{fg}"/><rect x="298" y="212" width="14" height="140" fill="{fg}"/>'
		f'<rect x="220" y="212" width="78" height="90" rx="4" fill="{wood}" opacity=".85"/>',
		"chair": f'<rect x="140" y="110" width="120" height="120" rx="18" fill="{fg}"/>'
		f'<rect x="130" y="235" width="140" height="30" rx="12" fill="{fg}"/>'
		f'<rect x="194" y="265" width="12" height="60" fill="#8A93A6"/>'
		f'<path d="M200 325 L130 350 M200 325 L270 350 M200 325 L200 356" stroke="#8A93A6" stroke-width="10" stroke-linecap="round"/>',
		"shelf": f'<rect x="125" y="80" width="150" height="280" rx="4" fill="{wood}"/>'
		+ "".join(f'<rect x="137" y="{y}" width="126" height="54" fill="#F3EDE5"/>' for y in (92, 158, 224, 290))
		+ "".join(f'<rect x="{x}" y="{y}" width="12" height="40" fill="{fg}" opacity=".7"/>' for x, y in ((145, 104), (160, 108), (175, 104), (210, 236), (225, 240)))
		,
		"stool": f'<rect x="150" y="150" width="100" height="90" rx="10" fill="{fg}"/>'
		f'<rect x="140" y="240" width="120" height="22" rx="8" fill="{fg}"/>'
		f'<path d="M152 262 L140 350 M248 262 L260 350" stroke="#8A93A6" stroke-width="8" stroke-linecap="round"/>',
		"cabinet": f'<rect x="120" y="70" width="160" height="290" rx="6" fill="{wood}"/>'
		f'<line x1="200" y1="78" x2="200" y2="352" stroke="#8C6640" stroke-width="3"/>'
		f'<circle cx="188" cy="215" r="5" fill="{fg}"/><circle cx="212" cy="215" r="5" fill="{fg}"/>',
	}
	return (
		'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="800" height="800">'
		f'<rect width="400" height="400" fill="{bg}"/><ellipse cx="200" cy="362" rx="130" ry="10" fill="#000" opacity=".06"/>'
		f"{parts[shape]}</svg>"
	)
