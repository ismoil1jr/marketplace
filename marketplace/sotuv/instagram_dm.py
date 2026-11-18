"""Instagram Direct: yangi mijoz xabarlarini yig'ish, o'sha mijozga javob yuborish, operator yozsa AI'ni to'xtatish."""
import json
import re
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from marketplace.sotuv.meta import _graph, _ig_status, _page_token

HUMAN_PAUSE = 24 * 3600
_FIELDS = "id,updated_time,messages.limit(10){id,message,created_time,from{id,username}}"


def _human_key(shop, mijoz_id):
	return f"mp_ig_human:{shop}:{mijoz_id}"


def is_human_paused(shop: str, mijoz_id: str) -> bool:
	return bool(frappe.cache.get_value(_human_key(shop, mijoz_id)))


def _norm(t):
	return re.sub(r"\s+", " ", t or "").strip()


def _is_ours(shop, customer_id, m):
	"""Do'kon nomidan yozilgan xabar bizning (AI) javobimizmi? id yoki oxirgi 24 soatdagi matn bo'yicha."""
	if frappe.db.exists("Instagram Xabar", {"shop": shop, "javob_id": m["id"]}) or \
			frappe.db.exists("Instagram Xabar", {"shop": shop, "direct_id": m["id"]}):
		return True
	text = _norm(m.get("text"))
	if not text:
		return False
	rows = frappe.get_all("Instagram Xabar", filters={
		"shop": shop, "turi": "DM", "mijoz_id": customer_id, "holat": "Yuborildi",
		"modified": (">", add_to_date(now_datetime(), hours=-24)),
	}, pluck="ai_javob", limit=50)
	# «+» izohiga Direct'ga yuborilgan javob (private reply) ham bizniki
	rows += frappe.get_all("Instagram Xabar", filters={
		"shop": shop, "turi": "Izoh", "direct_id": ["is", "set"],
		"modified": (">", add_to_date(now_datetime(), hours=-24)),
	}, pluck="direct_javob", limit=100)
	return any(_norm(r) == text for r in rows)


def fetch_messages(shop: str, since_ts: int) -> list[dict]:
	from marketplace.sotuv.instagram import _shop, _utc

	page = _shop(shop, "meta_page_id")
	ig = _shop(shop, "ig_user_id")
	if not ig:
		_ig_status(shop, _("Instagram akkaunt ID yo'q — Direct tekshirilmadi"))
		return []
	token = _page_token(shop)
	data = _graph("GET", f"{page}/conversations", token, platform="instagram", fields=_FIELDS, limit=25).get("data", [])
	out = []
	now = time.time()
	for conv in data:
		if conv.get("updated_time") and int(_utc(conv["updated_time"]).timestamp()) < since_ts:
			continue
		msgs = []
		for m in (conv.get("messages") or {}).get("data", []):
			if not m.get("id") or not m.get("created_time"):
				continue
			frm = m.get("from") or {}
			msgs.append({
				"id": m["id"], "text": m.get("message") or "", "username": frm.get("username") or "",
				"from_id": frm.get("id") or "", "timestamp": int(_utc(m["created_time"]).timestamp()),
			})
		customer = next((m["from_id"] for m in msgs if m["from_id"] and m["from_id"] != ig), None)
		if not customer:
			continue
		operator_ts = None  # oxirgi 24 soatdagi eng yangi operator (bizniki bo'lmagan) xabari
		for m in msgs:
			if m["from_id"] == ig:
				# since'dan eski bo'lsa ham: kesh tozalansa (deploy) pauza Meta'dagi vaqtdan qayta tiklanadi
				if now - m["timestamp"] < HUMAN_PAUSE and (operator_ts is None or m["timestamp"] > operator_ts) \
						and not _is_ours(shop, customer, m):
					operator_ts = m["timestamp"]
				continue
			if m["timestamp"] <= since_ts:
				continue
			if m["from_id"] == customer and m["text"].strip():
				out.append({
					"id": m["id"], "parent_id": None, "text": m["text"], "username": m["username"],
					"from_id": customer, "timestamp": m["timestamp"], "media_id": None, "havola": None,
					"suhbat_id": conv.get("id"),
				})
		if operator_ts is not None:
			# TTL = 24 soat − xabar yoshi: har tekshiruvda qayta yozilsa ham muddat surilmaydi
			ttl = int(min(HUMAN_PAUSE, HUMAN_PAUSE - (now - operator_ts)))
			if ttl > 0:
				frappe.cache.set_value(_human_key(shop, customer), 1, expires_in_sec=ttl)
	return out


def history(doc) -> list[dict]:
	filters = {
		"shop": doc.shop, "turi": "DM", "mijoz_id": doc.mijoz_id, "name": ["!=", doc.name],
	}
	if doc.vaqt:
		filters["vaqt"] = ["<=", doc.vaqt]
	rows = frappe.get_all("Instagram Xabar", filters=filters,
		fields=["matn", "ai_javob", "holat"], order_by="vaqt desc, creation desc", limit=10)
	out = []
	# Suhbat «+» izohi va unga Direct'ga yuborilgan javobdan boshlangan bo'lishi mumkin — AI uni ham ko'rsin
	if doc.username:
		for r in reversed(frappe.get_all("Instagram Xabar", filters={
			"shop": doc.shop, "turi": "Izoh", "username": doc.username, "direct_id": ["is", "set"],
			"creation": (">", add_to_date(now_datetime(), days=-7)),
		}, fields=["matn", "direct_javob"], order_by="creation desc", limit=2)):
			out.append({"kim": "Mijoz", "matn": f"(izoh) {r.matn}"})
			out.append({"kim": "Do'kon", "matn": r.direct_javob})
	for r in reversed(rows):
		out.append({"kim": "Mijoz", "matn": r.matn})
		if r.holat == "Yuborildi" and r.ai_javob:
			out.append({"kim": "Do'kon", "matn": r.ai_javob})
	return out


def send_dm(shop: str, doc) -> str:
	from marketplace.sotuv.instagram import _shop

	res = _graph("POST", f"{_shop(shop, 'meta_page_id')}/messages", _page_token(shop),
		recipient=json.dumps({"id": doc.mijoz_id}), message=json.dumps({"text": doc.ai_javob}))
	return res.get("message_id")
