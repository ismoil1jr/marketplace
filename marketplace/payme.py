"""Payme Merchant API (JSON-RPC): https://developer.help.paycom.uz/protokol-merchant-api/

Har bir do'konning o'z manzili (Shop formasida ko'rsatiladi):
    https://<domen>/api/method/marketplace.payme.callback?dokon=<Shop>
Payme kabinetida shu do'kon (MChJ) kassasiga o'z manzili va hisob maydoni `order_id` yoziladi.
Kalit `Authorization: Basic base64("Paycom:<kalit>")` da keladi va o'sha do'konning Shop formasidagi
(shifrlangan) kalitiga mos kelishi shart. ?dokon'siz eski manzilda do'kon kalitning o'zidan topiladi.

Har doim HTTP 200 va {"result": ...} yoki {"error": {...}} qaytadi — Payme shuni kutadi.
"""

import base64
import hmac
import json
import time

import frappe
from frappe.utils import cint, flt
from werkzeug.wrappers import Response

from marketplace.payments import mark_paid, mark_refunded, to_tiyin, url_shop

TIMEOUT_MS = 43_200_000  # 12 soat: shu vaqtda to'lanmagan tranzaksiya bekor bo'ladi

STATE_CREATED, STATE_DONE, STATE_CANCELLED, STATE_CANCELLED_AFTER = 1, 2, -1, -2

ERRORS = {
	-32504: ("Недостаточно привилегий", "Ruxsat yo‘q", "Insufficient privileges"),
	-32700: ("Ошибка парсинга JSON", "JSON xato", "Parse error"),
	-32300: ("Ошибка запроса", "So‘rov xato", "Request error"),
	-32601: ("Метод не найден", "Metod topilmadi", "Method not found"),
	-31001: ("Неверная сумма", "Summa noto‘g‘ri", "Incorrect amount"),
	-31003: ("Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"),
	-31007: ("Заказ выполнен, отмена невозможна", "Buyurtma topshirilgan, bekor qilib bo‘lmaydi", "Order delivered, cannot cancel"),
	-31008: ("Невозможно выполнить операцию", "Amalni bajarib bo‘lmaydi", "Unable to perform operation"),
	-31050: ("Заказ не найден", "Buyurtma topilmadi", "Order not found"),
	-31051: ("Заказ уже оплачен или отменён", "Buyurtma to‘langan yoki bekor qilingan", "Order already paid or cancelled"),
	-31052: ("Заказ ожидает оплаты в другой транзакции", "Buyurtma boshqa tranzaksiyada to‘lanmoqda", "Order is pending in another transaction"),
}


class PaymeError(Exception):
	def __init__(self, code, data=None):
		self.code, self.data = code, data


@frappe.whitelist(allow_guest=True, methods=["POST"])
def callback(**kwargs):
	try:
		body = json.loads(frappe.request.get_data(as_text=True) or "{}")
	except ValueError:
		return _reply({"error": _error(-32700)}, None)
	rpc_id = body.get("id")
	try:
		shop = _authenticate()
		handler = METHODS.get(body.get("method"))
		if not handler:
			raise PaymeError(-32601, body.get("method"))
		result = handler(shop, body.get("params") or {}, body)
		frappe.db.commit()
		return _reply({"result": result}, rpc_id)
	except PaymeError as e:
		frappe.db.rollback()
		return _reply({"error": _error(e.code, e.data)}, rpc_id)
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Payme callback xatosi", body)
		return _reply({"error": _error(-32300)}, rpc_id)


def _authenticate():
	"""Basic Paycom:<kalit> -> do'kon. Kalit hech bir do'konnikiga mos kelmasa -32504."""
	header = getattr(frappe.local, "payme_authorization", "") or ""
	try:
		scheme, token = header.split(" ", 1)
		login, key = base64.b64decode(token).decode().split(":", 1)
	except Exception:
		raise PaymeError(-32504)
	if scheme.lower() != "basic" or login != "Paycom" or not key:
		raise PaymeError(-32504)

	filters = {"payme_merchant_id": ["is", "set"]}
	# Do'konning o'z manzili (?dokon=): faqat shu do'kon kaliti bilan kiriladi
	if shop_name := url_shop():
		filters["name"] = shop_name
	for name in frappe.get_all("Shop", filters=filters, pluck="name"):
		shop = frappe.get_doc("Shop", name)
		field = "payme_test_key" if cint(shop.payme_test_mode) else "payme_key"
		expected = shop.get_password(field, raise_exception=False)
		if expected and hmac.compare_digest(expected, key):
			return shop
	raise PaymeError(-32504)


# ---------- Metodlar ----------


def check_perform_transaction(shop, params, body):
	so = _order(shop, params)
	return {"allow": True, "detail": _receipt(so)}


def create_transaction(shop, params, body):
	tx = _tx(shop, params.get("id"), lock=True, must_exist=False)
	if tx:
		if tx.state != STATE_CREATED:
			raise PaymeError(-31008)
		if _expired(tx):
			_cancel(tx, STATE_CANCELLED, 4)
			raise PaymeError(-31008)
		return {"create_time": cint(tx.create_time), "transaction": str(tx.name), "state": tx.state}

	so = _order(shop, params)
	if frappe.db.exists("Payment Transaction", {"sales_order": so.name, "provider": "Payme", "state": STATE_CREATED}):
		raise PaymeError(-31052, "order_id")

	tx = frappe.get_doc(
		{
			"doctype": "Payment Transaction",
			"shop": shop.name,
			"sales_order": so.name,
			"provider": "Payme",
			"provider_txn_id": params.get("id"),
			"amount": flt(params.get("amount")) / 100,
			"state": STATE_CREATED,
			"create_time": str(cint(params.get("time")) or _now()),
			"raw_payload": json.dumps(body, ensure_ascii=False),
		}
	).insert(ignore_permissions=True)
	return {"create_time": cint(tx.create_time), "transaction": str(tx.name), "state": tx.state}


def perform_transaction(shop, params, body):
	tx = _tx(shop, params.get("id"), lock=True)
	if tx.state == STATE_CREATED:
		if _expired(tx):
			_cancel(tx, STATE_CANCELLED, 4)
			raise PaymeError(-31008)
		tx.db_set({"state": STATE_DONE, "perform_time": str(_now())})
		mark_paid(tx.sales_order, "Payme", f"(Payme {tx.provider_txn_id})")
	elif tx.state != STATE_DONE:
		raise PaymeError(-31008)
	return {"transaction": str(tx.name), "perform_time": cint(tx.perform_time), "state": tx.state}


def cancel_transaction(shop, params, body):
	tx = _tx(shop, params.get("id"), lock=True)
	reason = cint(params.get("reason"))
	if tx.state == STATE_CREATED:
		_cancel(tx, STATE_CANCELLED, reason)
	elif tx.state == STATE_DONE:
		if flt(frappe.db.get_value("Sales Order", tx.sales_order, "per_delivered")):
			raise PaymeError(-31007)
		_cancel(tx, STATE_CANCELLED_AFTER, reason)
		mark_refunded(tx.sales_order, "Payme", f"(Payme {tx.provider_txn_id})")
	return {"transaction": str(tx.name), "cancel_time": cint(tx.cancel_time), "state": tx.state}


def check_transaction(shop, params, body):
	tx = _tx(shop, params.get("id"))
	return _tx_info(tx)


def get_statement(shop, params, body):
	rows = frappe.get_all(
		"Payment Transaction",
		filters={"shop": shop.name, "provider": "Payme"},
		fields=["name"],
		order_by="creation asc",
	)
	start, end = cint(params.get("from")), cint(params.get("to"))
	out = []
	for r in rows:
		tx = frappe.get_doc("Payment Transaction", r.name)
		if start <= cint(tx.create_time) <= end:
			out.append(
				{
					"id": tx.provider_txn_id,
					"time": cint(tx.create_time),
					"amount": to_tiyin(tx.amount),
					"account": {"order_id": tx.sales_order},
					**_tx_info(tx),
				}
			)
	return {"transactions": out}


METHODS = {
	"CheckPerformTransaction": check_perform_transaction,
	"CreateTransaction": create_transaction,
	"PerformTransaction": perform_transaction,
	"CancelTransaction": cancel_transaction,
	"CheckTransaction": check_transaction,
	"GetStatement": get_statement,
}


# ---------- Yordamchilar ----------


def _order(shop, params):
	"""Buyurtmani topadi va to'lash mumkinligini tekshiradi (summa tiyinda)."""
	order_id = ((params.get("account") or {}).get("order_id") or "").strip()
	so = frappe.db.get_value(
		"Sales Order",
		{"name": order_id, "shop": shop.name},
		["name", "grand_total", "docstatus", "payment_status"],
		as_dict=True,
	)
	if not so or so.docstatus != 1:
		raise PaymeError(-31050, "order_id")
	if so.payment_status != "Kutilmoqda":
		raise PaymeError(-31051, "order_id")
	if cint(params.get("amount")) != to_tiyin(so.grand_total):
		raise PaymeError(-31001, "amount")
	return so


def _receipt(so):
	"""Fiskal chek uchun tovarlar (Payme chekni MChJ STIR'i bilan soliqqa o'zi yuboradi)."""
	items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": so.name},
		fields=["item_code", "item_name", "qty", "rate"],
		order_by="idx",
	)
	codes = {
		i.name: i
		for i in frappe.get_all(
			"Item", filters={"name": ["in", [i.item_code for i in items]]}, fields=["name", "mxik_code", "package_code"]
		)
	}
	return {
		"receipt_type": 0,
		"items": [
			{
				"title": i.item_name[:128],
				"price": to_tiyin(i.rate),
				"count": cint(i.qty),
				"code": codes.get(i.item_code, {}).get("mxik_code") or "",
				"package_code": codes.get(i.item_code, {}).get("package_code") or "",
				"vat_percent": 0,
			}
			for i in items
		],
	}


def _tx(shop, txn_id, lock=False, must_exist=True):
	name = frappe.db.get_value(
		"Payment Transaction", {"provider": "Payme", "provider_txn_id": txn_id or "", "shop": shop.name}, "name",
		for_update=lock,
	)
	if not name:
		if must_exist:
			raise PaymeError(-31003)
		return None
	return frappe.get_doc("Payment Transaction", name)


def _cancel(tx, state, reason):
	tx.db_set({"state": state, "reason": reason, "cancel_time": str(_now())})


def _expired(tx):
	return _now() - cint(tx.create_time) > TIMEOUT_MS


def _tx_info(tx):
	return {
		"create_time": cint(tx.create_time),
		"perform_time": cint(tx.perform_time),
		"cancel_time": cint(tx.cancel_time),
		"transaction": str(tx.name),
		"state": tx.state,
		"reason": tx.reason if tx.state < 0 else None,
	}


def _now():
	return int(time.time() * 1000)


def _error(code, data=None):
	ru, uz, en = ERRORS.get(code, ERRORS[-32300])
	err = {"code": code, "message": {"ru": ru, "uz": uz, "en": en}}
	if data:
		err["data"] = data
	return err


def _reply(payload, rpc_id):
	payload["id"] = rpc_id
	return Response(json.dumps(payload, ensure_ascii=False), status=200, mimetype="application/json")
