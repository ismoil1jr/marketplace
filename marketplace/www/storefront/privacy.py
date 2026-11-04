import frappe
from frappe.utils import cint

from marketplace import storefront

no_cache = 1


def get_context(context):
	"""Do'konning maxfiylik siyosati: /s/<do'kon>/maxfiylik. Meta (Instagram) lead-formasi shu havolani so'raydi.
	Sotuvchi kim ekanini (yuridik nom, STIR) Shop formasidan oladi — har bir do'konda o'zi."""
	shop = storefront.get_shop(frappe.form_dict.shop)
	shop.update(frappe.db.get_value("Shop", shop.name, ["legal_name", "stir"], as_dict=True) or {})
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""
	context.seller = shop.legal_name or shop.shop_name
	# Qo'ng'iroq yozuvlari shuncha kundan keyin o'chiriladi (Telefoniya Sozlamalari), 0 — o'chirilmaydi
	context.call_days = cint(frappe.db.get_single_value("Telefoniya Sozlamalari", "saqlash_kuni"))
