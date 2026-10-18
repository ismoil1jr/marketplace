import frappe

from marketplace import customers, orders, otp, storefront

no_cache = 1


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""

	# Faqat sessiyadagi mijozning va faqat shu do'kondagi buyurtmalari
	customer = customers.current_customer()
	context.customer = customer
	context.phone_masked = otp.mask_phone(customer.phone) if customer else ""
	context.active, context.done = orders.list_orders_for_customer(customer, shop.name) if customer else ([], [])
