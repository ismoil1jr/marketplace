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


def loyal_name(phone, shop=None):
	"""Do'kon "Doimiy mijoz" anketasida yozgan ism: avval shu do'konniki, bo'lmasa istalgan do'konniki."""
	for filters in ([{"phone": phone, "shop": shop}] if shop else []) + [{"phone": phone}]:
		name = frappe.db.get_value("Doimiy Mijoz", filters, "mijoz_ismi", order_by="modified desc")
		if name:
			return name
	return None


def get_or_create_customer(phone, first_name, last_name, shop=None):
	"""Ism Telegram'dan keladi. Lekin do'kon mijozni doimiy mijoz qilib ismini yozgan bo'lsa — o'sha qoladi,
	Telegram'dagi ism uni almashtirmaydi."""
	full_name = loyal_name(phone, shop) or " ".join(p.strip() for p in (first_name, last_name) if p and p.strip())
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
		"Customer Session", {"token_hash": _hash(token)}, ["name", "customer", "phone", "expires_at", "last_seen"], as_dict=True
	)
	now = now_datetime()
	if not row or get_datetime(row.expires_at) < now:
		return None
	_touch(row, now)
	return frappe._dict(
		customer=row.customer,
		phone=row.phone,
		name=frappe.db.get_value("Customer", row.customer, "customer_name"),
	)


SEEN_EVERY = 300  # soniya


def _touch(row, now):
	"""Profil → «Faol seanslar» uchun oxirgi faollik. Har so'rovda emas, 5 daqiqada bir yoziladi: chat har 3 soniyada
	so'raydi, bir mijozning parallel so'rovlari bitta qatorni yangilab MariaDB 1020 «Record has changed since last
	read» bilan yiqilardi. Shunday to'qnashuv bo'lsa ham so'rov davom etadi — bu yozuv muhim emas."""
	if row.last_seen and (now - get_datetime(row.last_seen)).total_seconds() < SEEN_EVERY:
		return
	frappe.db.savepoint("mp_seen")
	try:
		frappe.db.set_value("Customer Session", row.name, "last_seen", now, update_modified=False)
	except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
		frappe.db.rollback(save_point="mp_seen")


def end_session():
	request = getattr(frappe, "request", None)
	token = request.cookies.get(COOKIE) if request else None
	if token:
		frappe.db.delete("Customer Session", {"token_hash": _hash(token)})
	frappe.local.cookie_manager.delete_cookie(COOKIE)


def _hash(token):
	return hashlib.sha256(token.encode()).hexdigest()


def _current_token_hash():
	request = getattr(frappe.local, "request", None)  # so'rovsiz (test, navbat) — None
	token = request.cookies.get(COOKIE) if request else None
	return _hash(token) if token else None


def list_sessions(customer):
	"""Profil → «Faol seanslar»: mijoz kirgan qurilmalar (muddati o'tmaganlari), shu qurilma birinchi."""
	from marketplace.tg_login import device_label

	current = _current_token_hash()
	rows = frappe.get_all(
		"Customer Session", filters={"customer": customer, "expires_at": [">", now_datetime()]},
		fields=["name", "token_hash", "user_agent", "last_seen", "creation"], order_by="last_seen desc",
	)
	out = [
		frappe._dict(name=r.name, device=device_label(r.user_agent), last_seen=r.last_seen or r.creation,
		             current=bool(current) and r.token_hash == current)
		for r in rows
	]
	return sorted(out, key=lambda r: not r.current)


def end_one_session(customer, name):
	"""Profil → Faol seanslar → «Chiqarish»: bitta boshqa qurilmani chiqaradi. Faqat o'z seansini va shu qurilmani
	emas (shu qurilmadan — «Akkauntdan chiqish» tugmasi)."""
	from frappe import _

	row = frappe.db.get_value("Customer Session", name, ["customer", "token_hash"], as_dict=True)
	if not row or row.customer != customer:
		frappe.throw(_("Seans topilmadi"))
	if row.token_hash == _current_token_hash():
		frappe.throw(_("Bu — shu qurilma. Chiqish uchun «Akkauntdan chiqish»ni bosing"))
	frappe.delete_doc("Customer Session", name, ignore_permissions=True, force=True)


def end_other_sessions(customer):
	"""Shu qurilmadan boshqa hamma qurilmadan chiqish. Qaytaradi: nechta seans yopildi."""
	current = _current_token_hash()
	others = frappe.get_all("Customer Session", filters={"customer": customer, "token_hash": ["!=", current or ""]}, pluck="name")
	for name in others:
		frappe.delete_doc("Customer Session", name, ignore_permissions=True, force=True)
	return len(others)
