# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

"""Do'konlar bo'yicha savdo: tanlangan davrda har bir do'konning buyurtmalari, tushumi va qarzdorligi."""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.only_for(("System Manager", "Marketplace Manager"))
	from_date = getdate(filters.from_date or get_first_day(today()))
	to_date = getdate(filters.to_date or today())

	so = frappe.qb.DocType("Sales Order")
	from frappe.query_builder.functions import Count, Sum
	from pypika import Case

	paid = Case().when(so.payment_status == "To'langan", so.grand_total).else_(0)
	waiting = Case().when(so.payment_status == "Kutilmoqda", so.grand_total).else_(0)
	cancelled = Case().when((so.docstatus == 2) | (so.payment_status == "Bekor"), 1).else_(0)
	delivered = Case().when(so.per_delivered >= 100, 1).else_(0)
	query = (
		frappe.qb.from_(so)
		.select(
			so.shop,
			Count(so.name).as_("orders"),
			Sum(paid).as_("paid_amount"),
			Sum(waiting).as_("waiting_amount"),
			Sum(cancelled).as_("cancelled"),
			Sum(delivered).as_("delivered"),
		)
		.where((so.shop.isnotnull()) & (so.docstatus.isin([1, 2])))
		.where(so.transaction_date.between(from_date, to_date))
		.groupby(so.shop)
	)
	if filters.shop:
		query = query.where(so.shop == filters.shop)
	rows = {r.shop: r for r in query.run(as_dict=True)}

	shops = frappe.get_all(
		"Shop", filters={"name": filters.shop} if filters.shop else {}, fields=["name", "shop_name", "layout_style", "status"]
	)
	items = {
		r.shop: r.cnt
		for r in frappe.get_all(
			"Item",
			filters={"shop": ["is", "set"], "disabled": 0, "variant_of": ["is", "not set"]},
			fields=["shop", {"COUNT": "*", "as": "cnt"}],
			group_by="shop",
		)
	}

	data = []
	for s in shops:
		r = rows.get(s.name) or frappe._dict()
		active = flt(r.orders) - flt(r.cancelled)
		data.append(
			{
				"shop": s.name,
				"shop_name": s.shop_name,
				"layout": {"vitrina": "A Vitrina", "story": "B Instagram", "katalog": "C Katalog"}.get(s.layout_style, s.layout_style),
				"status": s.status,
				"items": items.get(s.name, 0),
				"orders": flt(r.orders),
				"delivered": flt(r.delivered),
				"cancelled": flt(r.cancelled),
				"paid_amount": flt(r.paid_amount),
				"waiting_amount": flt(r.waiting_amount),
				"avg_check": flt(r.paid_amount) / active if active else 0,
			}
		)
	data.sort(key=lambda d: d["paid_amount"], reverse=True)

	columns = [
		{"fieldname": "shop", "label": _("Do'kon"), "fieldtype": "Link", "options": "Shop", "width": 160},
		{"fieldname": "shop_name", "label": _("Nomi"), "fieldtype": "Data", "width": 160},
		{"fieldname": "layout", "label": _("Shablon"), "fieldtype": "Data", "width": 110},
		{"fieldname": "status", "label": _("Holati"), "fieldtype": "Data", "width": 90},
		{"fieldname": "items", "label": _("Tovarlar"), "fieldtype": "Int", "width": 90},
		{"fieldname": "orders", "label": _("Buyurtmalar"), "fieldtype": "Int", "width": 110},
		{"fieldname": "delivered", "label": _("Topshirilgan"), "fieldtype": "Int", "width": 110},
		{"fieldname": "cancelled", "label": _("Bekor"), "fieldtype": "Int", "width": 80},
		{"fieldname": "paid_amount", "label": _("Tushum (to'langan)"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "waiting_amount", "label": _("To'lov kutilmoqda"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "avg_check", "label": _("O'rtacha chek"), "fieldtype": "Currency", "width": 140},
	]
	chart = {
		"data": {
			"labels": [d["shop_name"] for d in data],
			"datasets": [{"name": _("Tushum"), "values": [d["paid_amount"] for d in data]}],
		},
		"type": "bar",
		"colors": ["#1F5C4A"],
		# Ustun ustiga kelganda 40480000 emas, 40,480,000 so‘m
		"fieldtype": "Currency",
	}
	total_paid = sum(d["paid_amount"] for d in data)
	summary = [
		{"label": _("Do'konlar"), "value": len(data), "indicator": "blue"},
		{"label": _("Buyurtmalar"), "value": int(sum(d["orders"] for d in data)), "indicator": "blue"},
		{"label": _("Tushum"), "value": total_paid, "datatype": "Currency", "indicator": "green"},
		{"label": _("To'lov kutilmoqda"), "value": sum(d["waiting_amount"] for d in data), "datatype": "Currency", "indicator": "orange"},
	]
	return columns, data, None, chart, summary
