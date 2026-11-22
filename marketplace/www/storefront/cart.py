import frappe

from marketplace import storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.noindex = 1  # shaxsiy sahifa — Google'da chiqmaydi
	context.csrf_token = frappe.session.data.csrf_token or ""
