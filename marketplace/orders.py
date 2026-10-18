"""Mijoz buyurtmasi: savat -> ERPNext Sales Order.

Qoidalar:
  * narx, ulgurji chegara va qoldiq faqat serverdan (storefront.get_cart_lines); brauzer
    yuborgan narxga hech qachon ishonilmaydi;
  * bitta buyurtma = bitta do'kon = bitta kassa;
  * Sales Order darhol submit qilinadi: summa qotadi (Payme aynan shu summani tekshiradi)
    va qoldiq zaxiralanadi (Bin.reserved_qty).
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, today

from marketplace import payments, storefront

DELIVERY_METHODS = ("Kuryer", "O'zim olaman")


@contextmanager
def as_system():
	"""ERPNext ichki funksiyalari (get_item_details va b.) ruxsatni joriy foydalanuvchi uchun
	tekshiradi va ignore_permissions'ga qaramaydi. Mijoz esa Guest. Shuning uchun buyurtma
	tizim nomidan yaratiladi — faqat shu yerda, barcha tekshiruvlar biz tomonda bajarilgandan keyin."""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)


def place_order(shop, lines, delivery_method, address, customer):
	if delivery_method not in DELIVERY_METHODS:
		frappe.throw(_("Yetkazib berish usulini tanlang"))
	address = (address or "").strip()
	if delivery_method == "Kuryer" and len(address) < 5:
		frappe.throw(_("Yetkazib berish manzilini yozing"), title=_("Manzil"))

	cart = storefront.get_cart_lines(shop, lines)
	if not cart:
		frappe.throw(_("Savat bo‘sh yoki tovarlar tugagan"))

	requested = {line.get("code"): int(line.get("qty") or 0) for line in lines}
	short = [c["name"] for c in cart if c["qty"] < requested.get(c["code"], 0)]
	if short:
		frappe.throw(_("Omborda yetarli emas: {0}. Savatni yangilang.").format(", ".join(short)))

	with as_system():
		return _create_sales_order(shop, cart, delivery_method, address, customer)


def _create_sales_order(shop, cart, delivery_method, address, customer):
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": frappe.defaults.get_global_default("company"),
			"customer": customer.customer,
			"transaction_date": today(),
			"delivery_date": add_days(today(), 2),
			"set_warehouse": shop.warehouse,
			"selling_price_list": storefront._selling_price_list(),
			"ignore_pricing_rule": 1,
			"shop": shop.name,
			"customer_phone": customer.phone,
			"order_source": "Web",
			"payment_status": "Kutilmoqda",
			"delivery_method": delivery_method,
			"delivery_address": address if delivery_method == "Kuryer" else None,
			"items": [
				{
					"item_code": c["code"],
					"qty": c["qty"],
					"rate": c["price"],
					"price_list_rate": c["retail_price"],
					"warehouse": shop.warehouse,
					"delivery_date": add_days(today(), 2),
				}
				for c in cart
			],
		}
	)
	so.flags.ignore_permissions = True
	so.insert()

	# ERPNext narxni o'zicha qayta hisoblab yubormaganini tekshiramiz
	expected = sum(c["amount"] for c in cart)
	if abs(flt(so.grand_total) - expected) > 0.5:
		frappe.throw(_("Narx hisobida xatolik. Iltimos, savatni yangilang."))

	so.submit()
	return so


def get_order_for_customer(name, customer, include_cancelled=False):
	"""Faqat shu mijozning buyurtmasi. include_cancelled — chek/ko'rish sahifasi uchun (to'lov uchun emas)."""
	so = frappe.db.get_value(
		"Sales Order",
		{"name": name, "customer": customer.customer, "docstatus": ["in", [1, 2]] if include_cancelled else 1},
		[
			"name", "shop", "grand_total", "payment_method", "payment_status", "delivery_method", "delivery_address",
			"transaction_date", "creation", "docstatus", "status", "per_delivered",
		],
		as_dict=True,
	)
	if not so:
		raise frappe.DoesNotExistError(_("Buyurtma topilmadi"))
	so["items"] = frappe.get_all(
		"Sales Order Item", {"parent": name}, ["item_code", "item_name", "qty", "rate", "amount"], order_by="idx"
	)
	so["count"] = sum(int(i.qty) for i in so["items"])
	so["state"], so["state_label"] = order_state(so)
	so["created"] = get_datetime(so.creation).strftime("%d.%m.%Y %H:%M")
	return so


# ---------------- Mijozga ko'rinadigan holat ("Buyurtmalarim" va chek) ----------------
# Kalit CSS'da ham ishlatiladi: .sf-status--<kalit>
ACTIVE_STATES = ("waiting", "paid", "cod")


def order_state(so):
	"""(kalit, yorliq). Naqd buyurtma sotuvchi "Naqd pul olindi" bosmaguncha kutilmoqda turadi;
	Payme/Click to'lovi webhook bilan avtomatik "To'langan" bo'ladi."""
	if so.docstatus == 2 or so.payment_status == "Bekor":
		return "cancelled", "Bekor qilingan"
	paid = so.payment_status == "To'langan"
	cash = so.payment_method == "Naqd"
	if cash and not paid:
		return "cod", "Naqd — to‘lov kutilmoqda"
	if flt(so.per_delivered) >= 100 or so.status in ("Completed", "To Bill"):
		return "delivered", "Topshirildi" + (" · naqd to‘langan" if cash else "")
	if so.status == "Closed":
		return "closed", "Yopilgan"
	if paid:
		return "paid", "Naqd — to‘langan" if cash else f"To‘langan ({so.payment_method})" if so.payment_method else "To‘langan"
	return "waiting", "To‘lov kutilmoqda"


def list_orders_for_customer(customer, shop):
	"""Mijozning shu do'kondagi buyurtmalari: (jarayonda, yakunlangan), yangilari birinchi.
	Filtr har doim sessiyadagi mijoz + do'kon — boshqa birovning buyurtmasi chiqmaydi."""
	rows = frappe.get_all(
		"Sales Order",
		filters={"customer": customer.customer, "shop": shop, "docstatus": ["in", [1, 2]]},
		fields=["name", "grand_total", "payment_method", "payment_status", "creation", "docstatus", "status", "per_delivered"],
		order_by="creation desc",
		limit_page_length=200,
	)
	counts = {}
	if rows:
		for i in frappe.get_all("Sales Order Item", {"parent": ["in", [r.name for r in rows]]}, ["parent", "qty"]):
			counts[i.parent] = counts.get(i.parent, 0) + int(i.qty)

	active, done = [], []
	for r in rows:
		r.state, r.state_label = order_state(r)
		r.count = counts.get(r.name, 0)
		r.date = get_datetime(r.creation).strftime("%d.%m.%Y")
		(active if r.state in ACTIVE_STATES else done).append(r)
	return active, done


def choose_payment(name, method, customer):
	so = get_order_for_customer(name, customer)
	shop = storefront.get_shop(so.shop)
	if method not in ("Payme", "Click", "Naqd"):
		frappe.throw(_("Bu to‘lov usuli mavjud emas"))
	if method == "Naqd" and not shop.enable_cod:
		frappe.throw(_("Bu to‘lov usuli mavjud emas"))
	if so.payment_status == "To'langan":
		frappe.throw(_("Buyurtma allaqachon to‘langan"))

	frappe.db.set_value("Sales Order", name, "payment_method", method)
	if method == "Naqd":
		return {"status": "confirmed"}
	# Payme / Click: mijoz to'lov sahifasiga (telefonda ilovaga) yuboriladi
	return {"status": "pending_gateway", "redirect": payments.checkout_url(so, method)}
