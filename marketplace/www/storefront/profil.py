import frappe
from frappe.utils import get_datetime, now_datetime

from marketplace import customers, orders, storefront
from marketplace.sotuv import tovar_chat
from marketplace.sotuv.telefoniya import pretty_phone

no_cache = 1
MONTHS = ("yan", "fev", "mar", "apr", "may", "iyun", "iyul", "avg", "sen", "okt", "noy", "dek")


def get_context(context):
	"""Mijoz profili: Telegram rasmi, ismi va raqami, sotuvchi bilan chatlar, buyurtmalar, sozlamalar
	(kirish usuli, faol seanslar) va chiqish. Sarlavhadagi «Profil» tugmasi shu yerga olib keladi."""
	shop = storefront.get_shop(frappe.form_dict.shop)
	context.shop = shop
	context.base = f"/s/{shop.name}"
	context.catalog_json = {}
	context.asset_version = storefront.asset_version()
	context.noindex = 1  # shaxsiy sahifa
	context.csrf_token = frappe.session.data.csrf_token or ""

	customer = customers.current_customer()
	context.customer = customer
	if not customer:
		return
	tg = frappe.db.get_value(
		"Telegram Mijoz", {"phone": customer.phone}, ["full_name", "username", "photo"], as_dict=True, order_by="modified desc"
	) or frappe._dict()
	context.tg = tg
	context.phone = pretty_phone(customer.phone)
	context.initials = "".join(p[0] for p in (customer.name or "?").split()[:2]).upper()
	context.chats = tovar_chat.customer_threads(customer.customer, shop.name)
	for c in context.chats:
		c.when = short_time(c.oxirgi_vaqt)
	context.unread = sum(c.unread for c in context.chats)
	active, done = orders.list_orders_for_customer(customer, shop.name)
	context.orders_active, context.orders_total = len(active), len(active) + len(done)
	context.sessions = customers.list_sessions(customer.customer)
	for s in context.sessions:
		s.when = seen_text(s.last_seen)


def short_time(value):
	"""Chat ro'yxati: bugun — 14:05, aks holda — 21-noy."""
	if not value:
		return ""
	d = get_datetime(value)
	now = now_datetime()
	return d.strftime("%H:%M") if d.date() == now.date() else f"{d.day}-{MONTHS[d.month - 1]}"


def seen_text(value):
	"""Seans: oxirgi faolligi — «hozir», «bugun 14:05», «21-noy»."""
	if not value:
		return ""
	d = get_datetime(value)
	now = now_datetime()
	if (now - d).total_seconds() < 300:
		return "hozir faol"
	if d.date() == now.date():
		return f"bugun {d:%H:%M}"
	return f"{d.day}-{MONTHS[d.month - 1]} {d.year}" if d.year != now.year else f"{d.day}-{MONTHS[d.month - 1]}, {d:%H:%M}"
