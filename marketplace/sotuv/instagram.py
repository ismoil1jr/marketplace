"""Instagram izohlarini yig'ish (post, reel, faol reklama) va saqlash. AI ham, javob yuborish ham bu yerda emas."""
import json
import re
import time
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import add_to_date, convert_utc_to_system_timezone, now_datetime, today

from marketplace.sotuv import ig_ai, instagram_dm
from marketplace.sotuv.meta import MetaError, _graph, _ig_status, _page_token
from marketplace.sotuv.murojaat import save_lead

LOOKBACK = 15 * 60
SINCE_OVERLAP = 120
RATE_CODES = {4, 17, 32, 613}
MAX_PER_HOUR = 10
POLL_BUDGET = 50

_COMMENT_FIELDS = "id,text,timestamp,username,from{id,username}"
_SECRET_RE = re.compile(r"(access_token|appsecret_proof|client_secret|fb_exchange_token)=[^&\s'\"]+")


def is_rate_limit(code) -> bool:
	"""Meta so'rovlar limiti: eski kodlar (4, 17, 32, 613) va Business Use Case kodlari 80000–80099
	(sahifa tokeni bilan: IG 80002, Pages 80001, Messenger 80006, Ads 80004 ...)."""
	try:
		code = int(code)
	except (TypeError, ValueError):
		return False
	return code in RATE_CODES or 80000 <= code < 80100


def _scrub(text):
	"""Error Log'ga yoziladigan matndan token/imzolarni o'chiradi (ehtiyot uchun)."""
	return _SECRET_RE.sub(r"\1=***", text or "")


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
	out, seen = [], {}

	def add(mid, link, text):
		text = (text or "").strip()
		if mid and mid not in seen:
			seen[mid] = {"id": mid, "havola": link or "", "post_matni": text}
			out.append(seen[mid])
		elif mid and text and not seen[mid]["post_matni"]:
			seen[mid]["post_matni"] = text

	for m in _graph("GET", f"{ig}/media", token, fields="id,permalink,caption", limit=25).get("data", []):
		add(m.get("id"), m.get("permalink"), m.get("caption"))

	act = _shop(shop, "meta_ad_account")
	if act:
		try:
			ads = _graph("GET", f"{act}/ads", token,
				effective_status=json.dumps(["ACTIVE"]),
				fields="creative{effective_instagram_media_id,instagram_permalink_url,body,title}", limit=50)
			for a in ads.get("data", []):
				cr = a.get("creative") or {}
				text = "\n".join(t.strip() for t in (cr.get("title"), cr.get("body")) if t and t.strip())
				add(cr.get("effective_instagram_media_id"), cr.get("instagram_permalink_url"), text)
		except MetaError as e:
			_ig_status(shop, _("Reklamalarni olib bo'lmadi (kod {0}); postlar tekshirilmoqda").format(e.code or "-"))
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
		"post_matni": media.get("post_matni") or "",
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
			if is_rate_limit(e.code):
				raise
			_ig_status(shop, _("Post izohlarini olib bo'lmadi (kod {0}); keyingisiga o'tildi").format(e.code or "-"))
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
		"post_matni": c.get("post_matni") or None,
		"vaqt": vaqt,
	})
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		return None
	return doc.name


def _enqueue(name):
	# commit'dan keyin: worker qatorni ko'rmasdan process'ni boshlamasin (DoesNotExistError)
	frappe.enqueue("marketplace.sotuv.instagram.process", queue="short", enqueue_after_commit=True,
		job_id=f"igx-{name}", deduplicate=True, name=name)


def _sweep(shop):
	"""Saqlangan, lekin navbatga qo'yilmay qolgan («Yangi») izohlarni qayta navbatga qo'yadi."""
	now = now_datetime()
	for name in frappe.get_all("Instagram Xabar", filters={
		"shop": shop, "holat": "Yangi",
		"creation": ["<", add_to_date(now, minutes=-2)], "vaqt": [">", add_to_date(now, minutes=-60)],
	}, pluck="name", limit=50):
		_enqueue(name)


def poll() -> None:
	"""Har daqiqada: yoqilgan do'konlarning yangi izohlarini yig'ib, AI qayta ishlashga qo'yadi."""
	if frappe.cache.get_value("mp_ig_ai_pause"):
		return
	lock = frappe.cache.make_key("mp_ig_poll_lock")
	if not frappe.cache.set(lock, 1, ex=300, nx=True):
		return
	try:
		_poll()
	finally:
		frappe.cache.delete(lock)


def _skip_dm(name):
	"""Ketma-ket xabarlarda faqat eng yangisiga javob beriladi; eskilari «Javobsiz» (sweep olmaydi)."""
	frappe.db.set_value("Instagram Xabar", name,
		{"holat": "Javobsiz", "xato": "Keyingi xabar bilan birga javob beriladi"})


def _poll():
	t0 = time.time()
	shops = frappe.get_all("Shop", filters={
		"meta_page_id": ["is", "set"], "ig_user_id": ["is", "set"], "ig_ai_rejim": ["!=", "O'chiq"],
	}, pluck="name")
	for shop in shops:
		if time.time() - t0 > POLL_BUDGET:
			break
		if frappe.cache.get_value(f"mp_ig_pause:{shop}"):
			continue
		start = int(t0)
		key = f"mp_ig_since:{shop}"
		old = int(frappe.cache.get_value(key) or 0)
		since = max(old, start - LOOKBACK)
		try:
			for c in fetch_comments(shop, since):
				name = store(shop, c)
				if name:
					_enqueue(name)
			try:
				newest = {}
				for m in instagram_dm.fetch_messages(shop, since):
					name = store(shop, m, turi="DM")
					if not name:
						continue
					cust = m.get("from_id")
					prev = newest.get(cust)
					if prev is None:
						newest[cust] = (m.get("timestamp") or 0, name)
					elif (m.get("timestamp") or 0) >= prev[0]:
						_skip_dm(prev[1])
						newest[cust] = (m.get("timestamp") or 0, name)
					else:
						_skip_dm(name)
				for _ts, name in newest.values():
					_enqueue(name)
			except MetaError as e:
				if is_rate_limit(e.code):
					raise
				_ig_status(shop, _("Direct xabarlarini olib bo'lmadi (kod {0})").format(e.code or "-"))
			_sweep(shop)
			frappe.cache.set_value(key, max(old, start), expires_in_sec=24 * 3600)
		except MetaError as e:
			# Traceback emas, faqat matn: MetaError'ning matnida token yo'q (meta._graph `from None`)
			if is_rate_limit(e.code):
				frappe.cache.set_value(f"mp_ig_pause:{shop}", 1, expires_in_sec=15 * 60)
				_ig_status(shop, _("Instagram so'rovlar limiti (kod {0}); 15 daqiqa kutiladi").format(e.code))
			elif _ig_status(shop, _("Izohlarni olib bo'lmadi (kod {0})").format(e.code or "-")):
				frappe.log_error(title=f"Instagram: {shop}", message=_scrub(f"{e} (kod {e.code or '-'})"))
		except Exception as e:
			if _ig_status(shop, _("Izohlarni olishda xatolik ({0}); keyingi daqiqada qayta uriniladi").format(type(e).__name__)):
				frappe.log_error(title=f"Instagram: {shop}", message=_scrub(frappe.get_traceback()))
		frappe.db.commit()


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
	if doc.turi == "DM":
		return instagram_dm.send_dm(shop, doc)
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
	kw = {"post_matni": doc.post_matni or None}
	if doc.turi == "DM":
		if not draft_only and instagram_dm.is_human_paused(doc.shop, doc.mijoz_id):
			doc.db_set({"holat": "Qoralama", "xato": "Operator suhbatda"})
			return "Qoralama"
		kw["tarix"] = instagram_dm.history(doc)
	try:
		info = ig_ai.answer(doc.shop, doc.matn, doc.turi, **kw)
	except (ig_ai.IgAiError, MetaError) as e:
		return _fail(doc, e)
	if not info.get("javob_kerak") and not draft_only:
		_lead(doc, info)
		doc.db_set({"holat": "Javobsiz", "ai_javob": "", "til": info.get("til"), "xato": ""})
		return "Javobsiz"
	vals = {"ai_javob": info.get("javob") or "", "til": info.get("til"), "xato": ""}
	if not draft_only and not vals["ai_javob"].strip():
		_lead(doc, info)
		doc.db_set({**vals, "holat": "Xato", "xato": "AI bo'sh javob qaytardi"})
		return "Xato"
	if draft_only or rejim == "Sinov":
		_lead(doc, info)
		doc.db_set({**vals, "holat": "Qoralama"})
		return "Qoralama"
	if _hourly_count(doc) >= MAX_PER_HOUR:
		_lead(doc, info)
		doc.db_set({**vals, "holat": "Qoralama", "xato": "Mijoz uchun soatlik limit"})
		return "Qoralama"
	doc.ai_javob = vals["ai_javob"]
	try:
		reply_id = _deliver(doc.shop, doc)
	except (MetaError, frappe.ValidationError) as e:
		_lead(doc, info)
		doc.db_set({**vals, "holat": "Xato", "xato": str(e)[:500]})
		return "Xato"
	# Post chiqdi: yozuvni darhol saqlaymiz, keyingi xato uni qaytarib yubormasin (qayta post bo'lmasin)
	doc.db_set({**vals, "holat": "Yuborildi", "javob_id": reply_id})
	frappe.db.commit()
	_lead(doc, info)
	return "Yuborildi"


def process(name: str) -> str:
	doc = frappe.get_doc("Instagram Xabar", name)
	if doc.holat != "Yangi":
		return doc.holat
	rejim = _shop(doc.shop, "ig_ai_rejim")
	if rejim not in ("Sinov", "Yoqilgan"):
		return doc.holat
	# Qatorni qulflaymiz: ikkinchi worker kutadi va yangi holatni ko'radi
	if frappe.db.get_value("Instagram Xabar", name, "holat", for_update=True) != "Yangi":
		return frappe.db.get_value("Instagram Xabar", name, "holat")
	doc.reload()
	return _run(doc, rejim)


def _writable(name):
	doc = frappe.get_doc("Instagram Xabar", name)
	if not frappe.has_permission("Instagram Xabar", "write", doc):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	return doc


@frappe.whitelist(methods=["POST"])
def send(name: str):
	# Avval qulf: holatni qulflangan o'qishdan olamiz (ikkinchi bosuvchi birinchisi tugaguncha kutadi)
	row = frappe.db.get_value("Instagram Xabar", name, ["holat", "ai_javob"], as_dict=True, for_update=True)
	if not row:
		frappe.throw(_("Xabar topilmadi"), frappe.DoesNotExistError)
	if row.holat not in ("Qoralama", "Xato") or not (row.ai_javob or "").strip():
		frappe.throw(_("Faqat tayyor javobli qoralamani yuborish mumkin"))
	doc = _writable(name)
	try:
		reply_id = _deliver(doc.shop, doc)
	except MetaError as e:
		doc.db_set({"holat": "Xato", "xato": str(e)[:500]})
		frappe.db.commit()  # throw so'rovni qaytaradi; xato holati saqlansin
		frappe.throw(_("Yuborib bo'lmadi: {0}").format(e))
	doc.db_set({"holat": "Yuborildi", "javob_id": reply_id, "xato": ""})
	frappe.db.commit()
	return "Yuborildi"


@frappe.whitelist(methods=["POST"])
def regenerate(name: str):
	doc = _writable(name)
	if doc.holat == "Yuborildi":
		frappe.throw(_("Yuborilgan javobni qayta yozib bo'lmaydi"))
	return _run(doc, "Sinov", draft_only=True)
