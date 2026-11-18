"""Instagram izohlarini yig'ish (post, reel, faol reklama) va saqlash. AI ham, javob yuborish ham bu yerda emas."""
import json
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import add_to_date, convert_utc_to_system_timezone, now_datetime, today

from marketplace.sotuv import ig_ai
from marketplace.sotuv.meta import MetaError, _graph, _page_token, _status
from marketplace.sotuv.murojaat import save_lead

LOOKBACK = 15 * 60
RATE_CODES = {4, 17, 32, 613}
MAX_PER_HOUR = 10

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


def media_list(shop: str, token: str | None = None) -> list[dict]:
	token = token or _page_token(shop)
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
	for media in media_list(shop, token):
		try:
			data = _graph("GET", f"{media['id']}/comments", token, fields=fields, limit=50).get("data", [])
		except MetaError as e:
			if e.code in RATE_CODES:
				raise
			_status(shop, _("Post izohlarini olib bo'lmadi (kod {0}); keyingisiga o'tildi").format(e.code or "-"))
			continue
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


def _post(shop, doc):
	"""Izoh ostiga (yoki javob ostiga) shop nomidan javob yozadi; javob id'sini qaytaradi."""
	text = doc.ai_javob
	if doc.ota_id:
		text = f"@{doc.username} {text}"
	res = _graph("POST", f"{doc.ota_id or doc.tashqi_id}/replies", _page_token(shop), message=text)
	return res.get("id")


def _deliver(shop, doc):
	if doc.turi == "Izoh":
		return _post(shop, doc)
	frappe.throw(_("Bu turdagi xabarni yuborib bo'lmaydi"))


def _hourly_count(doc):
	return frappe.db.count("Instagram Xabar", {
		"shop": doc.shop, "mijoz_id": doc.mijoz_id, "holat": "Yuborildi",
		"modified": (">", add_to_date(now_datetime(), hours=-1)),
	})


def _lead(doc, info):
	"""Telefon bor bo'lsa murojaat yaratadi (yoki mavjudiga ulaydi); yomon raqamda lidsiz davom etadi."""
	if not info.get("telefon") or doc.murojaat:
		return
	izoh = ("Direct: " if doc.turi == "DM" else "Izoh: ") + (doc.matn or "")
	try:
		name, _dup = save_lead(doc.shop, {
			"telefon": info["telefon"], "ism": info.get("ism") or doc.username or "",
			"manba": "Instagram", "izoh": izoh, "lead_id": f"ig:{doc.mijoz_id}:{today()}",
		}, info.get("tovar_kodi"))
	except frappe.ValidationError:
		frappe.clear_messages()
		return
	doc.db_set("murojaat", name)


def _fail(doc, e):
	if isinstance(e, ig_ai.IgAiError) and e.pause:
		frappe.cache.set_value("mp_ig_ai_pause", 1, expires_in_sec=3600)
	doc.db_set({"holat": "Xato", "xato": str(e)[:500]})
	return "Xato"


def _run(doc, rejim, draft_only=False):
	kw = {}
	if doc.turi == "DM":
		from marketplace.sotuv import instagram_dm

		kw["tarix"] = instagram_dm.history(doc)
	try:
		info = ig_ai.answer(doc.shop, doc.matn, doc.turi, **kw)
	except (ig_ai.IgAiError, MetaError) as e:
		return _fail(doc, e)
	_lead(doc, info)
	if not info.get("javob_kerak") and not draft_only:
		doc.db_set({"holat": "Javobsiz", "ai_javob": "", "til": info.get("til"), "xato": ""})
		return "Javobsiz"
	vals = {"ai_javob": info.get("javob") or "", "til": info.get("til"), "xato": ""}
	if draft_only or rejim == "Sinov":
		doc.db_set({**vals, "holat": "Qoralama"})
		return "Qoralama"
	if _hourly_count(doc) >= MAX_PER_HOUR:
		doc.db_set({**vals, "holat": "Qoralama", "xato": "Mijoz uchun soatlik limit"})
		return "Qoralama"
	doc.ai_javob = vals["ai_javob"]
	try:
		reply_id = _deliver(doc.shop, doc)
	except (MetaError, frappe.ValidationError) as e:
		doc.db_set({**vals, "holat": "Xato", "xato": str(e)[:500]})
		return "Xato"
	doc.db_set({**vals, "holat": "Yuborildi", "javob_id": reply_id})
	return "Yuborildi"


def process(name: str) -> str:
	doc = frappe.get_doc("Instagram Xabar", name)
	if doc.holat != "Yangi":
		return doc.holat
	rejim = _shop(doc.shop, "ig_ai_rejim")
	if rejim not in ("Sinov", "Yoqilgan"):
		return doc.holat
	return _run(doc, rejim)


def _writable(name):
	doc = frappe.get_doc("Instagram Xabar", name)
	if not frappe.has_permission("Instagram Xabar", "write", doc):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["POST"])
def send(name: str):
	doc = _writable(name)
	if doc.holat not in ("Qoralama", "Xato") or not (doc.ai_javob or "").strip():
		frappe.throw(_("Faqat tayyor javobli qoralamani yuborish mumkin"))
	try:
		reply_id = _deliver(doc.shop, doc)
	except MetaError as e:
		doc.db_set({"holat": "Xato", "xato": str(e)[:500]})
		frappe.throw(_("Yuborib bo'lmadi: {0}").format(e))
	doc.db_set({"holat": "Yuborildi", "javob_id": reply_id, "xato": ""})
	return "Yuborildi"


@frappe.whitelist(methods=["POST"])
def regenerate(name: str):
	doc = _writable(name)
	if doc.holat == "Yuborildi":
		frappe.throw(_("Yuborilgan javobni qayta yozib bo'lmaydi"))
	return _run(doc, "Sinov", draft_only=True)
