"""Mijoz sahifalari chaqiradigan ochiq (guest) API.

URL: /api/method/marketplace.api.<funksiya>
"""

import json

import frappe
from frappe.rate_limiter import rate_limit

from marketplace import customers, orders, otp, storefront, tg_login


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def get_cart(shop, lines, pending=None):
	"""Savat: brauzer faqat {code, qty} yuboradi, narx va qoldiq serverdan olinadi.

	lines: '[{"code": "nafis-tekstil-00001", "qty": 2}, ...]'
	pending: shu brauzerda "To'lovga o'tish" bosilgan, hali savatdan olinmagan buyurtma — holati qaytadi
	"""
	if isinstance(lines, str):
		lines = json.loads(lines)
	shop_doc = storefront.get_shop(shop)
	customer = customers.current_customer()
	pend = orders.pending_state(shop_doc.name, pending, customer) if pending else None
	held = orders.held_by(pend["name"]) if pend and pend["state"] == "pending" else None
	cart = storefront.get_cart_lines(shop_doc, lines, held)
	return {
		"lines": cart,
		"total": sum(line["amount"] for line in cart),
		# Majburiy tovar (masalan, ruchka) olinmagan bo'lsa — savatda ogohlantirish va "Savatga qo'shish"
		"mandatory": orders.mandatory_status(shop_doc, customer, [line["code"] for line in cart]) if cart else {"required": False},
		"pending": pend,
	}


# ---------------- Rasmiylashtirish: Telegram orqali kirish, mijoz, buyurtma ----------------
# Cookie (mp_sid) SameSite=Lax: boshqa saytdan yashirin POST yuborilganda brauzer uni qo'shmaydi.


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def telegram_login(shop, path=""):
	"""Telegram orqali kirish: bot havolasi (t.me/<bot>?start=l<id>) va faqat shu brauzerdagi secret (tg_login.py)."""
	return tg_login.start(storefront.get_shop(shop).name, path)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=400, seconds=600)
def telegram_login_status(login, secret):
	"""Sayt har 2 soniyada so'raydi: botda raqam yuborilgach — sessiya ochiladi (cookie shu javob bilan ketadi)."""
	return tg_login.status(login, secret)


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
	try:
		tg_login.remember_order(so.shop, customer)  # boshqa do'konda kirgan mijoz — shu do'kon ro'yxatiga ham
	except Exception:
		frappe.log_error(f"Mijoz do'kon ro'yxatiga yozilmadi: {so.name}", "Marketplace Telegram mijozlar")
	return {"order": so.name, "total": so.grand_total, "url": f"/s/{shop}/buyurtma/{so.name}"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=600)
def update_address(order, address):
	return orders.update_address(order, address, _require_customer())


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=600)
def choose_payment(order, method):
	return orders.choose_payment(order, method, _require_customer())


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=30, seconds=600)
def receipt_pdf(order):
	"""To'langan buyurtma cheki — PDF fayl bo'lib yuklanadi."""
	from marketplace.receipts import receipt_pdf as build

	filename, content = build(order, _require_customer())
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"


def _require_customer():
	customer = customers.current_customer()
	if not customer:
		frappe.throw(frappe._("Avval telefon raqamingizni tasdiqlang"), frappe.AuthenticationError)
	return customer
