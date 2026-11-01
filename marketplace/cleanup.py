"""Bir martalik tozalash (faqat sinov bazasi uchun): `before` sanasidan oldin yaratilgan barcha tovarlar
va ular bilan bog'liq hamma narsa o'chiriladi — buyurtmalar, yetkazishlar, kirimlar, qoldiq yozuvlari, narxlar.

	# avval nima o'chishini ko'rish (hech narsa o'chmaydi):
	bench --site marketplace.local execute marketplace.cleanup.run
	# o'chirish:
	bench --site marketplace.local execute marketplace.cleanup.run --kwargs "{'apply': 1}"

Ishlatib bo'lgach, bu faylni o'chirib yuborsa bo'ladi.
"""

import frappe

STOCK_VOUCHERS = ("Stock Reconciliation", "Stock Entry", "Delivery Note", "Purchase Receipt")


def run(before="2026-10-21", apply=0):
	old = frappe.get_all("Item", filters={"creation": ["<", before]}, pluck="name")
	if not old:
		print("O'chiriladigan tovar yo'q")
		return

	# Eski tovari bor buyurtmalar butunlay o'chadi (yarim buyurtma qoldirib bo'lmaydi)
	orders = _parents("Sales Order Item", old)
	delivery_notes = _parents("Delivery Note Item", old) | _linked("Delivery Note Item", "against_sales_order", orders)
	vouchers = {dt: _parents(_child_of(dt), old) for dt in STOCK_VOUCHERS if dt != "Delivery Note"}
	vouchers["Delivery Note"] = delivery_notes

	print(f"Tovarlar ({before} dan oldin): {len(old)}")
	print(f"Buyurtmalar: {len(orders)}")
	for dt, names in vouchers.items():
		if names:
			print(f"{dt}: {len(names)}")
	kept = frappe.get_all("Item", filters={"creation": [">=", before], "variant_of": ["is", "not set"]}, pluck="item_name")
	print("Qoladigan tovarlar:", ", ".join(kept) or "—")

	if not frappe.utils.cint(apply):
		print("\nHech narsa o'chirilmadi. O'chirish uchun: --kwargs \"{'apply': 1}\"")
		return

	_delete_docs("Sales Order", orders)
	if orders:
		_delete_docs("Payment Transaction", set(frappe.get_all("Payment Transaction", {"sales_order": ["in", list(orders)]}, pluck="name")))
	for dt, names in vouchers.items():
		# Ichida yangi tovar ham bor hujjatdan faqat eski qatorlar olinadi
		mixed = {n for n in names if frappe.db.exists(_child_of(dt), {"parent": n, "item_code": ["not in", old]})}
		_delete_docs(dt, names - mixed)
		if mixed:
			frappe.db.delete(_child_of(dt), {"parent": ["in", list(mixed)], "item_code": ["in", old]})
	for dt in ("Stock Ledger Entry", "Bin", "Item Price"):
		frappe.db.delete(dt, {"item_code": ["in", old]})
	_delete_docs("Item", set(old))
	frappe.db.commit()
	frappe.clear_cache()
	print(f"\nO'chirildi: {len(old)} ta tovar, {len(orders)} ta buyurtma")


def _child_of(doctype):
	return {"Stock Reconciliation": "Stock Reconciliation Item", "Stock Entry": "Stock Entry Detail"}.get(
		doctype, f"{doctype} Item"
	)


def _parents(child, items):
	return set(frappe.get_all(child, filters={"item_code": ["in", items]}, pluck="parent", distinct=True))


def _linked(child, field, names):
	if not names:
		return set()
	return set(frappe.get_all(child, filters={field: ["in", list(names)]}, pluck="parent", distinct=True))


def _delete_docs(doctype, names):
	"""Hujjat, uning barcha jadval qatorlari va unga bog'liq yozuvlar (izoh, tarix, bildirishnoma, buxgalteriya)."""
	names = list(names)
	if not names:
		return
	for df in frappe.get_meta(doctype).get_table_fields():
		frappe.db.delete(df.options, {"parent": ["in", names], "parenttype": doctype})
	for dt, field in (
		("Stock Ledger Entry", "voucher_no"),
		("GL Entry", "voucher_no"),
		("Payment Ledger Entry", "voucher_no"),
		("Repost Item Valuation", "voucher_no"),
	):
		frappe.db.delete(dt, {"voucher_type": doctype, field: ["in", names]})
	frappe.db.delete("Comment", {"reference_doctype": doctype, "reference_name": ["in", names]})
	frappe.db.delete("Version", {"ref_doctype": doctype, "docname": ["in", names]})
	frappe.db.delete("Notification Log", {"document_type": doctype, "document_name": ["in", names]})
	frappe.db.delete("File", {"attached_to_doctype": doctype, "attached_to_name": ["in", names]})
	frappe.db.delete(doctype, {"name": ["in", names]})
