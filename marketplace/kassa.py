"""Naqd pul: mijozdan kuryerga, kuryerdan do'kon kassasiga (ikki tomonlama tasdiq bilan).

Sales Order.mp_cash_status:
  "Kuryerda"            — kuryer mijozdan naqd oldi (seller_desk.courier_delivered yoki do'konchi deliver_cash'da kuryerni tanladi)
  "Topshirilmoqda"      — kuryer "Do'kon kassiriga topshirish" bosdi (courier_handover), do'konchi hali tasdiqlamagan
  "Do'konga topshirildi" — do'konchi "Qabul qildim" bosdi (seller_desk.cash_handed_over) — pul do'kon kassasida
  bo'sh                 — naqdni do'konning o'zi oldi (mijoz do'kondan olib ketdi) — pul darrov kassada

Kuryer sahifasi: Desk → Kuryer kassasi (dokon/page/kuryer_kassa). Do'konchiga: Do'konim'dagi "Naqd pul" bloki (cash_summary).
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, get_fullname, now_datetime

from marketplace.permissions import get_user_shop, is_admin, member_shop

IN_HAND, SENT, HANDED = "Kuryerda", "Topshirilmoqda", "Do'konga topshirildi"
FIELDS = ["name", "customer_name", "customer_phone", "grand_total", "currency", "mp_courier", "mp_delivered_at", "mp_cash_sent_at"]


def _shop(admin_optional=False):
	# Admin do'kon panelida bo'lmasa, lekin o'zi do'kon a'zosi bo'lsa — o'sha do'kon (permissions.member_shop).
	# admin_optional: do'kon panelida bo'lmagan admin uchun xato emas, None (sahifa do'konni tanlashni so'raydi)
	shop = get_user_shop() or member_shop()
	if not shop and not (admin_optional and is_admin()):
		frappe.throw(_("Siz hech qaysi do'konga biriktirilmagansiz"), frappe.PermissionError)
	return shop


def _money(amount):
	return fmt_money(amount, currency="UZS")


def shop_couriers(shop):
	"""Do'kon kuryerlari: [{user, name}]."""
	users = frappe.get_all("Shop Member", filters={"parent": shop, "parenttype": "Shop", "role": "Kuryer"}, pluck="user")
	return [{"user": u, "name": get_fullname(u)} for u in users]


def _notify(users, subject, order=None):
	for user in set(users):
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Sales Order" if order else None,
			 "document_name": order, "subject": subject}
		).insert(ignore_permissions=True)
		frappe.publish_realtime("marketplace_new_order", {"name": order, "subject": subject}, user=user, after_commit=True)


def _shop_owners(shop):
	"""Pulni qabul qiladiganlar: kuryer va sotuv menejeridan boshqa a'zolar."""
	return frappe.get_all(
		"Shop Member", filters={"parent": shop, "parenttype": "Shop", "role": ["not in", ["Kuryer", "Sotuv menejer"]]}, pluck="user"
	)


# ---------- Kuryer ----------


@frappe.whitelist()
def courier_cash():
	"""Kuryer kassasi: qo'lidagi naqd (buyurtmalar bilan) va do'konchi tasdiqlashini kutayotganlari."""
	shop = _shop()
	user = frappe.session.user
	base = {"shop": shop, "docstatus": 1, "payment_method": "Naqd", "mp_courier": user}
	in_hand = frappe.get_all("Sales Order", filters={**base, "mp_cash_status": IN_HAND}, fields=FIELDS, order_by="mp_delivered_at asc")
	sent = frappe.get_all("Sales Order", filters={**base, "mp_cash_status": SENT}, fields=FIELDS, order_by="mp_cash_sent_at desc")
	# Topshirish tarixi: bir vaqtda (bir daqiqada) topshirilgan buyurtmalar — bitta yozuv: qancha, qachon, qabul qilindimi
	hist = frappe.get_all(
		"Sales Order", filters={**base, "mp_cash_status": ["in", [SENT, HANDED]]},
		fields=["name", "grand_total", "mp_cash_status", "mp_cash_sent_at", "mp_cash_handed_at"], limit_page_length=500,
	)
	groups = {}
	for o in hist:
		key = str(o.mp_cash_sent_at or o.mp_cash_handed_at or "")[:16]
		g = groups.setdefault(key, {"sent_at": str(o.mp_cash_sent_at or o.mp_cash_handed_at or ""), "handed_at": "", "total": 0.0, "count": 0, "accepted": True})
		g["total"] += flt(o.grand_total)
		g["count"] += 1
		if o.mp_cash_status == HANDED:
			g["handed_at"] = max(g["handed_at"], str(o.mp_cash_handed_at or ""))
		else:
			g["accepted"] = False
	handovers = sorted(groups.values(), key=lambda g: g["sent_at"], reverse=True)[:30]
	return {
		"courier": get_fullname(user), "shop_name": frappe.db.get_value("Shop", shop, "shop_name"),
		"in_hand": in_hand, "in_hand_total": sum(flt(o.grand_total) for o in in_hand),
		"sent": sent, "sent_total": sum(flt(o.grand_total) for o in sent),
		"handovers": handovers,
	}


@frappe.whitelist(methods=["POST"])
def courier_handover(orders=None):
	"""Kuryer: "Do'kon kassiriga topshirish". orders bo'lmasa — qo'lidagi hammasi. Pul "Topshirilmoqda" bo'ladi,
	do'konchi "Qabul qildim" bosgandagina kassaga o'tadi."""
	shop = _shop()
	user = frappe.session.user
	names = frappe.parse_json(orders) if orders else None
	filters = {"shop": shop, "docstatus": 1, "mp_courier": user, "mp_cash_status": IN_HAND}
	if names:
		filters["name"] = ["in", names]
	rows = frappe.get_all("Sales Order", filters=filters, fields=["name", "grand_total"])
	if not rows:
		frappe.throw(_("Qo'lingizda topshiriladigan naqd pul yo'q"))
	now = now_datetime()
	for r in rows:
		frappe.db.set_value("Sales Order", r.name, {"mp_cash_status": SENT, "mp_cash_sent_at": now}, update_modified=False)
	total = sum(flt(r.grand_total) for r in rows)
	who = get_fullname(user)
	subject = _("{0} {1} naqd pulni topshirdi ({2} ta buyurtma) — qabul qilganingizni tasdiqlang").format(who, _money(total), len(rows))
	_notify(_shop_owners(shop), subject, rows[0].name if len(rows) == 1 else None)
	try:
		from marketplace import telegram_bot

		telegram_bot.send_to_shop(
			shop, f"💵 <b>{telegram_bot.html.escape(who)}</b> {_money(total)} naqd pulni topshirdi ({len(rows)} ta buyurtma).\n"
			"Desk → Do'konim → Naqd pul: «Qabul qildim» bosing.", with_admin=False,
		)
	except Exception:
		frappe.log_error("Kuryer topshirgan pul: Telegram xabari ketmadi")
	return {"count": len(rows), "total": total}


# ---------- Do'konchi ----------


@frappe.whitelist()
def get_couriers():
	"""Do'konchi "Pulni kim oldi?" oynasi uchun."""
	return shop_couriers(_shop())


@frappe.whitelist(methods=["POST"])
def deliver_cash(order: str, by: str):
	"""Do'konchi kuryer bilan yetkaziladigan naqd buyurtmani topshirdi: by — kuryer (pul o'sha kuryerda turadi)
	yoki "shop" (pulni do'konning o'zi oldi — darrov kassada)."""
	from marketplace.seller_desk import _not_courier, _seller_order, mark_cash_received, mark_delivered

	_not_courier()
	so = _seller_order(order)
	if so.payment_method != "Naqd":
		frappe.throw(_("Bu buyurtma naqd emas"))
	if by == "shop":
		mark_cash_received(order)
		return mark_delivered(order)
	if by not in {c["user"] for c in shop_couriers(so.shop)}:
		frappe.throw(_("Bu kuryer sizning do'koningizniki emas"))
	if flt(so.per_delivered) >= 100:
		frappe.throw(_("Bu buyurtma allaqachon topshirilgan"))
	so.db_set({"mp_courier": by, "mp_delivered_at": now_datetime(), "payment_status": "To'langan", "mp_cash_status": IN_HAND})
	stamp_paid(so.name)
	dn = mark_delivered(order)
	so.add_comment("Info", _("Topshirildi, naqd {0} kuryerda: {1}").format(_money(so.grand_total), get_fullname(by)))
	return dn


@frappe.whitelist()
def cash_summary():
	"""Do'konim "Naqd pul" bloki: kassada, kuryerlarda (har biri bo'yicha), tasdiq kutayotganlar va onlayn to'lovlar."""
	shop = _shop()
	paid = {"shop": shop, "docstatus": 1, "payment_status": "To'langan"}
	rows = frappe.get_all("Sales Order", filters={**paid, "payment_method": "Naqd"}, fields=FIELDS + ["mp_cash_status"])
	kassa = [r for r in rows if r.mp_cash_status not in (IN_HAND, SENT)]
	couriers = {}
	for r in rows:
		if r.mp_cash_status not in (IN_HAND, SENT):
			continue
		c = couriers.setdefault(r.mp_courier, {"user": r.mp_courier, "name": get_fullname(r.mp_courier) if r.mp_courier else "—",
		                                       "in_hand": 0.0, "in_hand_count": 0, "sent": 0.0, "sent_orders": []})
		if r.mp_cash_status == IN_HAND:
			c["in_hand"] += flt(r.grand_total)
			c["in_hand_count"] += 1
		else:
			c["sent"] += flt(r.grand_total)
			c["sent_orders"].append({"name": r.name, "customer_name": r.customer_name, "amount": flt(r.grand_total), "sent_at": str(r.mp_cash_sent_at or "")})
	online = frappe.get_all("Sales Order", filters={**paid, "payment_method": ["in", ["Payme", "Click"]]}, fields=["grand_total"])
	return {
		"kassa": sum(flt(r.grand_total) for r in kassa), "kassa_count": len(kassa),
		"couriers": sorted(couriers.values(), key=lambda c: -(c["in_hand"] + c["sent"])),
		"in_couriers": sum(c["in_hand"] for c in couriers.values()),
		"pending": sum(c["sent"] for c in couriers.values()),
		"online": sum(flt(r.grand_total) for r in online),
	}


@frappe.whitelist(methods=["POST"])
def accept_cash(orders):
	"""Do'konchi: "Qabul qildim" — kuryer topshirgan (yoki qo'lidagi) pul do'kon kassasiga o'tadi."""
	from marketplace.seller_desk import cash_handed_over

	names = frappe.parse_json(orders) if isinstance(orders, str) else orders
	couriers = set(frappe.get_all("Sales Order", filters={"name": ["in", names or [""]]}, pluck="mp_courier"))
	total = sum(flt(v) for v in frappe.get_all("Sales Order", filters={"name": ["in", names or [""]], "mp_cash_status": ["in", [IN_HAND, SENT]]}, pluck="grand_total"))
	done = cash_handed_over(frappe.as_json(names))
	if done:
		_notify([c for c in couriers if c], _("Do'kon {0} naqd pulni qabul qildi").format(_money(total)))
	return {"count": done, "total": total}



# ---------- Tranzaksiyalar (do'konchi: Desk → Tranzaksiyalar) ----------
# Har qator — bitta to'lov urinishi, o'z noyob ID'si bilan:
#   Payme / Click — Payment Transaction (payme.py / click.py): ID — provayderning tranzaksiya raqami. To'lanmasa
#     "Kutilmoqda" bo'lib qoladi (yoki provayder bekor qiladi); mijoz qayta to'lasa — yangi ID bilan yangi qator.
#   Naqd — Sales Order.mp_payment_id ("NQ..."), vaqti — mp_paid_at.

PROVIDERS = ("Payme", "Click", "Naqd")
# payme.py / click.py: 1 — yaratilgan (kutilmoqda), 2 — to'langan, -1 — bekor, -2 — to'langandan keyin bekor (pul qaytdi)
TXN_STATUS = {1: "Kutilmoqda", 2: "To'langan", -1: "Bekor", -2: "Qaytarilgan"}


def new_cash_id():
	while True:
		pid = "NQ" + frappe.generate_hash(length=8).upper()
		if not frappe.db.exists("Sales Order", {"mp_payment_id": pid}):
			return pid


def stamp_paid(order):
	"""Pul tushgan payt: to'langan vaqt (bir marta) va naqdda — noyob To'lov ID. payments.mark_paid va naqd yo'llari chaqiradi."""
	so = frappe.db.get_value("Sales Order", order, ["payment_method", "mp_payment_id", "mp_paid_at"], as_dict=True)
	if not so:
		return
	values = {}
	if not so.mp_paid_at:
		values["mp_paid_at"] = now_datetime()
	if so.payment_method == "Naqd" and not so.mp_payment_id:
		values["mp_payment_id"] = new_cash_id()
	if values:
		frappe.db.set_value("Sales Order", order, values, update_modified=False)


def _ms_to_local(value):
	from datetime import datetime, timezone

	from frappe.utils import convert_utc_to_system_timezone

	if not str(value or "").isdigit():
		return None
	utc = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
	return convert_utc_to_system_timezone(utc).replace(tzinfo=None)


def _product_ids(order_names):
	"""{buyurtma: [tovar ID]} — variant emas, tovarning o'zi (Iphone 17 pro max, rang/o'lchamsiz)."""
	rows = frappe.get_all(
		"Sales Order Item", filters={"parent": ["in", order_names or [""]], "parenttype": "Sales Order"},
		fields=["parent", "item_code"], order_by="idx asc",
	)
	templates = dict(frappe.get_all(
		"Item", filters={"name": ["in", list({r.item_code for r in rows}) or [""]], "variant_of": ["is", "set"]},
		fields=["name", "variant_of"], as_list=True,
	))
	out = {}
	for r in rows:
		code = templates.get(r.item_code) or r.item_code
		if code not in out.setdefault(r.parent, []):
			out[r.parent].append(code)
	return out


@frappe.whitelist()
def transactions(from_date: str | None = None, to_date: str | None = None, provider: str | None = None,
                 status: str | None = None, q: str | None = None):
	"""Do'konning to'lovlari: Payme/Click urinishlari va naqd to'lovlar — To'lov ID, vaqt, provayder, holat,
	mijoz, telefon, tovar ID'lari, summa. Kartalar — davrdagi to'langanlar provayder bo'yicha."""
	from frappe.utils import get_datetime, getdate

	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	rows = []
	for t in frappe.get_all(
		"Payment Transaction", filters={"shop": shop},
		fields=["name", "sales_order", "provider", "state", "provider_txn_id", "amount", "create_time", "perform_time", "cancel_time", "creation"],
	):
		state = TXN_STATUS.get(t.state, "Kutilmoqda")
		when = _ms_to_local(t.perform_time if t.state == 2 else t.create_time) or get_datetime(t.creation)
		rows.append({"id": t.provider_txn_id or str(t.name), "provider": t.provider, "status": state, "time": when,
		             "order": t.sales_order, "amount": flt(t.amount)})  # payme.py / click.py so'mda saqlaydi
	cash = frappe.get_all(
		"Sales Order",
		filters={"shop": shop, "docstatus": ["in", [1, 2]], "payment_method": "Naqd", "mp_placed": 1},
		fields=["name", "payment_status", "mp_payment_id", "mp_paid_at", "grand_total", "creation", "docstatus"],
	)
	for so in cash:
		if not so.mp_payment_id:  # eski yoki boshqa yo'l bilan yozilgan naqd buyurtma — ID shu yerda beriladi
			so.mp_payment_id = new_cash_id()
			frappe.db.set_value("Sales Order", so.name, "mp_payment_id", so.mp_payment_id, update_modified=False)
		state = "Bekor" if so.docstatus == 2 or so.payment_status == "Bekor" else "To'langan" if so.payment_status == "To'langan" else "Kutilmoqda"
		rows.append({"id": so.mp_payment_id, "provider": "Naqd", "status": state, "order": so.name, "amount": flt(so.grand_total),
		             "time": get_datetime(so.mp_paid_at or so.creation)})

	orders = {
		o.name: o for o in frappe.get_all(
			"Sales Order", filters={"name": ["in", list({r["order"] for r in rows if r["order"]}) or [""]]},
			fields=["name", "customer_name", "customer_phone"],
		)
	}
	products = _product_ids(list(orders))
	start, end = getdate(from_date) if from_date else None, getdate(to_date) if to_date else None
	text = (q or "").strip().lower()
	out, totals = [], {p: {"amount": 0.0, "count": 0} for p in PROVIDERS}
	pending = 0
	for r in rows:
		if (start and r["time"].date() < start) or (end and r["time"].date() > end):
			continue
		so = orders.get(r["order"]) or frappe._dict()
		r.update(customer_name=so.customer_name, phone=so.customer_phone, products=products.get(r["order"], []), time=str(r["time"]))
		if r["status"] == "To'langan":
			totals[r["provider"]]["amount"] += r["amount"]
			totals[r["provider"]]["count"] += 1
		elif r["status"] == "Kutilmoqda":
			pending += 1
		if provider and r["provider"] != provider:
			continue
		if status and r["status"] != status:
			continue
		if text and text not in " ".join([r["id"], r["order"] or "", so.customer_name or "", so.customer_phone or ""] + r["products"]).lower():
			continue
		out.append(r)
	out.sort(key=lambda x: x["time"], reverse=True)
	return {
		"rows": out[:500], "totals": totals, "pending": pending,
		"total": {"amount": sum(v["amount"] for v in totals.values()), "count": sum(v["count"] for v in totals.values())},
	}


@frappe.whitelist()
def transaction_items(order: str):
	"""Tovar ID bosilganda: shu to'lovdagi mijoz nima xarid qilgani — rasm, nomi, rang/o'lcham, soni, narxi."""
	from marketplace.storefront import variant_labels

	shop = _shop()
	so = frappe.get_doc("Sales Order", order)
	if so.shop != shop:
		frappe.throw(_("Bu buyurtma sizning do'koningizniki emas"), frappe.PermissionError)
	codes = [i.item_code for i in so.items]
	info = {i.name: i for i in frappe.get_all("Item", filters={"name": ["in", codes or [""]]}, fields=["name", "item_name", "variant_of", "image"])}
	bases = {i.name: i for i in frappe.get_all(
		"Item", filters={"name": ["in", [i.variant_of for i in info.values() if i.variant_of] or [""]]}, fields=["name", "item_name", "image"])}
	labels = variant_labels(codes)
	items = []
	for i in so.items:
		it = info.get(i.item_code) or frappe._dict()
		base = bases.get(it.variant_of) or it
		items.append({"product_id": base.name or i.item_code, "name": base.item_name or i.item_name, "variant": labels.get(i.item_code) or "",
		              "image": it.image or base.image, "qty": flt(i.qty), "rate": flt(i.rate), "amount": flt(i.amount)})
	return {"order": so.name, "customer_name": so.customer_name, "phone": so.customer_phone, "total": flt(so.grand_total),
	        "date": str(so.transaction_date), "items": items}
