"""Mijoz buyurtmasi: savat -> ERPNext Sales Order.

Qoidalar:
  * narx, ulgurji chegara va qoldiq faqat serverdan (storefront.get_cart_lines); brauzer
    yuborgan narxga hech qachon ishonilmaydi;
  * bitta buyurtma = bitta do'kon = bitta kassa;
  * Sales Order darhol submit qilinadi: summa qotadi (Payme aynan shu summani tekshiradi)
    va qoldiq zaxiralanadi (Bin.reserved_qty);
  * lekin u sotuvchi uchun hali "buyurtma" emas (mp_placed = 0): mijoz naqdni tanlaganda yoki
    Payme/Click to'lovi o'tganda confirm_order chaqiriladi — shundagina do'konga ko'rinadi va xabar boradi.
    To'lanmay qolgan buyurtmalar 24 soatdan keyin bekor qilinadi, zaxira bo'shaydi (cancel_abandoned).
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, getdate, now_datetime, today

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
	if delivery_method == "O'zim olaman" and not cint(shop.get("enable_pickup", 1)):
		frappe.throw(_("Bu do'kon faqat kuryer orqali yetkazib beradi"))
	address = (address or "").strip()
	if delivery_method == "Kuryer" and len(address) < 5:
		frappe.throw(_("Yetkazib berish manzilini yozing"), title=_("Manzil"))
	_release_pending(shop.name, customer)

	cart = storefront.get_cart_lines(shop, lines)
	if not cart:
		frappe.throw(_("Savat bo‘sh yoki tovarlar tugagan"))

	requested = {line.get("code"): int(line.get("qty") or 0) for line in lines}
	short = [c["name"] for c in cart if c["qty"] < requested.get(c["code"], 0)]
	if short:
		frappe.throw(_("Yetarli qolmagan: {0}. Savatni yangilang.").format(", ".join(short)))

	need = mandatory_status(shop, customer, [c["code"] for c in cart])
	if need["required"]:
		frappe.throw(
			_("Buyurtma berish uchun avval «{0}» ni xarid qilishingiz kerak — uni savatga qo'shing").format(
				", ".join(i["name"] for i in need["items"])
			),
			title=_("Majburiy tovar"),
		)

	with as_system():
		return _create_sales_order(shop, cart, delivery_method, address, customer)


def _release_pending(shop_name, customer):
	"""Mijoz to'lov sahifasidan qaytib, savatni qayta rasmiylashtiryapti: oldingi yakunlanmagan buyurtmasi bekor
	qilinadi — zaxira bo'shaydi (aks holda oxirgi dona "yetarli qolmagan" bo'lib qoladi), do'konda ikkita
	to'lanmagan buyurtma turmaydi. Yangi buyurtma yaratilmasa (xato) — so'rov bilan birga orqaga qaytadi.
	Payme/Click'da to'lov jarayoni ochilgan buyurtmaga tegilmaydi (pul tushib qolishi mumkin) — uni
	24 soatdan keyin cancel_abandoned yopadi."""
	for name in frappe.get_all(
		"Sales Order",
		filters={"shop": shop_name, "customer": customer.customer, "docstatus": 1, "mp_placed": 0,
		         "payment_status": ["not in", ["To'langan", "Bekor"]]},
		pluck="name",
	):
		if _gateway_open(name):
			continue
		with as_system():
			so = frappe.get_doc("Sales Order", name)
			so.db_set("payment_status", "Bekor")
			so.cancel()
			so.add_comment("Info", _("Mijoz savatga qaytib, qayta rasmiylashtirdi — bu yakunlanmagan buyurtma bekor qilindi"))


def _gateway_open(name):
	# Payment Transaction holati: 1 — yaratilgan (to'lanmoqda), 2 — o'tgan (payme.py / click.py)
	return frappe.db.exists("Payment Transaction", {"sales_order": name, "state": ["in", [1, 2]]})


def held_by(name):
	"""To'lanmagan buyurtma zaxiralagan tovarlar {kod: soni} — qayta rasmiylashtirilsa bo'shaydi (_release_pending).
	To'lov jarayoni ochiq bo'lsa — bo'shamaydi, demak qaytarib hisoblanmaydi."""
	if _gateway_open(name):
		return {}
	held = {}
	for row in frappe.get_all("Sales Order Item", filters={"parent": name}, fields=["item_code", "qty"]):
		held[row.item_code] = held.get(row.item_code, 0) + flt(row.qty)
	return held


def pending_state(shop_name, name, customer):
	"""Savat sahifasi: shu brauzerda boshlangan buyurtma nima bo'ldi — done (yakunlangan: savatdan olinadi),
	pending (to'lanmagan: savat turadi), cancelled / gone."""
	so = customer and frappe.db.get_value(
		"Sales Order", {"name": name, "shop": shop_name, "customer": customer.customer},
		["name", "docstatus", "mp_placed", "payment_status"], as_dict=True,
	)
	if not so:
		return {"state": "gone"}
	if so.docstatus == 2 or so.payment_status == "Bekor":
		state = "cancelled"
	elif so.mp_placed or so.payment_status == "To'langan":
		state = "done"
	else:
		state = "pending"
	return {"name": so.name, "state": state, "url": f"/s/{shop_name}/buyurtma/{so.name}"}


# ---------------- Majburiy tovar ----------------
# Do'konda "Majburiy tovar" (Item.mp_majburiy) bo'lsa: har bir majburiy tovar alohida — mijoz uni bir marta
# bo'lsa ham olgan bo'lishi yoki savatida bo'lishi kerak, aks holda boshqa buyurtma bera olmaydi. Keyin yangi
# majburiy tovar qo'shilsa — eski mijoz ham uni oladi. "Olgan" — shu raqamdan bekor qilinmagan, yakunlangan
# buyurtmada bo'lgan, yoki call-center eski raqamni tekshirib aynan shu tovarga tasdiq bergan (Majburiy Tasdiq).


def mandatory_items(shop_name):
	"""Do'konning majburiy tovarlari (andozalar): saytda, sotuvda ("tez kunda" emas)."""
	return frappe.get_all(
		"Item",
		filters={"shop": shop_name, "mp_majburiy": 1, "disabled": 0, "is_published": 1, "variant_of": ["is", "not set"],
		         "mp_tez_kunda": 0},
		pluck="name",
		order_by="creation",
	)


def mandatory_bought(shop_name, phone, mandatory=None):
	"""Shu raqam (+998...) qaysi majburiy tovarlarni olgan: {andoza: asos} — buyurtma raqami yoki tasdiq raqami."""
	mandatory = mandatory_items(shop_name) if mandatory is None else mandatory
	if not mandatory or not phone:
		return {}
	template_of = {code: code for code in mandatory}
	template_of.update(
		frappe.get_all("Item", filters={"variant_of": ["in", mandatory]}, fields=["name", "variant_of"], as_list=True)
	)
	so = frappe.qb.DocType("Sales Order")
	soi = frappe.qb.DocType("Sales Order Item")
	rows = (
		frappe.qb.from_(so).join(soi).on(soi.parent == so.name)
		.select(soi.item_code, so.name)
		.where(so.shop == shop_name).where(so.customer_phone == phone).where(so.docstatus == 1)
		.where(so.mp_placed == 1).where(so.payment_status != "Bekor").where(soi.item_code.isin(list(template_of)))
		.orderby(so.creation).run()
	)
	out = {}
	for code, order in rows:
		out.setdefault(template_of[code], order)
	for t in frappe.get_all(
		"Majburiy Tasdiq", filters={"shop": shop_name, "telefon": phone, "tovar": ["in", mandatory]},
		fields=["tovar", "name"], order_by="creation",
	):
		out.setdefault(t.tovar, t.name)
	return out


def mandatory_status(shop, customer, codes):
	"""Savat uchun: {"required": bool, "items": [hali olinmagan majburiy tovarlar kartochkasi], "call_center": ...}.
	Har bir majburiy tovar: savatda bo'lsa yoki mijoz uni avval olgan bo'lsa — talab qilinmaydi.
	Omborda tugagan majburiy tovar talab qilinmaydi: uni olib bo'lmaydi, do'kon savdosi to'xtab qolmasin."""
	mandatory = mandatory_items(shop.name)
	if not mandatory:
		return {"required": False}
	in_cart = set(codes) | set(
		frappe.get_all("Item", filters={"name": ["in", list(codes) or [""]], "variant_of": ["is", "set"]}, pluck="variant_of")
	)
	bought = mandatory_bought(shop.name, customer.phone, mandatory) if customer else {}
	catalog = {p["code"]: p for p in storefront.get_catalog(shop)["items"]}
	todo = [c for c in mandatory if c not in in_cart and c not in bought and c in catalog]
	# Qoldiq jonli (katalog keshi 5 daqiqagacha eski bo'lishi mumkin): endigina tugagan tovarni so'rab, mijozni
	# qotirib qo'ymaymiz — savat ham qoldiqni jonli tekshiradi
	live = storefront._get_stock(todo, shop.warehouse) if todo else {}
	live.update(storefront._get_variant_stock([c for c in todo if catalog[c].get("has_variants")], shop.warehouse))
	items = [
		{k: catalog[c].get(k) for k in ("code", "name", "price", "old_price", "discount", "thumb", "has_variants")}
		| {"in_stock": True}
		for c in todo
		if catalog[c].get("stock_qty") is None or live.get(c, 0) > 0
	]
	return {"required": bool(items), "logged_in": bool(customer), "items": items, "call_center": shop.get("phone")}


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
			"mp_placed": 0,
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
			"transaction_date", "creation", "docstatus", "status", "per_delivered", "mp_placed",
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


def update_address(name, address, customer):
	"""To'lov sahifasida manzilni tuzatish: buyurtma hali do'konga bormagan (mp_placed = 0, to'lanmagan) bo'lsa.
	Do'konga borganidan keyin manzil faqat do'kon orqali o'zgaradi — kuryer eski manzilga yo'l olgan bo'lishi mumkin."""
	so = get_order_for_customer(name, customer)
	address = " ".join((address or "").split())
	if so.delivery_method != "Kuryer":
		frappe.throw(_("Bu buyurtma do‘kondan olib ketiladi — manzil kerak emas"))
	if len(address) < 5:
		frappe.throw(_("Yetkazib berish manzilini yozing"), title=_("Manzil"))
	if so.payment_status == "To'langan" or frappe.db.get_value("Sales Order", name, "mp_placed"):
		frappe.throw(_("Buyurtma do‘konga yuborilgan. Manzilni o‘zgartirish uchun do‘kon bilan bog‘laning."))
	frappe.db.set_value("Sales Order", name, "delivery_address", address[:500])
	return {"address": address[:500]}


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
		confirm_order(name)
		return {"status": "confirmed"}
	# Payme / Click: mijoz to'lov sahifasiga (telefonda ilovaga) yuboriladi
	return {"status": "pending_gateway", "redirect": payments.checkout_url(so, method)}


# ---------------- Buyurtma do'konga qachon boradi ----------------


def confirm_order(name):
	"""Mijoz buyurtmani yakunladi (naqd tanladi yoki to'ladi): endi do'kon ko'radi va xabar oladi.
	Qaytaradi: True — hozir tasdiqlandi, False — avval tasdiqlangan edi."""
	from marketplace.inventory import enqueue_low_stock_check

	if frappe.db.get_value("Sales Order", name, "mp_placed"):
		return False
	frappe.db.set_value("Sales Order", name, "mp_placed", 1)
	so = frappe.get_doc("Sales Order", name)
	_notify(so)
	enqueue_low_stock_check(so)
	return True


def sales_order_on_submit(doc, method=None):
	"""Qo'lda kiritilgan (Desk) buyurtma darhol "berilgan": xabar shu yerda. Saytdagisi — confirm_order'da."""
	if doc.get("mp_placed"):
		_notify(doc)


def _notify(so):
	from marketplace.seller_desk import notify_new_order
	from marketplace.telegram_bot import enqueue_order_notification

	notify_new_order(so)
	enqueue_order_notification(so)


def cancel_abandoned():
	"""Har soat: 24 soat ichida to'lov usuli tanlanmagan / to'lanmagan sayt buyurtmalari bekor qilinadi
	(do'kon ularni umuman ko'rmagan) — omborda zaxira qilingan tovar yana sotuvga chiqadi."""
	for name in frappe.get_all(
		"Sales Order",
		filters={
			"docstatus": 1,
			"mp_placed": 0,
			"payment_status": ["!=", "To'langan"],
			"creation": ["<", add_to_date(now_datetime(), hours=-24)],
		},
		pluck="name",
	):
		try:
			so = frappe.get_doc("Sales Order", name)
			# Sotuv menejeri mijoz bilan gaplashib, qayta qo'ng'iroq sanasini qo'ygan — u kungacha kutamiz
			if so.get("mp_keyingi_qongiroq") and getdate(so.mp_keyingi_qongiroq) >= getdate():
				continue
			so.flags.ignore_permissions = True
			so.db_set("payment_status", "Bekor")
			so.cancel()
			so.add_comment("Info", _("Mijoz 24 soat ichida buyurtmani yakunlamadi — avtomatik bekor qilindi"))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Tashlab ketilgan buyurtma bekor qilinmadi: {name}")
