import frappe
from frappe.utils import flt

from marketplace import customers, seo, storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	product = storefront.get_product(shop, frappe.form_dict.item)

	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.product = product
	context.related = storefront.get_related(shop, product)
	context.customer = customers.current_customer()  # tepadagi panel: «Buyurtmalarim» yoki «Kirish»
	# JS savat paneli uchun: shu mahsulot va pastdagi o'xshashlari (kartadagi "+" tugmasi)
	context.catalog_json = {
		p["code"]: {"name": p["name"], "price": p["price"], "thumb": p["thumb"], "ws": p.get("wholesale_price"), "wsmin": p.get("wholesale_min")}
		for p in context.related
	}
	context.catalog_json[product.code] = {"name": product.name, "price": product.price, "thumb": product.thumb}
	context.og_image = seo.abs_url(product.images[0] if product.images else (product.thumb or shop.logo))
	# Google: asl manzil, tovarning o'z tavsifi (do'kon shiori emas), narx/rasm bilan schema.org Product
	url = seo.shop_url(shop.name, "p", product.code)
	context.canonical_url = url
	context.og_type = "product"
	price = f"{flt(product.price):,.0f}".replace(",", " ") + " so‘m" if flt(product.price) > 0 and not product.no_price else None
	context.meta_description = seo.meta_text(
		f"{product.name}" + (f" — {price}" if price else "") + f", {shop.shop_name} do‘konida",
		product.description or shop.tagline,
	)
	context.ld_json = seo.jsonld(
		seo.product_schema(shop, product, url),
		seo.breadcrumbs(
			("magazinlar.uz", seo.abs_url("/")), (shop.shop_name, seo.shop_url(shop.name)), (product.name, url)
		),
	)
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""
