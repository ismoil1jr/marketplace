"""Sotuvchi uchun oylik hisobot (Desk → Hisobot): tushum, buyurtmalar, eng ko'p sotilganlar."""

import calendar
from datetime import date

import frappe
from frappe.query_builder import Case, DatePart
from frappe.query_builder.functions import Coalesce, Count, Extract, IfNull, Sum
from frappe.utils import cint, flt, getdate, today

from marketplace.permissions import get_user_shop

PAID = "To'langan"
CANCELLED = "Bekor"
ADMIN_ROLES = {"System Manager", "Marketplace Manager"}


@frappe.whitelist()
def get_sales_report(year=None, month=None, shop=None):
	"""month=0 yoki bo'sh -> butun yil. Sotuvchi faqat o'z do'konini ko'radi."""
	shop = _resolve_shop(shop)
	now = getdate(today())
	year = cint(year) or now.year
	month = now.month if month is None or month == "" else cint(month)
	if not 0 <= month <= 12:
		frappe.throw("Noto'g'ri oy")

	start, end = _period(year, month)
	# Taqqoslash: oy -> oldingi oy, butun yil -> oldingi yil
	if month:
		prev_start, prev_end = _period(year - 1, 12) if month == 1 else _period(year, month - 1)
	else:
		prev_start, prev_end = _period(year - 1, 0)

	summary = _summary(shop, start, end)
	prev = _summary(shop, prev_start, prev_end)
	summary["change"] = {
		"revenue": _pct(summary["revenue"], prev["revenue"]),
		"orders": _pct(summary["orders"], prev["orders"]),
		"paid": _pct(summary["paid"], prev["paid"]),
	}

	return {
		"shop": shop,
		"year": year,
		"month": month,
		"is_admin": _is_admin(),
		"shops": _shop_options() if _is_admin() else [],
		"years": _years(shop, now.year),
		"summary": summary,
		"previous": prev,
		"monthly": _monthly(shop, year),
		"top_products": _top_products(shop, start, end),
		"categories": _categories(shop, start, end),
		"payment_methods": _payment_methods(shop, start, end),
	}


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


def _period(year, month):
	if month:
		return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
	return date(year, 1, 1), date(year, 12, 31)


def _pct(cur, prev):
	if not prev:
		return None
	return round((flt(cur) - flt(prev)) * 100 / flt(prev), 1)


def _so_query(shop, start, end):
	so = frappe.qb.DocType("Sales Order")
	q = frappe.qb.from_(so).where(so.transaction_date[start:end]).where(so.docstatus > 0)
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
		Count("*").as_("orders"),
		Sum(Case().when(paid, 1).else_(0)).as_("paid"),
		Sum(Case().when(pending, 1).else_(0)).as_("pending"),
		Sum(Case().when(_is_cancelled(so), 1).else_(0)).as_("cancelled"),
		Sum(Case().when(_active(so) & (so.per_delivered >= 100), 1).else_(0)).as_("delivered"),
		Sum(Case().when(paid, so.grand_total).else_(0)).as_("revenue"),
		Sum(Case().when(pending, so.grand_total).else_(0)).as_("pending_amount"),
	).run(as_dict=True)[0]
	return {k: (flt(v) if k.endswith(("revenue", "amount")) else cint(v)) for k, v in row.items()}


def _monthly(shop, year):
	so, q = _so_query(shop, *_period(year, 0))
	m = Extract(DatePart.month, so.transaction_date)
	paid = _active(so) & (so.payment_status == PAID)
	rows = (
		q.select(
			m.as_("month"),
			Count("*").as_("orders"),
			Sum(Case().when(paid, 1).else_(0)).as_("paid"),
			Sum(Case().when(paid, so.grand_total).else_(0)).as_("revenue"),
		)
		.groupby(m)
		.run(as_dict=True)
	)
	by_month = {cint(r.month): r for r in rows}
	return [
		{
			"month": i,
			"orders": cint(by_month.get(i, {}).get("orders")),
			"paid": cint(by_month.get(i, {}).get("paid")),
			"revenue": flt(by_month.get(i, {}).get("revenue")),
		}
		for i in range(1, 13)
	]


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
			Sum(soi.qty).as_("qty"),
			Sum(soi.amount).as_("amount"),
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
				"item_group": i.item_group,
				"qty": flt(r.qty),
				"amount": flt(r.amount),
				"orders": cint(r.orders),
				"variants": cint(r.variants) if i.has_variants else 0,
			}
		)
	return {
		"by_qty": sorted(out, key=lambda x: (-x["qty"], -x["amount"]))[:limit],
		"by_amount": sorted(out, key=lambda x: (-x["amount"], -x["qty"]))[:limit],
	}


def _categories(shop, start, end):
	so, soi, q = _lines_query(shop, start, end)
	group = IfNull(soi.item_group, "")
	rows = (
		q.select(group.as_("item_group"), Sum(soi.qty).as_("qty"), Sum(soi.amount).as_("amount"))
		.groupby(group)
		.run(as_dict=True)
	)
	return sorted(
		({"item_group": r.item_group or "Boshqa", "qty": flt(r.qty), "amount": flt(r.amount)} for r in rows),
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


def _years(shop, current):
	so = frappe.qb.DocType("Sales Order")
	q = frappe.qb.from_(so).select(Extract(DatePart.year, so.transaction_date).as_("y")).where(so.docstatus > 0)
	if shop:
		q = q.where(so.shop == shop)
	first = q.orderby(so.transaction_date).limit(1).run()
	first = cint(first[0][0]) if first else current
	return list(range(current, min(first, current) - 1, -1))


def _shop_options():
	return frappe.get_all("Shop", fields=["name", "shop_name"], order_by="shop_name asc")
