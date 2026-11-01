"""Mijoz uchun to'lov cheki (PDF): "Buyurtmalarim" va buyurtma sahifasidan yuklab olinadi.

Faqat to'langan buyurtma uchun. Chekda sotuvchi (MChJ nomi, STIR, manzil), har bir tovar MXIK kodi bilan,
jami va to'lov ma'lumoti (Payme/Click tranzaksiya raqami). PDF'ni Frappe bilan birga o'rnatilgan WeasyPrint yasaydi.
Bu fiskal chek emas: soliq cheki Payme/Click tomonidan alohida beriladi.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime

from marketplace import orders
from marketplace.storefront import fmt_sum

PAID = "To'langan"


def receipt_pdf(name, customer):
	"""(fayl nomi, PDF baytlari). Boshqa mijozning buyurtmasi topilmaydi (get_order_for_customer)."""
	from weasyprint import HTML

	so = orders.get_order_for_customer(name, customer)
	if so.payment_status != PAID:
		frappe.throw(_("Chek to‘lov qilingandan keyin chiqadi"))
	html = frappe.render_template("marketplace/templates/storefront/receipt_pdf.html", _context(so))
	return f"chek-{so.name}.pdf", HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()


def _context(so):
	shop = frappe.db.get_value(
		"Shop",
		so.shop,
		["shop_name", "legal_name", "stir", "phone", "city", "pickup_address", "logo"],
		as_dict=True,
	)
	codes = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ["in", [i.item_code for i in so["items"]]]}, fields=["name", "mxik_code", "package_code"]
		)
	}
	for i in so["items"]:
		i.mxik = (codes.get(i.item_code) or {}).get("mxik_code") or ""
	txn = frappe.get_all(
		"Payment Transaction",
		filters={"sales_order": so.name, "state": 2},
		fields=["provider", "provider_txn_id", "modified"],
		order_by="modified desc",
		limit=1,
	)
	txn = txn[0] if txn else None
	return {
		"so": so,
		"shop": shop,
		"txn": txn,
		"paid_at": get_datetime(txn.modified).strftime("%d.%m.%Y %H:%M") if txn else None,
		"fmt_sum": fmt_sum,
	}
