"""Mijoz sahifalari chaqiradigan ochiq (guest) API.

URL: /api/method/marketplace.api.<funksiya>
"""

import json

import frappe
from frappe.rate_limiter import rate_limit

from marketplace import customers, orders, otp, storefront


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def get_cart(shop, lines):
	"""Savat: brauzer faqat {code, qty} yuboradi, narx va qoldiq serverdan olinadi.

	lines: '[{"code": "nafis-tekstil-00001", "qty": 2}, ...]'
	"""
	if isinstance(lines, str):
		lines = json.loads(lines)
	shop_doc = storefront.get_shop(shop)
	cart = storefront.get_cart_lines(shop_doc, lines)
	return {"lines": cart, "total": sum(line["amount"] for line in cart)}


# ---------------- Rasmiylashtirish: Telegram kodi, mijoz, buyurtma ----------------
# Cookie (mp_sid) SameSite=Lax: boshqa saytdan yashirin POST yuborilganda brauzer uni qo'shmaydi.


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=600)
def request_code(phone):
	"""Telegram'ga tasdiqlash kodi yuboradi. Qaysi sahifadan so'ralgani botdagi "Saytga qaytish" uchun saqlanadi."""
	from urllib.parse import urlparse

	referer = urlparse(frappe.get_request_header("Referer") or "").path
	return otp.send_code(otp.normalize_phone(phone), return_path=referer)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def verify_code(phone, code, first_name, last_name=""):
	"""Kod to'g'ri bo'lsa: Customer topiladi/yaratiladi va sessiya ochiladi."""
	if not (first_name or "").strip():
		frappe.throw(frappe._("Ismingizni yozing"))
	phone = otp.normalize_phone(phone)
	otp.verify_code(phone, code)
	customer = customers.get_or_create_customer(phone, first_name, last_name)
	customers.start_session(customer, phone)
	# Yangi cookie javob bilan ketadi, shu so'rovda hali yo'q — shuning uchun to'g'ridan-to'g'ri qaytaramiz
	return {"name": frappe.db.get_value("Customer", customer, "customer_name"), "phone_masked": otp.mask_phone(phone)}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def me():
	c = customers.current_customer()
	if not c:
		return None
	return {"name": c.name, "phone_masked": otp.mask_phone(c.phone)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout():
	customers.end_session()


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def place_order(shop, lines, delivery_method, address=""):
	customer = _require_customer()
	if isinstance(lines, str):
		lines = json.loads(lines)
	so = orders.place_order(storefront.get_shop(shop), lines, delivery_method, address, customer)
	return {"order": so.name, "total": so.grand_total, "url": f"/s/{shop}/buyurtma/{so.name}"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=600)
def choose_payment(order, method):
	return orders.choose_payment(order, method, _require_customer())


def _require_customer():
	customer = customers.current_customer()
	if not customer:
		frappe.throw(frappe._("Avval telefon raqamingizni tasdiqlang"), frappe.AuthenticationError)
	return customer
