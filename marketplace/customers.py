"""Mijoz: telefon raqami bo'yicha Customer va brauzer sessiyasi.

Frappe'da User yaratish email talab qiladi, mijozlarga esa email kerak emas. Shuning uchun
mijoz — oddiy ERPNext Customer, "kirish" esa o'zimizning sessiya cookie'si:
  brauzerda: mp_sid = tasodifiy token (HttpOnly, SameSite=Lax)
  bazada:    Customer Session.token_hash = sha256(token)  — token o'g'irlansa ham bazadan tiklanmaydi
"""

import hashlib
import secrets

import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

COOKIE = "mp_sid"


def get_or_create_customer(phone, first_name, last_name):
	full_name = " ".join(p.strip() for p in (first_name, last_name) if p and p.strip())
	name = frappe.db.get_value("Customer", {"mp_phone": phone})
	if name:
		if full_name and frappe.db.get_value("Customer", name, "customer_name") != full_name:
			frappe.db.set_value("Customer", name, "customer_name", full_name)
		return name

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": full_name or phone,
			"customer_type": "Individual",
			"customer_group": frappe.db.get_single_value("Selling Settings", "customer_group") or "Individual",
			"territory": frappe.db.get_single_value("Selling Settings", "territory") or "Uzbekistan",
			"mp_phone": phone,
			"mobile_no": phone,
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def start_session(customer, phone):
	token = secrets.token_urlsafe(32)
	days = cint(frappe.get_cached_doc("Marketplace Settings").session_days) or 30
	frappe.get_doc(
		{
			"doctype": "Customer Session",
			"customer": customer,
			"phone": phone,
			"token_hash": _hash(token),
			"expires_at": add_to_date(now_datetime(), days=days),
			"last_seen": now_datetime(),
			"user_agent": (frappe.get_request_header("User-Agent") or "")[:500],
		}
	).insert(ignore_permissions=True)
	frappe.local.cookie_manager.set_cookie(COOKIE, token, max_age=days * 86400, httponly=True, samesite="Lax")


def current_customer():
	"""Sessiyadagi mijoz: {customer, phone, name} yoki None."""
	request = getattr(frappe, "request", None)
	token = request.cookies.get(COOKIE) if request else None
	if not token:
		return None
	row = frappe.db.get_value(
		"Customer Session", {"token_hash": _hash(token)}, ["name", "customer", "phone", "expires_at"], as_dict=True
	)
	if not row or get_datetime(row.expires_at) < now_datetime():
		return None
	frappe.db.set_value("Customer Session", row.name, "last_seen", now_datetime(), update_modified=False)
	return frappe._dict(
		customer=row.customer,
		phone=row.phone,
		name=frappe.db.get_value("Customer", row.customer, "customer_name"),
	)


def end_session():
	request = getattr(frappe, "request", None)
	token = request.cookies.get(COOKIE) if request else None
	if token:
		frappe.db.delete("Customer Session", {"token_hash": _hash(token)})
	frappe.local.cookie_manager.delete_cookie(COOKIE)


def _hash(token):
	return hashlib.sha256(token.encode()).hexdigest()
