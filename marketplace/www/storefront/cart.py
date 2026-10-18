import frappe

from marketplace import storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""
