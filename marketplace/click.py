"""Click SHOP API (Prepare / Complete): https://docs.click.uz/click-api-request/

Manzillar hamma do'konlar uchun bitta, Click kabinetida har bir MChJ xizmatiga shular yoziladi:
    Prepare:  https://<domen>/api/method/marketplace.click.prepare
    Complete: https://<domen>/api/method/marketplace.click.complete
Do'kon `service_id` bo'yicha topiladi, so'rov imzosi (sign_string, MD5) o'sha do'konning
shifrlangan secret key'i bilan tekshiriladi. Javob har doim JSON, `error` 0 — muvaffaqiyat.
"""

import hashlib
import hmac
import json

import frappe
from frappe.utils import cint, flt
from werkzeug.wrappers import Response

from marketplace.payments import mark_paid

ACTION_PREPARE, ACTION_COMPLETE = 0, 1
STATE_CREATED, STATE_DONE, STATE_CANCELLED = 1, 2, -1

ERRORS = {
	0: "Success",
	-1: "SIGN CHECK FAILED!",
	-2: "Incorrect parameter amount",
	-3: "Action not found",
	-4: "Already paid",
	-5: "Order does not exist",
	-6: "Transaction does not exist",
	-8: "Error in request from click",
	-9: "Transaction cancelled",
}


class ClickError(Exception):
	def __init__(self, code):
		self.code = code


@frappe.whitelist(allow_guest=True, methods=["POST"])
def prepare(**kwargs):
	return _handle(ACTION_PREPARE)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def complete(**kwargs):
	return _handle(ACTION_COMPLETE)


def _handle(expected_action):
	p = frappe._dict(frappe.local.form_dict)
	p.pop("cmd", None)
	out = {"click_trans_id": p.click_trans_id, "merchant_trans_id": p.merchant_trans_id}
	try:
		if cint(p.action) != expected_action:
			raise ClickError(-3)
		shop = _shop(p)
		_check_sign(shop, p)
		if expected_action == ACTION_PREPARE:
			out["merchant_prepare_id"] = _prepare(shop, p)
		else:
			out["merchant_confirm_id"] = _complete(shop, p)
		frappe.db.commit()
		out.update(error=0, error_note=ERRORS[0])
	except ClickError as e:
		frappe.db.rollback()
		out.update(error=e.code, error_note=ERRORS.get(e.code, "Error"))
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Click callback xatosi", json.dumps(p, default=str))
		out.update(error=-8, error_note=ERRORS[-8])
	return Response(json.dumps(out), status=200, mimetype="application/json")


def _shop(p):
	name = frappe.db.get_value("Shop", {"click_service_id": str(p.service_id or "")}, "name")
	if not name or not p.click_trans_id or not p.merchant_trans_id:
		raise ClickError(-8)
	return frappe.get_doc("Shop", name)


def _check_sign(shop, p):
	secret = shop.get_password("click_secret_key", raise_exception=False) or ""
	parts = [p.click_trans_id, p.service_id, secret, p.merchant_trans_id]
	if cint(p.action) == ACTION_COMPLETE:
		parts.append(p.merchant_prepare_id)
	parts += [p.amount, p.action, p.sign_time]
	expected = hashlib.md5("".join(str(x or "") for x in parts).encode()).hexdigest()
	if not secret or not hmac.compare_digest(expected, str(p.sign_string or "")):
		raise ClickError(-1)


def _order(shop, p):
	so = frappe.db.get_value(
		"Sales Order",
		{"name": p.merchant_trans_id, "shop": shop.name},
		["name", "grand_total", "docstatus", "payment_status"],
		as_dict=True,
	)
	if not so or so.docstatus != 1:
		raise ClickError(-5)
	if so.payment_status == "To'langan":
		raise ClickError(-4)
	if so.payment_status == "Bekor":
		raise ClickError(-9)
	if abs(flt(p.amount) - flt(so.grand_total)) > 0.01:
		raise ClickError(-2)
	return so


def _prepare(shop, p):
	so = _order(shop, p)
	existing = frappe.db.get_value(
		"Payment Transaction", {"provider": "Click", "provider_txn_id": str(p.click_trans_id)}, ["name", "state"], as_dict=True
	)
	if existing:
		if existing.state == STATE_CANCELLED:
			raise ClickError(-9)
		return cint(existing.name)
	if cint(p.error) < 0:
		raise ClickError(-9)
	tx = frappe.get_doc(
		{
			"doctype": "Payment Transaction",
			"shop": shop.name,
			"sales_order": so.name,
			"provider": "Click",
			"provider_txn_id": str(p.click_trans_id),
			"amount": flt(p.amount),
			"state": STATE_CREATED,
			"create_time": str(p.sign_time or ""),
			"raw_payload": json.dumps(p, default=str),
		}
	).insert(ignore_permissions=True)
	return cint(tx.name)


def _complete(shop, p):
	name = frappe.db.get_value(
		"Payment Transaction",
		{"name": cint(p.merchant_prepare_id), "provider": "Click", "shop": shop.name, "provider_txn_id": str(p.click_trans_id)},
		"name",
		for_update=True,
	)
	if not name:
		raise ClickError(-6)
	tx = frappe.get_doc("Payment Transaction", name)
	if tx.state == STATE_DONE:
		raise ClickError(-4)
	if tx.state == STATE_CANCELLED:
		raise ClickError(-9)
	if cint(p.error) < 0:
		# Click to'lovni amalga oshira olmadi (kartada pul yo'q va h.k.)
		tx.db_set({"state": STATE_CANCELLED, "cancel_time": str(p.sign_time or ""), "reason": cint(p.error)})
		frappe.db.commit()
		raise ClickError(-9)
	_order(shop, p)
	tx.db_set({"state": STATE_DONE, "perform_time": str(p.sign_time or "")})
	mark_paid(tx.sales_order, "Click", f"(Click {p.click_trans_id})")
	return cint(tx.name)
