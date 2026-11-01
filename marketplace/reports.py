"""Sotuvchi hisoboti (Desk → Hisobot): tanlangan sanalar oralig'ida tushgan pul, buyurtmalar, eng ko'p
sotilganlar va ombor harakati (keldi, sotildi, kamomad) hamda harakatlar tarixi.

journal() tovar formasidagi "Ombor" tabi va Ombor sahifasida ham ishlatiladi (u yerda faqat kirimlar).
get_month_summary() — Do'konim bosh sahifasidagi oylik kirim (sotuvdan) va chiqim (tovar olishga)."""

from datetime import timedelta

import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, Count, IfNull, Sum
from frappe.utils import add_months, cint, flt, get_first_day, getdate, today

from marketplace.permissions import get_user_shop, group_title

PAID = "To'langan"
CANCELLED = "Bekor"
ADMIN_ROLES = {"System Manager", "Marketplace Manager"}
DAILY_MAX_DAYS = 62  # undan uzun davr grafigi oylar bo'yicha


@frappe.whitelist()
def get_sales_report(from_date=None, to_date=None, shop=None):
	"""Sanalar kiritilmasa — shu oy boshidan bugungacha. Sotuvchi faqat o'z do'konini ko'radi."""
	shop = _resolve_shop(shop)
	end = getdate(to_date or today())
	start = getdate(from_date) if from_date else get_first_day(end)
	if start > end:
		start, end = end, start
	if (end - start).days > 366 * 3:
		frappe.throw("Davr 3 yildan oshmasin")

	# Taqqoslash: xuddi shuncha uzun oldingi davr
	length = (end - start).days + 1
	prev_end = start - timedelta(days=1)
	prev_start = prev_end - timedelta(days=length - 1)

	summary = _summary(shop, start, end)
	prev = _summary(shop, prev_start, prev_end)
	summary["change"] = {key: _pct(summary[key], prev[key]) for key in ("sales", "revenue", "orders")}
	# Platforma admini (do'kon panelidan tashqarida) ombor bilan ishlamaydi: unga pul va buyurtmalar,
	# "Barcha do'konlar"da esa har bir do'kon bo'yicha jadval
	admin_area = _is_admin() and not get_user_shop()

	return {
		"shop": shop,
		"from_date": str(start),
		"to_date": str(end),
		"days": length,
		"is_admin": _is_admin(),
		"shops": _shop_options() if _is_admin() else [],
		"summary": summary,
		"previous": prev,
		"series": _series(shop, start, end),
		"top_products": _top_products(shop, start, end),
		"categories": _categories(shop, start, end),
		"payment_methods": _payment_methods(shop, start, end),
		"stock": None if admin_area else _stock_movement(shop, start, end),
		"by_shop": _by_shop(start, end) if admin_area and not shop else None,
	}


def _by_shop(start, end):
	"""Admin, "Barcha do'konlar": har bir do'kon — nechta buyurtma, kassaga qancha tushdi (Payme / Click / Naqd),
	to'lanishi kutilayotgani va bekor qilinganlari. Buyurtmasi bo'lmagan do'konlar ham (0 bilan) chiqadi."""
	so, q = _so_query(None, start, end)
	paid = _active(so) & (so.payment_status == PAID)
	pending = _active(so) & (IfNull(so.payment_status, "") != PAID)

	def paid_by(method):
		return Sum(Case().when(paid & (so.payment_method == method), so.grand_total).else_(0))

	rows = {
		r.shop: r
		for r in q.select(
			so.shop,
			Sum(Case().when(_active(so), 1).else_(0)).as_("orders"),
			Sum(Case().when(paid, 1).else_(0)).as_("paid"),
			Sum(Case().when(paid, so.grand_total).else_(0)).as_("revenue"),
			Sum(Case().when(pending, so.grand_total).else_(0)).as_("pending_amount"),
			Sum(Case().when(_is_cancelled(so), 1).else_(0)).as_("cancelled"),
			paid_by("Payme").as_("payme"),
			paid_by("Click").as_("click"),
			paid_by("Naqd").as_("naqd"),
		)
		.groupby(so.shop)
		.run(as_dict=True)
	}
	out = []
	for s in _shop_options():
		r = rows.get(s.name) or {}
		out.append(
			{
				"shop": s.name,
				"shop_name": s.shop_name,
				**{k: cint(r.get(k)) for k in ("orders", "paid", "cancelled")},
				**{k: flt(r.get(k)) for k in ("revenue", "pending_amount", "payme", "click", "naqd")},
			}
		)
	return sorted(out, key=lambda x: (-x["revenue"], -x["orders"], x["shop_name"] or ""))


def _is_admin():
	return frappe.session.user == "Administrator" or bool(ADMIN_ROLES & set(frappe.get_roles()))


def _resolve_shop(shop):
	# Sotuvchi uchun mijozdan kelgan shop'ga ishonmaymiz
	if not _is_admin():
		own = get_user_shop()
		if not own:
			frappe.throw("Siz hech qaysi do'konga biriktirilmagansiz", frappe.PermissionError)
		return own
	if shop and not frappe.db.exists("Shop", shop):
		frappe.throw("Do'kon topilmadi")
	# Admin do'kon panelida bo'lsa (Do'kon paneliga kirish) — o'sha do'kon
	return shop or get_user_shop() or None


def _pct(cur, prev):
	if not prev:
		return None
	return round((flt(cur) - flt(prev)) * 100 / flt(prev), 1)


def _so_query(shop, start, end):
	so = frappe.qb.DocType("Sales Order")
	q = frappe.qb.from_(so).where(so.transaction_date[start:end]).where(so.docstatus > 0).where(so.mp_placed == 1)
	if shop:
		q = q.where(so.shop == shop)
	return so, q


def _is_cancelled(so):
	return (so.docstatus == 2) | (IfNull(so.payment_status, "") == CANCELLED)


def _active(so):
	return (so.docstatus == 1) & (IfNull(so.payment_status, "") != CANCELLED)


def _summary(shop, start, end):
	so, q = _so_query(shop, start, end)
	paid = _active(so) & (so.payment_status == PAID)
	pending = _active(so) & (IfNull(so.payment_status, "") != PAID)
	row = q.select(
		Sum(Case().when(_active(so), 1).else_(0)).as_("orders"),
		Sum(Case().when(paid, 1).else_(0)).as_("paid"),
		Sum(Case().when(pending, 1).else_(0)).as_("pending"),
		Sum(Case().when(_is_cancelled(so), 1).else_(0)).as_("cancelled"),
		Sum(Case().when(_active(so) & (so.per_delivered >= 100), 1).else_(0)).as_("delivered"),
		# Savdo — bekor qilinmagan barcha buyurtmalar; tushum — shulardan to'langani
		Sum(Case().when(_active(so), so.grand_total).else_(0)).as_("sales"),
		Sum(Case().when(paid, so.grand_total).else_(0)).as_("revenue"),
		Sum(Case().when(pending, so.grand_total).else_(0)).as_("pending_amount"),
		Sum(Case().when(_is_cancelled(so), so.grand_total).else_(0)).as_("cancelled_amount"),
	).run(as_dict=True)[0]
	money = ("sales", "revenue", "pending_amount", "cancelled_amount")
	return {k: (flt(v) if k in money else cint(v)) for k, v in row.items()}


def _series(shop, start, end):
	"""Grafik: 62 kungacha — kunlar, undan uzun — oylar bo'yicha."""
	daily = (end - start).days < DAILY_MAX_DAYS
	so, q = _so_query(shop, start, end)
	paid = _active(so) & (so.payment_status == PAID)
	rows = (
		q.select(
			so.transaction_date.as_("day"),
			Sum(Case().when(_active(so), 1).else_(0)).as_("orders"),
			Sum(Case().when(_active(so), so.grand_total).else_(0)).as_("sales"),
			Sum(Case().when(paid, so.grand_total).else_(0)).as_("revenue"),
		)
		.groupby(so.transaction_date)
		.run(as_dict=True)
	)
	buckets = {}
	cur = start if daily else get_first_day(start)
	while cur <= end:
		buckets[cur] = {"from": str(max(cur, start)), "orders": 0, "sales": 0.0, "revenue": 0.0}
		nxt = cur + timedelta(days=1) if daily else getdate(add_months(cur, 1))
		buckets[cur]["to"] = str(min(nxt - timedelta(days=1), end))
		cur = nxt
	for r in rows:
		key = getdate(r.day) if daily else get_first_day(r.day)
		b = buckets.get(key)
		if b:
			b["orders"] += cint(r.orders)
			b["sales"] += flt(r.sales)
			b["revenue"] += flt(r.revenue)
	return {"unit": "day" if daily else "month", "points": list(buckets.values())}


def _lines_query(shop, start, end):
	"""Bekor qilinmagan buyurtmalar qatorlari (sotilgan tovarlar)."""
	so = frappe.qb.DocType("Sales Order")
	soi = frappe.qb.DocType("Sales Order Item")
	q = (
		frappe.qb.from_(soi)
		.join(so)
		.on(soi.parent == so.name)
		.where(soi.parenttype == "Sales Order")
		.where(so.transaction_date[start:end])
		.where(_active(so))
		.where(so.mp_placed == 1)
	)
	if shop:
		q = q.where(so.shop == shop)
	return so, soi, q


def _top_products(shop, start, end, limit=10):
	so, soi, q = _lines_query(shop, start, end)
	item = frappe.qb.DocType("Item")
	# Variantlar shablon ostida jamlanadi (rang/o'lcham alohida chiqmasin)
	code = Coalesce(item.variant_of, soi.item_code)
	rows = (
		q.left_join(item)
		.on(item.name == soi.item_code)
		.select(
			code.as_("item_code"),
			# "Sotildi" — faqat puli tushgan buyurtmalar (yig'indisi "Kassaga tushgan pul"ga teng);
			# to'lanmaganlari alohida — "To'lov kutilmoqda"
			Sum(Case().when(so.payment_status == PAID, soi.qty).else_(0)).as_("qty"),
			Sum(Case().when(so.payment_status == PAID, soi.amount).else_(0)).as_("amount"),
			Sum(Case().when(so.payment_status != PAID, soi.qty).else_(0)).as_("wait_qty"),
			Sum(Case().when(so.payment_status != PAID, soi.amount).else_(0)).as_("wait_amount"),
			Count(soi.parent).distinct().as_("orders"),
			Count(soi.item_code).distinct().as_("variants"),
		)
		.groupby(code)
		.run(as_dict=True)
	)
	if not rows:
		return {"by_qty": [], "by_amount": []}

	info = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", [r.item_code for r in rows]]},
			fields=["name", "item_name", "image", "item_group", "has_variants"],
		)
	}
	# Shablonda rasm bo'lmasa, birinchi rasmli variantdan olamiz
	no_image = [r.item_code for r in rows if not (info.get(r.item_code) or {}).get("image")]
	variant_images = {}
	if no_image:
		for v in frappe.get_all(
			"Item",
			filters={"variant_of": ["in", no_image], "image": ["is", "set"]},
			fields=["variant_of", "image"],
			order_by="name asc",
		):
			variant_images.setdefault(v.variant_of, v.image)

	out = []
	for r in rows:
		i = info.get(r.item_code) or frappe._dict()
		out.append(
			{
				"item_code": r.item_code,
				"item_name": i.item_name or r.item_code,
				"image": i.image or variant_images.get(r.item_code),
				"item_group": group_title(i.item_group),
				"qty": flt(r.qty),
				"amount": flt(r.amount),
				"wait_qty": flt(r.wait_qty),
				"wait_amount": flt(r.wait_amount),
				"orders": cint(r.orders),
				"variants": cint(r.variants) if i.has_variants else 0,
			}
		)
	return {
		"by_qty": sorted(out, key=lambda x: (-x["qty"], -x["amount"], -x["wait_qty"]))[:limit],
		"by_amount": sorted(out, key=lambda x: (-x["amount"], -x["qty"], -x["wait_amount"]))[:limit],
	}


def _categories(shop, start, end):
	so, soi, q = _lines_query(shop, start, end)
	group = IfNull(soi.item_group, "")
	rows = (
		q.where(so.payment_status == PAID)  # faqat puli tushgan sotuvlar
		.select(group.as_("item_group"), Sum(soi.qty).as_("qty"), Sum(soi.amount).as_("amount"))
		.groupby(group)
		.run(as_dict=True)
	)
	return sorted(
		({"item_group": group_title(r.item_group) or "Boshqa", "qty": flt(r.qty), "amount": flt(r.amount)} for r in rows),
		key=lambda x: -x["amount"],
	)


def _payment_methods(shop, start, end):
	so, q = _so_query(shop, start, end)
	method = IfNull(so.payment_method, "")
	paid = so.payment_status == PAID
	rows = (
		q.where(_active(so))
		.select(
			method.as_("method"),
			Count("*").as_("orders"),
			Sum(so.grand_total).as_("amount"),
			Sum(Case().when(paid, so.grand_total).else_(0)).as_("paid_amount"),
		)
		.groupby(method)
		.run(as_dict=True)
	)
	by = {r.method: r for r in rows}
	out = []
	for m in ("Payme", "Click", "Naqd", *sorted(set(by) - {"Payme", "Click", "Naqd"})):
		r = by.get(m)
		if r or m:
			out.append(
				{
					"method": m or "To'lov turi tanlanmagan",
					"orders": cint(r and r.orders),
					"amount": flt(r and r.amount),
					"paid_amount": flt(r and r.paid_amount),
				}
			)
	return out


def _shop_options():
	return frappe.get_all("Shop", fields=["name", "shop_name"], order_by="shop_name asc")


# ---------- Ombor harakati ----------


def _shop_warehouses(shop):
	filters = {"name": shop} if shop else {}
	return [w for w in frappe.get_all("Shop", filters=filters, pluck="warehouse") if w]


def _deltas(warehouses, item_codes=None, end=None):
	"""Ombor yozuvlari (eskisidan yangisiga), har biriga delta — qoldiq qanchaga o'zgargani.
	Stock Reconciliation'da actual_qty 0 bo'ladi, shuning uchun o'zgarish qoldiq farqidan olinadi."""
	sle = frappe.qb.DocType("Stock Ledger Entry")
	q = (
		frappe.qb.from_(sle)
		.select(
			sle.item_code, sle.warehouse, sle.posting_date, sle.posting_time, sle.creation, sle.owner,
			sle.voucher_type, sle.voucher_no, sle.qty_after_transaction, sle.incoming_rate,
		)
		.where(sle.is_cancelled == 0)
		.where(sle.warehouse.isin(warehouses))
		.orderby(sle.posting_date)
		.orderby(sle.posting_time)
		.orderby(sle.creation)
	)
	if item_codes is not None:
		q = q.where(sle.item_code.isin(list(item_codes) or [""]))
	if end:
		q = q.where(sle.posting_date <= end)
	last = {}  # (tovar, ombor) -> oldingi qoldiq
	for r in q.run(as_dict=True):
		key = (r.item_code, r.warehouse)
		r.after = flt(r.qty_after_transaction)
		r.delta = r.after - last.get(key, 0.0)
		last[key] = r.after
		yield r


def _kind(r):
	"""Kirim — tovar keldi; sotuv — mijozga berildi (Delivery Note); kamomad — sotuvsiz kamaygan."""
	if r.voucher_type == "Delivery Note":
		return "sotuv"
	return "kirim" if r.delta > 0 else "kamomad"


def _stock_movement(shop, start, end, limit=200):
	"""Har bir tovar bo'yicha: davr boshidagi qoldiq + kirim − sotildi − kamomad = davr oxiridagi qoldiq.
	Variantlar andoza ostida jamlanadi."""
	warehouses = _shop_warehouses(shop)
	empty = {
		"totals": {k: 0 for k in ("opening", "received", "sold", "adjusted", "closing")},
		"counts": {"kirim": 0, "sotuv": 0, "kamomad": 0}, "products": [], "journal": [],
	}
	if not warehouses:
		return empty
	per = {}  # item_code -> hisoblagichlar
	vouchers = {"kirim": set(), "sotuv": set(), "kamomad": set()}
	for r in _deltas(warehouses, end=end):
		if not r.delta:
			continue
		c = per.setdefault(r.item_code, {"opening": 0.0, "received": 0.0, "sold": 0.0, "adjusted": 0.0})
		if getdate(r.posting_date) < start:
			c["opening"] += r.delta
			continue
		kind = _kind(r)
		vouchers[kind].add(r.voucher_no)
		if kind == "sotuv":
			c["sold"] -= r.delta  # qaytarilgan tovar sotuvni kamaytiradi
		elif kind == "kirim":
			c["received"] += r.delta
		else:
			c["adjusted"] -= r.delta

	info = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ["in", list(per) or [""]]}, fields=["name", "item_name", "variant_of", "image", "item_group"]
		)
	}
	parents = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters={"name": ["in", list({i.variant_of for i in info.values() if i.variant_of}) or [""]]},
			fields=["name", "item_name", "image", "item_group"],
		)
	}
	grouped = {}
	for code, c in per.items():
		item = info.get(code) or frappe._dict(name=code, item_name=code)
		base = parents.get(item.variant_of) or item
		g = grouped.setdefault(
			base.name,
			{"item_code": base.name, "item_name": base.item_name, "image": base.image or item.image, "item_group": group_title(base.item_group),
			 "opening": 0.0, "received": 0.0, "sold": 0.0, "adjusted": 0.0, "variants": 0},
		)
		for k in ("opening", "received", "sold", "adjusted"):
			g[k] += c[k]
		g["variants"] += 1 if item.variant_of else 0
	products = []
	for g in grouped.values():
		g["closing"] = g["opening"] + g["received"] - g["sold"] - g["adjusted"]
		if any(g[k] for k in ("opening", "received", "sold", "adjusted", "closing")):
			products.append(g)
	products.sort(key=lambda g: (-(g["adjusted"] > 0), -(g["received"] + g["sold"]), g["item_name"] or ""))
	totals = {k: sum(g[k] for g in products) for k in ("opening", "received", "sold", "adjusted", "closing")}
	return {
		"totals": totals,
		"counts": {k: len(v) for k, v in vouchers.items()},
		"products": products[:limit],
		"journal": journal(warehouses, start=start, end=end),
	}


def journal(warehouses, item_codes=None, start=None, end=None, limit=100, kinds=None, vouchers=None):
	"""Harakatlar tarixi, eng yangisi birinchi: har bir hujjat — nima bo'ldi (kirim / sotuv / kamomad),
	qachon, kim, nechta dona va har bir tovardan keyin omborda nechta qoldi.
	Kirimda yana: kimdan olindi (supplier — kontragent ismi, supplier_id — Kontragent), 1 donasi narxi (rate)
	va summasi (amount).
	kinds={"kirim"} — faqat kirimlar (Ombor sahifasi va tovar formasidagi "Kirim tarixi");
	vouchers — faqat shu hujjatlar (Kontragent formasidagi "Xaridlar")."""
	from marketplace.storefront import variant_labels

	groups = {}
	for r in _deltas(warehouses, item_codes, end=end):
		if not r.delta or (start and getdate(r.posting_date) < start):
			continue
		if vouchers is not None and r.voucher_no not in vouchers:
			continue
		kind = _kind(r)
		if kinds and kind not in kinds:
			continue
		g = groups.setdefault(
			(r.voucher_no, kind),
			frappe._dict(
				kind=kind, voucher_type=r.voucher_type, voucher_no=r.voucher_no, date=str(r.posting_date),
				time=str(r.posting_time or "")[:5], creation=r.creation, owner=r.owner, qty=0.0, amount=0.0, rows=[],
			),
		)
		# Narx faqat kirim hujjatida (Material Receipt) haqiqiy: Stock Reconciliation'da u baholash narxi
		rate = flt(r.incoming_rate) if kind == "kirim" and r.voucher_type == "Stock Entry" else 0.0
		g.qty += abs(r.delta)
		g.amount += rate * abs(r.delta)
		g.rows.append({"item_code": r.item_code, "qty": abs(r.delta), "after": r.after, "rate": rate})
	out = sorted(groups.values(), key=lambda g: g.creation, reverse=True)[:limit]
	if not out:
		return []

	codes = list({row["item_code"] for g in out for row in g.rows})
	items = {
		i.name: i
		for i in frappe.get_all("Item", filters={"name": ["in", codes]}, fields=["name", "item_name", "variant_of"])
	}
	labels = variant_labels([c for c in codes if (items.get(c) or {}).get("variant_of")])
	bases = dict(
		frappe.get_all(
			"Item", filters={"name": ["in", list({i.variant_of for i in items.values() if i.variant_of}) or [""]]},
			fields=["name", "item_name"], as_list=True,
		)
	)
	by_type = {}
	for g in out:
		by_type.setdefault(g.voucher_type, set()).add(g.voucher_no)
	entries = {
		e.name: e
		for e in frappe.get_all(
			"Stock Entry", filters={"name": ["in", list(by_type.get("Stock Entry", [])) or [""]]}, fields=["name", "remarks", "mp_kontragent"]
		)
	}
	kontragents = dict(
		frappe.get_all(
			"Kontragent", filters={"name": ["in", [e.mp_kontragent for e in entries.values() if e.mp_kontragent] or [""]]},
			fields=["name", "kontragent_name"], as_list=True,
		)
	)
	customers = dict(
		frappe.get_all("Delivery Note", filters={"name": ["in", list(by_type.get("Delivery Note", [])) or [""]]}, fields=["name", "customer_name"], as_list=True)
	)
	names = {u: frappe.utils.get_fullname(u) for u in {g.owner for g in out}}
	for g in out:
		for row in g.rows:
			i = items.get(row["item_code"]) or frappe._dict(item_name=row["item_code"])
			row["name"] = bases.get(i.variant_of) or i.item_name
			row["variant"] = labels.get(row["item_code"]) or ""
		g.rows.sort(key=lambda row: (row["name"], row["variant"]))
		g.user = names.get(g.owner) or g.owner
		entry = entries.get(g.voucher_no) or {}
		g.note = customers.get(g.voucher_no) if g.kind == "sotuv" else entry.get("remarks") or ""
		supplier = entry.get("mp_kontragent") or ""
		g.supplier = kontragents.get(supplier) or supplier
		g.supplier_id = supplier if supplier in kontragents else ""
		del g["creation"], g["owner"]
	return out


@frappe.whitelist()
def get_month_summary(month=None, shop=None):
	"""Do'konim bosh sahifasidagi "Shu oy" bloki. month — "2026-10" (berilmasa — shu oy).
	Kirim — sotuvdan tushgan pul (to'langan buyurtmalar, Hisobot'dagi "Kassaga tushgan pul" bilan bir xil).
	Chiqim — omborga tovar olishga ketgan pul: shu oydagi kirimlar, soni × 1 donasining olish narxi."""
	shop = _resolve_shop(shop)
	start = get_first_day(getdate(f"{month}-01") if month else today())
	end = getdate(add_months(start, 1)) - timedelta(days=1)
	income = _summary(shop, start, end)
	expense = _purchases(shop, start, end)
	return {
		"month": start.strftime("%Y-%m"),
		"income": income["revenue"],
		"orders": income["paid"],
		"expense": expense["amount"],
		"receipts": expense["receipts"],
		"received_qty": expense["qty"],
		"unpriced_qty": expense["unpriced"],
		"profit": income["revenue"] - expense["amount"],
	}


def _purchases(shop, start, end):
	"""Davrdagi kirim hujjatlari (Material Receipt): nechta hujjat, nechta dona, jami olish summasi.
	unpriced — narxsiz kirgan donalar (narx majburiy bo'lishidan oldingi eski kirimlar): chiqimga qo'shilmagan."""
	warehouses = _shop_warehouses(shop)
	if not warehouses:
		return {"receipts": 0, "qty": 0.0, "amount": 0.0, "unpriced": 0.0}
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	row = (
		frappe.qb.from_(sed)
		.join(se)
		.on(sed.parent == se.name)
		.select(
			Count(se.name).distinct().as_("receipts"),
			Sum(sed.transfer_qty).as_("qty"),
			Sum(sed.basic_amount).as_("amount"),
			Sum(Case().when(sed.basic_rate == 0, sed.transfer_qty).else_(0)).as_("unpriced"),
		)
		.where(se.docstatus == 1)
		.where(se.purpose == "Material Receipt")
		.where(se.posting_date[start:end])
		.where(sed.t_warehouse.isin(warehouses))
		.run(as_dict=True)[0]
	)
	return {"receipts": cint(row.receipts), "qty": flt(row.qty), "amount": flt(row.amount), "unpriced": flt(row.unpriced)}
