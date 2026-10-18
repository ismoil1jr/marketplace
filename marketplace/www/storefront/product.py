import frappe

from marketplace import storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	product = storefront.get_product(shop, frappe.form_dict.item)

	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.product = product
	context.catalog_json = {product.code: {"name": product.name, "price": product.price, "thumb": product.thumb}}
	context.og_image = product.images[0] if product.images else shop.logo
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""
