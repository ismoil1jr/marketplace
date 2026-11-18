"""Instagram izohlarini yig'ish (post, reel, faol reklama) va saqlash. AI ham, javob yuborish ham bu yerda emas."""
import json
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import convert_utc_to_system_timezone

from marketplace.sotuv.meta import MetaError, _graph, _page_token, _status

LOOKBACK = 15 * 60
RATE_CODES = {4, 17, 32, 613}

_COMMENT_FIELDS = "id,text,timestamp,username,from{id,username}"


def _shop(shop, field):
	return (frappe.db.get_value("Shop", shop, field) or "").strip()


def _utc(ts):
	"""Graph vaqti ("2026-11-17T04:19:10+0000") -> timezone-aware UTC datetime."""
	try:
		dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z")
	except (ValueError, TypeError):
		dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=timezone.utc)
	return dt.astimezone(timezone.utc)


def media_list(shop: str) -> list[dict]:
	token = _page_token(shop)
	ig = _shop(shop, "ig_user_id")
	out, seen = [], set()

	def add(mid, link):
		if mid and mid not in seen:
			seen.add(mid)
			out.append({"id": mid, "havola": link or ""})

	for m in _graph("GET", f"{ig}/media", token, fields="id,permalink", limit=25).get("data", []):
		add(m.get("id"), m.get("permalink"))

	act = _shop(shop, "meta_ad_account")
	if act:
		try:
			ads = _graph("GET", f"{act}/ads", token,
				effective_status=json.dumps(["ACTIVE"]),
				fields="creative{effective_instagram_media_id,instagram_permalink_url}", limit=50)
			for a in ads.get("data", []):
				cr = a.get("creative") or {}
				add(cr.get("effective_instagram_media_id"), cr.get("instagram_permalink_url"))
		except MetaError as e:
			_status(shop, _("Reklamalarni olib bo'lmadi (kod {0}); postlar tekshirilmoqda").format(e.code or "-"))
	return out


def _flat(c, parent_id, media):
	frm = c.get("from") or {}
	return {
		"id": c.get("id"),
		"parent_id": parent_id,
		"text": c.get("text") or "",
		"username": c.get("username") or frm.get("username") or "",
		"from_id": frm.get("id") or "",
		"timestamp": int(_utc(c["timestamp"]).timestamp()),
		"media_id": media["id"],
		"havola": media["havola"],
	}


def fetch_comments(shop: str, since_ts: int) -> list[dict]:
	token = _page_token(shop)
	ig = _shop(shop, "ig_user_id")
	uname = _shop(shop, "ig_username")
	fields = f"{_COMMENT_FIELDS},replies{{{_COMMENT_FIELDS}}}"
	out = []
	for media in media_list(shop):
		data = _graph("GET", f"{media['id']}/comments", token, fields=fields, limit=50).get("data", [])
		for c in data:
			items = [_flat(c, None, media)]
			items += [_flat(r, c.get("id"), media) for r in (c.get("replies") or {}).get("data", [])]
			for x in items:
				if x["timestamp"] < since_ts:
					continue
				if (ig and x["from_id"] == ig) or (uname and x["username"] == uname):
					continue
				out.append(x)
	return out


def store(shop: str, c: dict, turi: str = "Izoh") -> str | None:
	if frappe.db.exists("Instagram Xabar", {"tashqi_id": c["id"]}):
		return None
	vaqt = None
	if c.get("timestamp"):
		utc = datetime.fromtimestamp(int(c["timestamp"]), tz=timezone.utc)
		vaqt = convert_utc_to_system_timezone(utc).replace(tzinfo=None)
	doc = frappe.get_doc({
		"doctype": "Instagram Xabar",
		"shop": shop,
		"turi": turi,
		"holat": "Yangi",
		"tashqi_id": c["id"],
		"ota_id": c.get("parent_id"),
		"media_id": c.get("media_id"),
		"media_havola": c.get("havola"),
		"mijoz_id": c.get("from_id"),
		"username": c.get("username"),
		"matn": c.get("text"),
		"vaqt": vaqt,
	})
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		return None
	return doc.name
