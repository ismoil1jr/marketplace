import frappe

from marketplace import customers, storefront
from marketplace.sotuv import tovar_chat

no_cache = 1


def get_context(context):
	"""Tovar bo'yicha sotuvchi bilan chat (/s/<do'kon>/chat/<tovar>). Kirmagan mijozga — Telegram orqali kirish.
	Xabarlar brauzerda yuklanadi (public/js/tovar_chat.js -> sotuv/tovar_chat.py)."""
	shop = storefront.get_shop(frappe.form_dict.shop)
	product = storefront.get_product(shop, frappe.form_dict.item)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.product = product
	context.card = tovar_chat.product_cards(shop.name, [product.code]).get(product.code) or {}
	context.customer = customers.current_customer()
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.noindex = 1  # shaxsiy sahifa
	context.csrf_token = frappe.session.data.csrf_token or ""
