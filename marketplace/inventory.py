"""Do'kon omboridagi qoldiqni o'zgartirish va "kam qoldi / tugadi" ogohlantirishlari.

Qoldiq faqat tovar formasining "Ombor" tabidan receive() orqali oshadi: kimdan olindi, nechta, necha puldan.
Ombor sahifasi, /panel va Telegram bot — faqat ko'rish.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

DEFAULT_LOW_STOCK = 3


def low_threshold(shop):
	value = frappe.db.get_value("Shop", shop, "low_stock_qty")
	return DEFAULT_LOW_STOCK if value is None else cint(value)


def status_of(available, threshold):
	if available <= 0:
		return "Tugagan"
	if available <= threshold:
		return "Kam qolgan"
	return ""


def shop_warehouse(shop):
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	if not warehouse:
		frappe.throw(_("Do'kon ombori topilmadi"))
	return warehouse


def stock_of(codes, warehouse):
	"""{item_code: (actual, reserved)} — do'kon omboridagi joriy holat."""
	if not codes:
		return {}
	return {
		b.item_code: (flt(b.actual_qty), flt(b.reserved_qty))
		for b in frappe.get_all(
			"Bin",
			filters={"item_code": ["in", list(codes)], "warehouse": warehouse},
			fields=["item_code", "actual_qty", "reserved_qty"],
		)
	}


class StockDecreaseError(frappe.ValidationError):
	pass


def receive(warehouse, rows, supplier, remarks=None):
	"""Kirim: rows = [(item_code, kelgan son, 1 donasining olish narxi)], supplier — shu do'konning Kontragent'i.
	Bitta "Material Receipt" hujjati (100 qator = 1 hujjat): kimdan olingani mp_kontragent'da, narx — qatorning
	basic_rate'ida. Oylik chiqim (reports.get_month_summary) va kontragent xaridlari shu yerdan hisoblanadi.

	Ombor faqat kirim bilan ko'payadi va faqat sotuv (Delivery Note) bilan kamayadi: qo'lda ayirish yo'q,
	shuning uchun "50 ta keldi, 49 ta yozildi" kabi yo'qotishlar hisobotda ko'rinib turadi.
	Tuzatishni faqat administrator ERPNext'ning Stock Reconciliation hujjati bilan qiladi.
	Ruxsat chaqiruvchida tekshirilgan bo'lishi kerak."""
	shop = frappe.db.get_value("Shop", {"warehouse": warehouse}, "name")
	if not supplier or frappe.db.get_value("Kontragent", supplier, "shop") != shop:
		frappe.throw(_("Tovar qaysi kontragentdan olinganini ro'yxatdan tanlang"))
	items = []
	for code, qty, rate in rows:
		qty = flt(qty)
		if qty < 0:
			frappe.throw(_("Ombordan qo'lda ayirib bo'lmaydi: tovar faqat sotuv orqali kamayadi"), StockDecreaseError)
		if qty != int(qty):
			frappe.throw(_("Soni butun bo'lishi kerak"))
		if flt(rate) <= 0:
			frappe.throw(_("1 donasi necha puldan olinganini yozing"))
		if qty:
			# allow_zero_valuation_rate qo'yilmaydi: u bor bo'lsa ERPNext basic_rate'ni 0 qilib yuboradi
			items.append({"item_code": code, "qty": qty, "t_warehouse": warehouse, "basic_rate": flt(rate)})
	if not items:
		return
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": frappe.db.get_value("Warehouse", warehouse, "company"),
			"to_warehouse": warehouse,
			"mp_kontragent": supplier,
			"remarks": remarks,
			"items": items,
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	for row in items:
		frappe.cache.hdel("mp_low_stock", row["item_code"])


# ---------- "Kam qoldi / tugadi" ogohlantirishi ----------


def enqueue_low_stock_check(doc, method=None):
	"""Buyurtma zaxiraga oladi, bo'sh qoldiq kamayadi — tekshiruv navbatga. Desk'dagi buyurtmada — on_submit'da;
	saytdagisida esa mijoz buyurtmani yakunlagandan keyin (naqd tanladi yoki to'ladi — orders.confirm_order):
	to'lov sahifasida turgan, hali hech narsa tanlamagan mijoz uchun do'konchiga xabar bormasin."""
	if doc.get("shop") and doc.get("mp_placed"):
		frappe.enqueue(
			"marketplace.inventory.check_low_stock",
			shop=doc.shop,
			item_codes=list({i.item_code for i in doc.items}),
			queue="short",
			enqueue_after_commit=True,
		)


def check_low_stock(shop, item_codes):
	"""Chegaraga tushgan tovarlar haqida egasiga darhol xabar. Bir holat uchun bir marta yuboriladi
	(qoldiq to'ldirilganda belgi o'chadi — receive)."""
	from marketplace import telegram_bot

	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	if not warehouse or not telegram_bot.token():
		return
	threshold = low_threshold(shop)
	stock = stock_of(item_codes, warehouse)
	lines = []
	for code in item_codes:
		actual, reserved = stock.get(code, (0, 0))
		status = status_of(actual - reserved, threshold)
		if not status:
			frappe.cache.hdel("mp_low_stock", code)
			continue
		if frappe.cache.hget("mp_low_stock", code) == status:
			continue
		frappe.cache.hset("mp_low_stock", code, status)
		name = frappe.db.get_value("Item", code, "item_name")
		left = max(cint(actual - reserved), 0)
		lines.append(("❌ " if status == "Tugagan" else "⚠️ ") + f"{telegram_bot.html.escape(name)} — <b>{left}</b> ta qoldi")
	if lines:
		more = f"\n… yana {len(lines) - 30} ta" if len(lines) > 30 else ""
		text = "📉 <b>Omborda kam qoldi</b>\n\n" + "\n".join(lines[:30]) + more + "\n\nKirim: Desk → Tovarlar → tovar → <b>Ombor</b> tabi"
		telegram_bot.send_to_shop(shop, text, with_admin=False)


def daily_low_stock_digest():
	"""Har kuni ertalab: har bir do'kon egasiga kam qolgan va tugagan tovarlar ro'yxati."""
	from marketplace import telegram_bot
	from marketplace.stock_page import shop_products

	if not telegram_bot.token():
		return
	for shop in frappe.get_all("Shop", filters={"status": ["!=", "Suspended"], "telegram_ids": ["is", "set"]}, pluck="name"):
		try:
			products = shop_products(shop)["products"]
			low, out = [], []
			for p in products:
				rows = p["variants"] if p["is_template"] else [dict(p, label=None)]
				for r in rows:
					if r["status"]:
						label = p["name"] + (f" ({r['label']})" if r.get("label") else "")
						(out if r["status"] == "Tugagan" else low).append(f"{label} — {cint(r['available'])}")
			if not (low or out):
				continue
			esc = telegram_bot.html.escape
			parts = ["☀️ <b>Ombor: ertalabki hisobot</b>", ""]
			if out:
				parts.append(f"❌ <b>Tugagan ({len(out)})</b>")
				parts += [f"• {esc(x)}" for x in out[:25]] + ([f"… yana {len(out) - 25} ta"] if len(out) > 25 else [])
				parts.append("")
			if low:
				parts.append(f"⚠️ <b>Kam qolgan ({len(low)})</b>")
				parts += [f"• {esc(x)}" for x in low[:25]] + ([f"… yana {len(low) - 25} ta"] if len(low) > 25 else [])
			telegram_bot.send_to_shop(shop, "\n".join(parts), with_admin=False)
		except Exception:
			frappe.log_error(f"Ombor hisoboti yuborilmadi: {shop}", "Telegram bot")
