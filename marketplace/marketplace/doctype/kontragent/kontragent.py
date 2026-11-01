# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count, Max, Min, Sum
from frappe.utils import cint, flt

from marketplace.permissions import get_user_shop


class Kontragent(Document):
	"""Do'kon tovar oladigan doimiy sotuvchi: "Ibrohim — O'rikzor bozori, ko'ylak".
	Ombor kirimida "Kimdan olindi" shu ro'yxatdan tanlanadi (Item.mp_kirim_kontragent -> Stock Entry.mp_kontragent),
	formasida esa undan nima, qachon, nechta va necha puldan olingani (get_purchases)."""

	def validate(self):
		if self.is_new() or not self.shop:
			self.shop = get_user_shop() or self.shop
		if not self.shop:
			frappe.throw(_("Do'konni tanlang"))
		self.kontragent_name = " ".join((self.kontragent_name or "").split())
		for field in ("telefon", "joyi", "nima_sotadi"):
			self.set(field, (self.get(field) or "").strip() or None)
		other = frappe.db.get_value(
			"Kontragent", {"shop": self.shop, "kontragent_name": self.kontragent_name, "name": ["!=", self.name]}, "name"
		)
		if other:
			frappe.throw(
				_("«{0}» kontragenti ro'yxatda bor. Ismi bir xil boshqa odam bo'lsa, bozorini qo'shib yozing (masalan: Ibrohim O'rikzor)").format(
					self.kontragent_name
				)
			)


@frappe.whitelist()
def get_purchases(kontragent: str):
	"""Formadagi "Xaridlar": jami (nechta kirim, nechta dona, summa, birinchi va oxirgi xarid)
	va har bir kirim — qaysi kuni, qaysi tovarlar (rang · o'lcham), nechta, necha puldan."""
	from marketplace.reports import journal

	doc = frappe.get_doc("Kontragent", kontragent)
	doc.check_permission("read")
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	total = (
		frappe.qb.from_(sed)
		.join(se)
		.on(sed.parent == se.name)
		.select(
			Count(se.name).distinct().as_("receipts"),
			Sum(sed.transfer_qty).as_("qty"),
			Sum(sed.basic_amount).as_("amount"),
			Min(se.posting_date).as_("first"),
			Max(se.posting_date).as_("last"),
		)
		.where(se.docstatus == 1)
		.where(se.mp_kontragent == doc.name)
		.run(as_dict=True)[0]
	)
	vouchers = set(frappe.get_all("Stock Entry", filters={"docstatus": 1, "mp_kontragent": doc.name}, pluck="name"))
	warehouse = frappe.db.get_value("Shop", doc.shop, "warehouse")
	receipts = journal([warehouse], vouchers=vouchers, limit=500) if vouchers and warehouse else []
	# Izohdan faqat do'konchi yozgani qoladi: "Tovar formasidan kirim: ..." — tizim qo'shgan qism
	auto = _("Tovar formasidan kirim")
	for g in receipts:
		g.note = (g.note or "").removeprefix(auto).lstrip(": ").strip()
	return {
		"receipts": cint(total.receipts),
		"qty": flt(total.qty),
		"amount": flt(total.amount),
		"first": str(total.first or ""),
		"last": str(total.last or ""),
		"journal": receipts,
	}
