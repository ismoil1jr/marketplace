"""Google uchun: sitemap, robots.txt, canonical, meta tavsif va JSON-LD (schema.org).

Hamma do'konlar bir xil — yangi do'kon ochilsa yoki tovar qo'shilsa, sitemap'ga o'zi tushadi.
"""

import re
from urllib.parse import quote

import frappe
from frappe.utils import flt, get_url

SITE_NAME = "Magazinlar"
DESC_LEN = 160

# Google'ga kerak emas: kabinet, API, kirish, shaxsiy sahifalar (savat/buyurtma noindex bilan ham yopiladi)
ROBOTS_DISALLOW = ("/desk", "/app", "/admin", "/api/", "/panel", "/login", "/update-password", "/me", "/print")


def abs_url(path):
	"""/files/x.jpg -> https://magazinlar.uz/files/x.jpg (tayyor http(s) havola o'zgarmaydi)."""
	if not path:
		return None
	if re.match(r"^https?://", path):
		return path
	return get_url(quote(path if path.startswith("/") else "/" + path, safe="/?=&%:"))


def shop_url(shop_name, *parts):
	return abs_url("/".join(["/s", shop_name, *parts]))


def meta_text(*chunks, limit=DESC_LEN):
	"""Bir nechta matnni bitta qatorga yig'adi va so'z chegarasida qisqartiradi (meta description uchun)."""
	text = " ".join(re.sub(r"\s+", " ", c or "").strip(" .") + "." for c in chunks if c and c.strip())
	text = text.strip()
	if len(text) <= limit:
		return text
	cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
	return cut + "…"


def name_list(names, limit=90):
	"""Takrorsiz nomlar, vergul bilan, limit belgigacha — butun nom bo'yicha (so'z o'rtasida kesilmaydi)."""
	out, size = [], 0
	for n in dict.fromkeys(n.strip() for n in names if n and n.strip()):
		if out and size + len(n) + 2 > limit:
			break
		out.append(n)
		size += len(n) + 2
	return ", ".join(out)


def jsonld(*objs):
	"""Sahifadagi <script type="application/ld+json"> uchun @graph."""
	return {"@context": "https://schema.org", "@graph": [o for o in objs if o]}


def breadcrumbs(*crumbs):
	"""crumbs: (nom, to'liq url) — Google natijada «magazinlar.uz › Pandoo › Panda books» ko'rsatadi."""
	return {
		"@type": "BreadcrumbList",
		"itemListElement": [
			{"@type": "ListItem", "position": i, "name": name, "item": url}
			for i, (name, url) in enumerate(crumbs, start=1)
		],
	}


def shop_schema(shop, url, products=()):
	"""Do'kon sahifasi: OnlineStore + uning Instagram/Telegram... (sameAs — Google ularni bitta brend deb biladi)."""
	names = [p["name"] for p in products][:6]
	return _clean({
		"@type": "OnlineStore",
		"@id": url + "#store",
		"name": shop.shop_name,
		"url": url,
		"description": meta_text(shop.tagline, ", ".join(names) if names else None, limit=300) or None,
		"logo": abs_url(shop.logo),
		"image": abs_url(shop.cover_image or shop.logo),
		"telephone": shop.phone or None,
		"address": {"@type": "PostalAddress", "addressLocality": shop.city, "addressCountry": "UZ"} if shop.city else None,
		"sameAs": [s["href"] for s in shop.get("socials") or []] or None,
		"parentOrganization": {"@id": get_url("/") + "#org"},
	})


def product_schema(shop, product, url):
	"""Mahsulot: nomi, rasmlari, narxi (UZS) va bor-yo'qligi — Google rasm/narx bilan ko'rsatishi mumkin."""
	data = {
		"@type": "Product",
		"@id": url + "#product",
		"name": product.name,
		"sku": product.code,
		"url": url,
		"image": [abs_url(i) for i in (product.images or [])[:6]] or ([abs_url(product.thumb)] if product.thumb else None),
		"description": meta_text(product.description, limit=1000) or None,
		"category": product.group or None,
	}
	if flt(product.price) > 0 and not product.no_price:
		if product.coming_soon:
			availability = "https://schema.org/PreOrder"
		else:
			availability = "https://schema.org/InStock" if product.in_stock else "https://schema.org/OutOfStock"
		data["offers"] = {
			"@type": "Offer",
			"url": url,
			"priceCurrency": "UZS",
			"price": f"{flt(product.price):.0f}",
			"availability": availability,
			"itemCondition": "https://schema.org/NewCondition",
			"seller": {"@type": "Organization", "name": shop.shop_name, "url": shop_url(shop.name)},
		}
	return _clean(data)


def site_schema(phone=None, logo=None):
	"""Bosh sahifa: sayt nomi «Magazinlar» (Google natijada shunday yozadi) va kompaniya."""
	home = get_url("/")
	return [
		{
			"@type": "WebSite",
			"@id": home + "#website",
			"name": SITE_NAME,
			"alternateName": ["magazinlar.uz", "Magazinlar.uz"],
			"url": home,
			"inLanguage": ["uz", "ru"],
			"publisher": {"@id": home + "#org"},
		},
		_clean(
			{
				"@type": "Organization",
				"@id": home + "#org",
				"name": "magazinlar.uz",
				"legalName": "ORANGE TEAM MChJ",
				"url": home,
				"logo": logo,
				"telephone": phone or None,
			}
		),
	]


def _clean(d):
	return {k: v for k, v in d.items() if v not in (None, "", [], {})}


def sitemap_links():
	"""Bosh sahifa, har bir faol do'kon va uning saytdagi har bir tovari (variantlar — shablon sahifasida)."""
	links = [{"loc": get_url("/"), "lastmod": None, "priority": "1.0"}]
	shops = frappe.get_all("Shop", filters={"status": "Active"}, fields=["name", "modified"], order_by="name asc")
	if not shops:
		return links
	items = frappe.db.sql(
		"""select name, shop, modified from `tabItem`
		where is_published = 1 and disabled = 0 and ifnull(variant_of, '') = '' and shop in %(shops)s
		order by shop, name""",
		{"shops": [s.name for s in shops]},
		as_dict=True,
	)
	by_shop = {}
	for it in items:
		by_shop.setdefault(it.shop, []).append(it)
	for s in shops:
		own = by_shop.get(s.name, [])
		last = max([s.modified] + [it.modified for it in own])
		links.append({"loc": shop_url(s.name), "lastmod": f"{last:%Y-%m-%d}", "priority": "0.9"})
		links.extend(
			{"loc": shop_url(s.name, "p", it.name), "lastmod": f"{it.modified:%Y-%m-%d}", "priority": "0.8"}
			for it in own
		)
	return links


def robots_txt():
	lines = ["User-agent: *", *(f"Disallow: {p}" for p in ROBOTS_DISALLOW), "", f"Sitemap: {get_url('/sitemap.xml')}"]
	extra = (frappe.db.get_single_value("Website Settings", "robots_txt") or "").strip()
	if extra:  # admin Website Settings'da qo'shimcha qoida yozgan bo'lsa — oxiriga
		lines += ["", extra]
	return "\n".join(lines) + "\n"
