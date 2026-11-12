"""AI: qo'ng'iroq yozuvini matnga aylantirish (transkript) va qisqa tahlil — Google Gemini.

Munisa opaning telefoniyasidagi (target_zenit.telefoniya.stt) kabi:
* yozuv kelishi bilan o'zi navbatga tushadi (telefoniya.ingest_call -> enqueue), tugma bosish shart emas;
* o'tkazib yuborilganlar (internet, Gemini band) har 15 daqiqada qayta uriniladi (process_queue), har biriga 3 tagacha;
* bitta so'rov: audio + ko'rsatma -> JSON {"transkript", "xulosa"};
* asosiy model band (503) yoki topilmasa — zaxira modelga o'tadi; kvota tugasa (429) quvur 1 soat pauzaga tushadi;
* juda qisqa (javob berilmagan) va juda uzun qo'ng'iroqlar o'tkazib yuboriladi — pul tejash.
Sozlamalar: Telefoniya Sozlamalari -> "AI" bo'limi. Eski yozuv fayllari esa cleanup_old_recordings bilan o'chiriladi.
"""

import base64
import json
import os
import re

import frappe
import requests
from frappe import _
from frappe.utils import add_days, add_to_date, cint, format_datetime, now_datetime

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PAUSE_KEY = "mp_stt_pause"
MAX_ATTEMPTS = 3
MAX_INLINE = 14 * 1024 * 1024  # Gemini so'rovi 20 MB gacha; base64 hajmni 1/3 ga oshiradi
MIME = {
	".m4a": "audio/mp4", ".mp4": "audio/mp4", ".aac": "audio/aac", ".mp3": "audio/mp3", ".amr": "audio/amr",
	".wav": "audio/wav", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".3gp": "audio/3gpp",
}
LANGS = {"uz": "o'zbek (lotin yozuvida)", "ru": "rus", "en": "ingliz"}

PROMPT = """Bu — internet-do'kon sotuv menejeri bilan mijoz o'rtasidagi telefon suhbatining yozuvi (O'zbekiston).
Odatda menejer mijozga saytdagi buyurtma (to'lanmagan, yetkazish, qayta qo'ng'iroq) bo'yicha qo'ng'iroq qiladi.
Asosiy til: {lang}. Suhbat aralash (o'zbekcha-ruscha) bo'lishi mumkin.

1. "transkript" — suhbatni so'zma-so'z yoz. Har bir gap yangi qatordan, boshida "Menejer:" yoki "Mijoz:".
   O'zbekcha gaplar lotin yozuvida, ruscha gaplar ruscha — tarjima qilma. Eshitilmagan joy — "[eshitilmadi]".
   O'zingdan hech narsa qo'shma.
2. "xulosa" — 2–4 qisqa band, har biri "• " bilan: mijoz buyurtmani oladimi yoki yo'qmi; sababi yoki e'tirozi;
   kelishilgan narsa (sana, vaqt, manzil, to'lov usuli); menejerning keyingi qadami.
   Suhbat bo'lmagan bo'lsa (jimlik, avtojavob, ovozli pochta) — faqat shuni yoz.

Faqat JSON qaytar: {{"transkript": "...", "xulosa": "..."}}"""


class SttError(Exception):
	"""retry — boshqa model/keyinroq urinsa o'tishi mumkin (band, tarmoq); pause — kvota tugadi;
	mime — audio turi qabul qilinmadi (boshqa tur bilan qayta urinish mumkin)."""

	def __init__(self, message, retry=False, pause=False, mime=False):
		super().__init__(message)
		self.retry = retry
		self.pause = pause
		self.mime = mime


def settings():
	return frappe.get_cached_doc("Telefoniya Sozlamalari")


def api_key():
	from frappe.utils.password import get_decrypted_password

	return (
		get_decrypted_password("Telefoniya Sozlamalari", "Telefoniya Sozlamalari", "gemini_api_kalit", raise_exception=False)
		or frappe.conf.get("gemini_api_key")
	)


def blockers():
	"""Avto transkripsiya nega ishlamayapti — sabablar (bo'sh ro'yxat = ishlayapti)."""
	cfg = settings()
	out = []
	if not cfg.ai_yoqilgan:
		out.append(_("«AI yoqilgan» belgilanmagan"))
	if not api_key():
		out.append(_("Gemini API kalit kiritilmagan (aistudio.google.com dan olinadi)"))
	if not cfg.gemini_model:
		out.append(_("Gemini model yozilmagan"))
	until = frappe.cache.get_value(PAUSE_KEY)
	if until:
		out.append(_("Gemini kvotasi tugagan — {0} gacha pauza").format(until))
	return out


def _pending_filters():
	"""Transkripsiya kutayotganlar: yozuvi bor, matni yo'q, urinishlar tugamagan, davomiyligi chegaralar ichida."""
	cfg = settings()
	filters = [
		["yozuv", "is", "set"],
		["yozuv_ochirildi", "=", 0],
		["notanish", "=", 0],
		["transkript", "is", "not set"],
		["holat", "!=", "Transkripsiya"],
		["stt_urinish", "<", MAX_ATTEMPTS],
		["davomiyligi", ">=", max(cint(cfg.stt_min_sekund), 1)],
	]
	if cint(cfg.stt_maks_daqiqa):
		filters.append(["davomiyligi", "<=", cint(cfg.stt_maks_daqiqa) * 60])
	return filters


def enqueue(name):
	"""Yangi yozuv keldi (telefoniya.ingest_call): AI yoqilgan bo'lsa — fonda matnga aylantiriladi."""
	if blockers() or not frappe.db.get_value("Telefon Qongiroq", [["name", "=", name], *_pending_filters()], "name"):
		return
	frappe.enqueue("marketplace.sotuv.stt.transcribe", name=name, queue="long", timeout=600, enqueue_after_commit=True)


def process_queue(limit=20):
	"""Har 15 daqiqa: transkripti yo'q yozuvlar (o'tkazib yuborilgan yoki eski). Kvota tugasa — to'xtaydi."""
	if blockers():
		return 0
	# Ish jarayoni o'lib qolgan bo'lsa (timeout), "Transkripsiya"da osilib qolmasin: 30 daqiqadan keyin qaytadan
	for name in frappe.get_all(
		"Telefon Qongiroq",
		filters={"holat": "Transkripsiya", "transkripsiya_vaqti": ["<", add_to_date(now_datetime(), minutes=-30)]},
		pluck="name",
	):
		frappe.db.set_value("Telefon Qongiroq", name, "holat", "Yozuv bor", update_modified=False)
	done = 0
	for name in frappe.get_all("Telefon Qongiroq", filters=_pending_filters(), pluck="name", order_by="boshlandi desc", limit_page_length=cint(limit)):
		result = transcribe(name)
		frappe.db.commit()
		if result.get("pause"):
			break
		done += result.get("holat") == "tayyor"
	return done


def transcribe(name, force=False):
	"""Bitta qo'ng'iroq: audio -> Gemini -> transkript va qisqa tahlil hujjatga yoziladi.
	Qaytaradi: {"holat": "tayyor", "sozlar", "model"} yoki {"holat": "xato", "sabab", ["pause"]}."""
	doc = frappe.get_doc("Telefon Qongiroq", name)
	if not doc.yozuv or doc.yozuv_ochirildi:
		return {"holat": "xato", "sabab": _("Bu qo'ng'iroqda ovoz yozuvi yo'q")}
	if doc.transkript and not force:
		return {"holat": "tayyor", "sozlar": doc.transkript_sozlar, "model": doc.stt_model}
	key = api_key()
	if not key:
		return {"holat": "xato", "sabab": _("Gemini API kalit kiritilmagan")}

	try:
		file = frappe.get_doc("File", {"file_url": doc.yozuv})
		content = file.get_content()
	except (frappe.DoesNotExistError, OSError):
		return _failed(doc, SttError(_("Yozuv fayli topilmadi")))
	if isinstance(content, str):
		content = content.encode()
	if len(content) > MAX_INLINE:
		return _failed(doc, SttError(_("Fayl juda katta ({0} MB) — transkripsiya qilinmadi").format(round(len(content) / 1048576, 1))))

	doc.db_set({"holat": "Transkripsiya", "transkripsiya_vaqti": now_datetime()}, update_modified=False)
	frappe.db.commit()  # boshqa jarayon (15 daqiqalik navbat) shu yozuvni ikkinchi marta olmasin
	try:
		result, model = _ask(content, MIME.get(os.path.splitext(file.file_name or doc.yozuv)[1].lower(), "audio/mp4"))
	except SttError as e:
		return _failed(doc, e)

	transcript = (result.get("transkript") or "").strip()
	doc.db_set(
		{
			"transkript": transcript,
			"ai_xulosa": (result.get("xulosa") or "").strip(),
			"stt_model": model,
			"transkripsiya_vaqti": now_datetime(),
			"transkript_sozlar": len(transcript.split()),
			"holat": "Tahlil qilindi",
			"xato_matni": None,
		},
		update_modified=False,
	)
	return {"holat": "tayyor", "sozlar": len(transcript.split()), "model": model}


def _failed(doc, error):
	if error.pause:
		until = format_datetime(add_to_date(now_datetime(), hours=1), "HH:mm")
		frappe.cache.set_value(PAUSE_KEY, until, expires_in_sec=3600)
	doc.db_set(
		{
			"holat": "Xato" if not error.pause else "Yozuv bor",
			"xato_matni": str(error)[:500],
			# Kvota tugashi yozuvning aybi emas — urinish sanalmaydi
			"stt_urinish": cint(doc.stt_urinish) + (0 if error.pause else 1),
		},
		update_modified=False,
	)
	return {"holat": "xato", "sabab": str(error), "pause": error.pause}


def _ask(content, mime):
	"""Avval asosiy model, band/topilmasa — zaxira. m4a (audio/mp4) qabul qilinmasa — audio/aac deb qayta."""
	cfg = settings()
	models = [m for m in (cfg.gemini_model, cfg.zaxira_model) if m]
	last = None
	kinds = (mime, "audio/aac") if mime == "audio/mp4" else (mime,)
	for model in dict.fromkeys(models):
		for kind in kinds:
			try:
				return _call(model, content, kind, cfg), model
			except SttError as e:
				if e.mime:
					last = e
					continue  # shu model, boshqa audio turi
				if not e.retry:
					raise
				last = e
				break  # band yoki topilmadi — keyingi model
	raise last or SttError(_("Gemini model yozilmagan"))


def _call(model, content, mime, cfg):
	from marketplace.telegram_bot import http  # faqat IPv4: IPv6 yo'li yo'q tarmoqda qotib qolmasin

	body = {
		"contents": [{"parts": [
			{"text": PROMPT.format(lang=LANGS.get(cfg.stt_til or "uz", LANGS["uz"]))},
			{"inline_data": {"mime_type": mime, "data": base64.b64encode(content).decode()}},
		]}],
		"generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
	}
	try:
		r = http.post(API.format(model=model), headers={"x-goog-api-key": api_key()}, json=body, timeout=300)
	except requests.RequestException as e:
		raise SttError(_("Gemini'ga ulanib bo'lmadi: {0}").format(e.__class__.__name__), retry=True) from e
	if r.status_code != 200:
		try:
			message = r.json().get("error", {}).get("message") or r.text
		except ValueError:
			message = r.text
		message = (message or "")[:300]
		if r.status_code == 429:
			raise SttError(_("Gemini kvotasi tugadi (429): {0}").format(message), pause=True)
		if r.status_code in (500, 502, 503, 504):
			raise SttError(_("Gemini band ({0}) — keyinroq qayta uriniladi").format(r.status_code), retry=True)
		if r.status_code == 404:
			raise SttError(_("«{0}» modeli topilmadi — sozlamada model nomini tekshiring").format(model), retry=True)
		if r.status_code in (401, 403) or "API key" in message:
			raise SttError(_("Gemini API kalit noto'g'ri yoki ruxsati yo'q: {0}").format(message))
		raise SttError(_("Gemini xatosi ({0}): {1}").format(r.status_code, message), mime="mime" in message.lower())
	return _parse(r.json())


def _parse(data):
	parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
	text = "".join(p.get("text", "") for p in parts).strip()
	text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
	try:
		out = json.loads(text)
	except ValueError:
		# Model JSON qaytarmagan bo'lsa — butun matn transkript sifatida, tahlilsiz
		return {"transkript": text, "xulosa": ""}
	if not isinstance(out, dict) or not (out.get("transkript") or out.get("xulosa")):
		raise SttError(_("Gemini bo'sh javob qaytardi"), retry=True)
	return out


# ---------- Formalar va sozlamalar uchun ----------


def _only_managers():
	frappe.only_for(("System Manager", "Marketplace Manager"))


@frappe.whitelist()
def transcribe_now(qongiroq: str):
	"""Qo'ng'iroq formasidagi "Transkripsiya qilish": darhol (kutib turadi), bor transkript ustiga yoziladi."""
	doc = frappe.get_doc("Telefon Qongiroq", qongiroq)
	doc.check_permission("read")
	if not api_key():
		frappe.throw(_("Gemini API kalit kiritilmagan: Telefoniya Sozlamalari → AI"))
	frappe.db.set_value("Telefon Qongiroq", qongiroq, "stt_urinish", 0, update_modified=False)
	return transcribe(qongiroq, force=True)


@frappe.whitelist()
def status():
	"""Sozlamalardagi holat paneli: ishlayaptimi, ishlamasa nega va sonlar."""
	_only_managers()
	cfg = settings()
	count = lambda filters: frappe.db.count("Telefon Qongiroq", filters)
	return {
		"ishlayapti": not blockers(),
		"sabablar": blockers(),
		"jami_yozuv": count({"yozuv": ["is", "set"]}),
		"transkript_bor": count({"transkript": ["is", "set"]}),
		"navbatda": count(_pending_filters()),
		"xato": count({"holat": "Xato"}),
		"model": cfg.gemini_model,
		"zaxira": cfg.zaxira_model,
		"pauza": frappe.cache.get_value(PAUSE_KEY),
	}


def retry_failed():
	"""Xato bo'lgan (transkripti yo'q) yozuvlar urinishlari nolga qaytariladi — 15 daqiqalik navbat ularni qayta oladi.
	Masalan, kalit noto'g'ri bo'lganda 3 marta yiqilgan yozuv kalit tuzatilgach o'zi matnga aylanadi."""
	names = frappe.get_all("Telefon Qongiroq", filters={"transkript": ["is", "not set"], "holat": "Xato"}, pluck="name")
	for name in names:
		frappe.db.set_value("Telefon Qongiroq", name, {"stt_urinish": 0, "holat": "Yozuv bor"}, update_modified=False)
	return len(names)


@frappe.whitelist()
def transcribe_all():
	"""Sozlamalardagi "Eski yozuvlarni transkripsiya qilish": transkripti yo'q hammasi fonda (xatolilar ham qaytadan)."""
	_only_managers()
	if reasons := blockers():
		frappe.throw("<br>".join(reasons), title=_("AI ishlamayapti"))
	retry_failed()
	count = frappe.db.count("Telefon Qongiroq", _pending_filters())
	if count:
		frappe.enqueue("marketplace.sotuv.stt.process_queue", limit=count, queue="long", timeout=3 * 3600)
	return {"navbatga_qoyildi": count}


@frappe.whitelist()
def clear_pause():
	_only_managers()
	frappe.cache.delete_value(PAUSE_KEY)


# ---------- Eski yozuvlar ----------


def cleanup_old_recordings():
	"""Har kuni: saqlash muddati o'tgan yozuv fayllari o'chiriladi. Qo'ng'iroq, transkript va tahlil qoladi."""
	days = cint(settings().saqlash_kuni)
	if days <= 0:
		return 0
	old = frappe.get_all(
		"Telefon Qongiroq", filters={"yozuv": ["is", "set"], "boshlandi": ["<", add_days(now_datetime(), -days)]}, pluck="name"
	)
	for name in old:
		for f in frappe.get_all("File", filters={"attached_to_doctype": "Telefon Qongiroq", "attached_to_name": name}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True, force=True)
		frappe.db.set_value("Telefon Qongiroq", name, {"yozuv": None, "yozuv_bor": 0, "yozuv_ochirildi": 1}, update_modified=False)
		frappe.db.commit()
	return len(old)
