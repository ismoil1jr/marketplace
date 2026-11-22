import frappe

from marketplace import customers, seo, storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	catalog = storefront.get_catalog(shop)

	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog = catalog
	context.highlights = storefront.get_highlights(catalog) if shop.layout == "story" else []
	# Ustma-ust kategoriyalar: papka -> ichidagilar (storefront.js ostida tugmalar chizadi)
	context.cat_tree = catalog.get("tree") or {}
	# JS savat paneli uchun: kod -> nom, narx, rasm
	context.catalog_json = {
		p["code"]: {
			"name": p["name"], "price": p["price"], "thumb": p["thumb"],
			"ws": p.get("wholesale_price"), "wsmin": p.get("wholesale_min"),
		}
		for p in catalog["items"]
	}
	mins = sorted({p["wholesale_min"] for p in catalog["items"] if p.get("wholesale_price")})
	context.has_wholesale = bool(mins)
	context.wholesale_min_label = mins[0] if len(mins) == 1 else (mins[0] if mins else 10)
	context.og_image = seo.abs_url(shop.logo or (catalog["items"][0]["thumb"] if catalog["items"] else None))
	# Google: asl manzil (/s/pandoo, ?layout= — shu sahifaning nusxasi), tavsifda tovar nomlari («panda books» qidiruvi)
	url = seo.shop_url(shop.name)
	context.canonical_url = url
	names = seo.name_list(p["name"] for p in catalog["items"])
	context.meta_description = seo.meta_text(
		shop.tagline,
		f"{shop.shop_name} onlayn do‘koni" + (f": {names}" if names else ""),
		"Payme, Click yoki naqd to‘lov, yetkazib berish",
	)
	context.ld_json = seo.jsonld(
		seo.shop_schema(shop, url, catalog["items"]),
		seo.breadcrumbs(("magazinlar.uz", seo.abs_url("/")), (shop.shop_name, url)),
	)
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""
	# Sarlavhadagi tugma: kirmagan mijozga «Kirish», kirganiga «Buyurtmalarim»
	context.customer = customers.current_customer()
	# Sarlavhadagi «Profil»da qizil raqam: sotuvchidan kelgan, hali o'qilmagan javoblar
	from marketplace.sotuv.tovar_chat import customer_unread

	context.chat_unread = customer_unread(context.customer.customer, shop.name) if context.customer else 0
