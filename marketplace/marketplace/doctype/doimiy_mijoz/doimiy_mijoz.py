# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

"""Doimiy mijoz: kuryer (yoki do'kon egasi) mijozdan so'rab yozadigan anketa.

Har bir do'konning o'z ro'yxati: bitta telefon raqami bitta do'konda faqat bir marta yoziladi.
Tug'ilgan kun va farzandlar — aksiya/sovg'a takliflari uchun; xaridlari esa shu do'kondagi
buyurtmalardan (telefon yoki saytdagi Customer bo'yicha) avtomatik yig'iladi.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, get_datetime, getdate, today

from marketplace.permissions import get_user_shop

MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]


class DoimiyMijoz(Document):
	def validate(self):
		from marketplace.otp import normalize_phone

		self.shop = get_user_shop() or self.shop
		if not self.shop:
			frappe.throw(_("Do'konni tanlang"))
		self.first_name = _clean_name(self.first_name)
		self.last_name = _clean_name(self.last_name)
		# "full_name" emas: Frappe User havolasida hujjatdagi full_name'ni ko'rsatadi ("Kim yozdi" buzilardi)
		self.mijoz_ismi = f"{self.first_name} {self.last_name}".strip()
		self.phone = normalize_phone(self.phone)

		other = frappe.db.get_value("Doimiy Mijoz", {"shop": self.shop, "phone": self.phone, "name": ["!=", self.name]})
		if other:
			frappe.throw(
				_("Bu raqam ro'yxatda bor: {0}").format(f'<a href="/desk/doimiy-mijoz/{other}">{other}</a>'),
				title=_("Mijoz allaqachon yozilgan"),
			)

		# Tug'ilgan sana ixtiyoriy (CEO): bo'lsa — oyi aksiyalar uchun yoziladi
		_check_birth_date(self.birth_date, _("Mijozning tug'ilgan sanasi"))
		self.birth_month = f"{getdate(self.birth_date).month:02d} {MONTHS[getdate(self.birth_date).month - 1]}" if self.birth_date else None
		for field in ("tuman", "kocha", "uy", "moljal"):
			self.set(field, " ".join((self.get(field) or "").split()) or None)
		self.latitude, self.longitude = _point(self.joylashuv)
		for child in self.children:
			child.child_name = _clean_name(child.child_name)
			_check_birth_date(child.birth_date, _("{0}-farzandning tug'ilgan sanasi").format(child.idx))
			child.age = _age(child.birth_date)
		self.children_count = len(self.children)

		self.customer = frappe.db.get_value("Customer", {"mp_phone": self.phone}) or self.customer
		if self.is_new():
			self.registered_by = frappe.session.user
		if self.registered_by:
			self.registered_by_full_name = frappe.utils.get_fullname(self.registered_by)

	def on_update(self):
		# Do'kon yozgan ism mijozning ismi bo'ladi: keyingi buyurtmalarda shu chiqadi, saytga Telegram orqali
		# kirganda ham Telegram'dagi ism uni almashtirmaydi (customers.get_or_create_customer)
		if self.customer and frappe.db.get_value("Customer", self.customer, "customer_name") != self.mijoz_ismi:
			frappe.db.set_value("Customer", self.customer, "customer_name", self.mijoz_ismi)


def _point(geojson):
	"""Xaritadagi birinchi nuqta (Geolocation — GeoJSON FeatureCollection) -> (kenglik, uzunlik)."""
	try:
		data = json.loads(geojson or "{}")
	except ValueError:
		return None, None
	for feature in data.get("features") or []:
		geometry = feature.get("geometry") or {}
		if geometry.get("type") == "Point" and len(geometry.get("coordinates") or []) >= 2:
			lng, lat = geometry["coordinates"][:2]
			return flt(lat, 7), flt(lng, 7)
	return None, None


def _clean_name(value):
	value = " ".join((value or "").split())
	return value[:1].upper() + value[1:] if value else value


def _age(birth_date):
	b, t = getdate(birth_date), getdate(today())
	return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def _check_birth_date(value, label):
	if not value:
		return
	if date_diff(today(), value) < 0:
		frappe.throw(_("{0} kelajakda bo'lishi mumkin emas").format(label))
	if _age(value) > 120:
		frappe.throw(_("{0} noto'g'ri").format(label))


@frappe.whitelist()
def get_purchases(name: str):
	"""Mijozning shu do'kondagi barcha buyurtmalari: nima, qachon, nechta, qancha va qanday to'lagan."""
	from marketplace.orders import order_state

	doc = frappe.get_doc("Doimiy Mijoz", name)
	doc.check_permission("read")

	match = {"customer_phone": doc.phone}
	orders = frappe.get_all(
		"Sales Order",
		filters={"shop": doc.shop, "docstatus": ["in", [1, 2]], "mp_placed": 1},
		or_filters={**match, **({"customer": doc.customer} if doc.customer else {})},
		fields=[
			"name", "transaction_date", "creation", "grand_total", "payment_method", "payment_status",
			"docstatus", "status", "per_delivered", "delivery_method",
		],
		order_by="creation desc",
		limit_page_length=500,
		ignore_permissions=True,
	)
	items = {}
	if orders:
		for i in frappe.get_all(
			"Sales Order Item",
			filters={"parent": ["in", [o.name for o in orders]]},
			fields=["parent", "item_name", "qty", "amount"],
			order_by="idx",
			ignore_permissions=True,
		):
			items.setdefault(i.parent, []).append({"name": i.item_name, "qty": cint(i.qty), "amount": flt(i.amount)})

	out, total, count = [], 0, 0
	for o in orders:
		state, label = order_state(o)
		rows = items.get(o.name, [])
		if state != "cancelled":
			total += flt(o.grand_total)
			count += 1
		out.append(
			{
				"name": o.name,
				"date": get_datetime(o.creation).strftime("%d.%m.%Y %H:%M"),
				"items": rows,
				"qty": sum(r["qty"] for r in rows),
				"total": flt(o.grand_total),
				"payment_method": o.payment_method or "",
				"state": state,
				"state_label": label,
			}
		)
	return {"orders": out, "count": count, "total": total, "last": out[0]["date"] if out else None}


def register_from_delivery(so):
	"""Yetkazilgan buyurtma mijozi o'zi doimiy mijozlarga yoziladi (seller_desk.mark_delivered). Raqami ro'yxatda
	bo'lsa — tegilmaydi. Familiya bo'lmasa ham yoziladi: anketaning qolganini kuryer yoki do'kon keyin to'ldiradi."""
	from marketplace.otp import normalize_phone

	raw = so.customer_phone or frappe.db.get_value("Customer", so.customer, "mp_phone")
	try:
		phone = normalize_phone(raw)
	except frappe.ValidationError:
		frappe.clear_messages()
		return None
	if not so.shop or frappe.db.exists("Doimiy Mijoz", {"shop": so.shop, "phone": phone}):
		return None
	first, _sep, last = (so.customer_name or "").strip().partition(" ")
	address = (so.get("delivery_address") or "").strip()
	doc = frappe.get_doc(
		{
			"doctype": "Doimiy Mijoz", "shop": so.shop, "phone": phone, "customer": so.customer, "source_order": so.name,
			"first_name": first if first and first != raw else _("Mijoz"), "last_name": last,
			"notes": _("Yetkazish manzili: {0}").format(address) if address else None,
		}
	)
	doc.flags.ignore_mandatory = True  # familiya buyurtmada bo'lmasligi mumkin
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def from_order(order: str):
	"""Buyurtma formasidagi "Mijozni ro'yxatga olish": shu raqam yozilgan bo'lsa — o'sha anketa,
	aks holda yangi anketa uchun buyurtmadagi ism va telefon."""
	if not frappe.has_permission("Sales Order", "read", order):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	so = frappe.db.get_value("Sales Order", order, ["shop", "customer", "customer_name", "customer_phone"], as_dict=True)
	phone = so.customer_phone or frappe.db.get_value("Customer", so.customer, "mp_phone")
	existing = phone and frappe.db.get_value("Doimiy Mijoz", {"shop": so.shop, "phone": phone})
	if existing:
		return {"existing": existing}
	first, _sep, last = (so.customer_name or "").strip().partition(" ")
	return {
		"first_name": first if first != phone else "",
		"last_name": last,
		"phone": phone,
		"customer": so.customer,
		"source_order": order,
	}
