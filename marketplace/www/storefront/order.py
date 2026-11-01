import frappe

from marketplace import customers, orders, payments, storefront

no_cache = 1

PAY_TITLES = {"Payme": "Payme", "Click": "Click", "Naqd": "Naqd pul"}
DELIVERY_TITLES = {"Kuryer": "Kuryer orqali", "O'zim olaman": "O‘zim olaman (do‘kondan)"}


def get_context(context):
	shop = storefront.get_shop(frappe.form_dict.shop)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.csrf_token = frappe.session.data.csrf_token or ""

	customer = customers.current_customer()
	context.customer = customer
	# Bekor qilingan buyurtma ham ko'rinadi (faqat o'qish uchun, to'lov tugmasisiz)
	order = orders.get_order_for_customer(frappe.form_dict.order, customer, include_cancelled=True) if customer else None
	if order and order.shop != shop.name:
		raise frappe.DoesNotExistError
	context.order = order
	if not order:
		return

	order.pay_title = PAY_TITLES.get(order.payment_method) or "Tanlanmagan"
	order.delivery_title = DELIVERY_TITLES.get(order.delivery_method) or order.delivery_method
	if order.state == "cancelled":
		order.pay_status_title = "Bekor qilingan"
	elif order.payment_status == "To'langan":
		order.pay_status_title = "To‘langan"
	elif order.payment_method == "Naqd":
		order.pay_status_title = "Naqd — topshirishda"
	else:
		order.pay_status_title = "Kutilmoqda"
	context.show_receipt = order.state != "cancelled" and (order.payment_status == "To'langan" or order.payment_method == "Naqd")

	# gateway_status: {"Payme": "live"|None, "Click": "live"|None}. Do'konda yoqilgan, lekin kassa
	# kalitlari hali kiritilmagan usul ko'rinib turadi, faqat tanlab bo'lmaydi.
	gw = payments.gateway_status(shop.name) or {}
	card = "Ilova yoki Uzcard / Humo karta"
	context.methods = [
		m for m in (
			# Payme va Click — o'z logolari (public/images/pay: payme.uz va click.uz rasmiy SVG'lari)
			{"key": "Payme", "title": "Payme", "sub": card, "logo": "/assets/marketplace/images/pay/payme.svg", "on": shop.enable_payme, "ready": bool(gw.get("Payme"))},
			{"key": "Click", "title": "Click", "sub": card, "logo": "/assets/marketplace/images/pay/click.svg", "on": shop.enable_click, "ready": bool(gw.get("Click"))},
			{"key": "Naqd", "title": "Naqd pul", "sub": "Kuryerga yetkazilganda" if order.delivery_method == "Kuryer" else "Mahsulotni olganingizda", "icon": "i-cash", "on": shop.enable_cod, "ready": True},
		)
		if m["on"]
	]
	for m in context.methods:
		if not m["ready"]:
			m["sub"] = "Kassa hali ulanmagan"
	context.first_ready = next((m["key"] for m in context.methods if m["ready"]), None)
