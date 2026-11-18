"""Instagram AI: katalog, prompt, Gemini chaqiruvi va javobni tahlil qilish.

Sof AI qatlami — Instagram/Graph API'ga umuman murojaat qilmaydi. Do'kon nomidan izoh va Direct xabarlariga javob
matni tayyorlaydi. Gemini bilan ishlash stt.py'dagi kabi (xato xaritasi, zaxira model, auto_models).
Tovar qoldig'i miqdori modelga HECH QACHON berilmaydi — faqat "bor" / "tugagan".
"""

import json
import re

import frappe
import requests
from frappe import _
from frappe.utils import get_url

from marketplace.sotuv import stt
from marketplace.sotuv.telefoniya import normalize_phone

CATALOG_LIMIT = 60
HISTORY_LIMIT = 10
KEYS = ("javob_kerak", "javob", "til", "telefon", "ism", "tovar_kodi")

PROMPT = """Sen «{shop}» internet-do'konining Instagram'dagi yordamchisisan: do'kon nomidan mijozlarning {turi_nomi}iga javob yozasan (O'zbekiston).

QOIDALAR:
1. Javob doim salomlashuv bilan boshlansin: o'zbekcha bo'lsa «Assalomu alaykum!», ruscha bo'lsa «Здравствуйте!».
2. Mijoz qaysi tilda va qaysi yozuvda (lotin, kirill, rus) yozgan bo'lsa — shu tilda va shu yozuvda javob ber.
3. Javob qisqa: {uzunlik}.
4. Tovarning qoldiq sonini hech qachon aytma — aniq sonini aytma. Faqat «holat» bo'yicha: "bor" bo'lsa «Ha, albatta bor», \
"tugagan" bo'lsa «Hozircha tugagan, menejerimiz aniqlab beradi».
5. Narx, chegirma, muddat yoki boshqa ma'lumotni o'zingdan to'qima. Faqat quyidagi ro'yxat va «AI uchun ma'lumot»dagini ayt. \
Narx ro'yxatda yo'q (narx null) bo'lsa: «Menejerimiz Direct'da aniqlab beradi».
6. Tovar so'ralsa, mos tovarning "havola"sini ber va "tovar_kodi"ga uning "kod"ini yoz. Mos tovar topilmasa — null.
7. «Post matni» (bo'lsa) — mijoz izoh qoldirgan post yoki reklamaning matni: savol odatda shu postdagi tovar haqida. \
Mijoz qaysi tovarni so'rayotgani aniq bo'lmasa yoki u tovar ro'yxatda bo'lmasa — tovarni ham, narxni ham taxmin qilma: \
{noaniq}.
8. Mijoz telefon raqamini yozgan bo'lsa "telefon"ga, ismini aytgan bo'lsa "ism"ga yoz, aks holda null.
9. "javob_kerak" ni false qil (javob bo'sh qolsin), agar: spam yoki reklama, faqat emoji yoki belgi, oddiy «rahmat» / «ok», \
haqorat yoki so'kinish, raqobatchi do'kon reklamasi bo'lsa. Aks holda true.

Natija FAQAT bitta JSON obyekt, boshqa hech narsa yozma (izoh, markdown, tushuntirish yo'q). Kalitlar:
{{"javob_kerak": true|false, "javob": "matn", "til": "uz|ru|en", "telefon": null|"raqam", "ism": null|"ism", "tovar_kodi": null|"kod"}}

Ma'lumotlar (JSON):
{data}
{post}{tarix}
Mijozning yangi {turi_nomi}i:
{matn}"""


class IgAiError(Exception):
	"""pause — kvota tugadi (429); retry — boshqa model/keyinroq urinsa o'tishi mumkin."""

	def __init__(self, message, pause=False, retry=False, missing=False):
		super().__init__(message)
		self.pause = pause
		self.retry = retry
		self.missing = missing  # 404: model nomi eskirgan


def _fold(text):
	"""Solishtirish uchun: kichik harf, apostrof turlari (‘ ’ ʻ ʼ `) bitta, bo'shliqlar bitta."""
	text = re.sub(r"[\u2018\u2019\u02bb\u02bc`\u00b4]", "'", (text or "").lower())
	return re.sub(r"\s+", " ", text).strip()


def catalog(shop, hint=None):
	"""Do'konning saytdagi tovarlari (60 tagacha): kod, nom, narx, holat (bor/tugagan), havola. Miqdor berilmaydi.
	hint (post/reklama matni): nomi hint ichida uchragan tovarlar — 60 tadan keyin bo'lsa ham — ro'yxat boshida."""
	filters = {"shop": shop, "is_published": 1, "disabled": 0, "variant_of": ["is", "not set"]}
	fields = ["name", "item_name", "is_stock_item", "has_variants", "mp_tez_kunda"]
	hint = _fold(hint)
	if hint:
		rows = frappe.get_all("Item", filters=filters, fields=fields, order_by="modified desc")
		hit = [r for r in rows if len(_fold(r.item_name)) >= 3 and _fold(r.item_name) in hint]
		hit.sort(key=lambda r: -len(_fold(r.item_name)))  # eng aniq (uzun) nom birinchi
		taken = {r.name for r in hit}
		rows = hit + [r for r in rows if r.name not in taken]
	else:
		rows = frappe.get_all("Item", filters=filters, fields=fields, order_by="modified desc",
			limit_page_length=CATALOG_LIMIT)
	rows = rows[:CATALOG_LIMIT]
	codes = [r.name for r in rows]
	if not codes:
		return []
	from marketplace.storefront import _get_prices, _get_stock, _get_variant_stock

	prices = _get_prices(codes)
	warehouse = frappe.db.get_value("Shop", shop, "warehouse")
	stock = _get_stock(codes, warehouse)
	stock.update(_get_variant_stock([r.name for r in rows if r.has_variants], warehouse))

	def in_stock(r):  # storefront._build_catalog bilan bir xil qoida
		if r.mp_tez_kunda:
			return False
		return (stock.get(r.name, 0) > 0) if (r.is_stock_item or r.has_variants) else True

	return [
		{
			"kod": r.name,
			"nom": r.item_name,
			"narx": int(round(float(prices[r.name]))) if prices.get(r.name) else None,
			"holat": "bor" if in_stock(r) else "tugagan",
			"havola": get_url(f"/s/{shop}/p/{r.name}"),
		}
		for r in rows
	]


POST_LIMIT = 1500


def build_prompt(shop_name, malumot, items, matn, turi, tarix=None, post_matni=None):
	dm = turi == "DM"
	data = json.dumps({"AI uchun ma'lumot": malumot or "", "tovarlar": items}, ensure_ascii=False, indent=1)
	lines = ""
	if tarix:
		turns = "\n".join(f"{t.get('kim')}: {t.get('matn')}" for t in tarix[-HISTORY_LIMIT:])
		lines = f"\nOldingi yozishma (eskisi birinchi):\n{turns}\n"
	post = ""
	if post_matni and post_matni.strip():
		post = f"\nPost matni (JSON):\n{json.dumps(post_matni.strip()[:POST_LIMIT], ensure_ascii=False)}\n"
	return PROMPT.format(
		shop=shop_name,
		turi_nomi="Direct xabar" if dm else "izoh",
		uzunlik="ko'pi bilan 3 gap" if dm else "ko'pi bilan 2 gap",
		noaniq=("mijozdan qaysi kitob yoki tovarni nazarda tutayotganini so'ra" if dm
			else "salomlashib, «Menejerimiz Direct'da aniqlab beradi» deb javob ber"),
		data=data,
		post=post,
		tarix=lines,
		matn=matn,
	)


def parse_reply(raw):
	text = (raw or "").strip()
	start, end = text.find("{"), text.rfind("}")
	if start < 0 or end <= start:
		raise IgAiError(_("AI javobida JSON topilmadi"), retry=True)
	try:
		data = json.loads(text[start : end + 1])
	except ValueError as e:
		raise IgAiError(_("AI javobi JSON emas"), retry=True) from e
	if not isinstance(data, dict):
		raise IgAiError(_("AI javobi JSON obyekt emas"), retry=True)

	def opt(key):
		value = data.get(key)
		return str(value).strip() or None if value not in (None, "") else None

	out = {
		"javob_kerak": data.get("javob_kerak") is True or str(data.get("javob_kerak")).lower() == "true",
		"javob": str(data.get("javob") or "").strip(),
		"til": str(data.get("til") or "").strip(),
		"telefon": opt("telefon"),
		"ism": opt("ism"),
		"tovar_kodi": opt("tovar_kodi"),
	}
	if out["javob_kerak"] and not out["javob"]:
		raise IgAiError(_("AI bo'sh javob qaytardi"), retry=True)
	return out


def extract_phone(text):
	"""Matndagi birinchi 9 va undan ko'p raqamli qator (bo'shliq, tire, qavs bilan ham) — 998... ko'rinishida."""
	for m in re.finditer(r"\+?\d[\d\s().\-]{7,}\d", text or ""):
		if len(re.sub(r"\D", "", m.group())) >= 9:
			return normalize_phone(m.group())
	return None


def _call(model, prompt):
	from marketplace.telegram_bot import http  # faqat IPv4

	body = {
		"contents": [{"parts": [{"text": prompt}]}],
		"generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
	}
	try:
		r = http.post(stt.API.format(model=model), headers={"x-goog-api-key": stt.api_key()}, json=body, timeout=60)
	except requests.RequestException as e:
		raise IgAiError(_("Gemini'ga ulanib bo'lmadi: {0}").format(e.__class__.__name__), retry=True) from e
	if r.status_code != 200:
		try:
			message = r.json().get("error", {}).get("message") or r.text
		except ValueError:
			message = r.text
		message = (message or "")[:300]
		if r.status_code == 429:
			raise IgAiError(_("Gemini kvotasi tugadi (429): {0}").format(message), pause=True)
		if r.status_code in (500, 502, 503, 504):
			raise IgAiError(_("Gemini band ({0})").format(r.status_code), retry=True)
		if r.status_code == 404:
			raise IgAiError(_("«{0}» modeli topilmadi").format(model), retry=True, missing=True)
		if r.status_code in (401, 403) or "API key" in message:
			raise IgAiError(_("Gemini API kalit noto'g'ri yoki ruxsati yo'q: {0}").format(message))
		raise IgAiError(_("Gemini xatosi ({0}): {1}").format(r.status_code, message))
	try:
		parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
		return "".join(p.get("text", "") for p in parts)
	except (ValueError, AttributeError, TypeError, IndexError, KeyError) as e:
		raise IgAiError(_("Gemini javobi tushunarsiz ({0})").format(e.__class__.__name__), retry=True) from e


def _ask(prompt):
	"""Asosiy model, band/topilmasa — zaxira; ikkalasi topilmasa — kalitdagi flash modellari. Qaytaradi (raw, model)."""
	cfg = stt.settings()
	models = list(dict.fromkeys(m.strip() for m in (cfg.gemini_model, cfg.zaxira_model) if m and m.strip()))
	if not models:
		raise IgAiError(_("Gemini model yozilmagan"))
	errors, last, auto_added, i = [], None, False, 0
	while i < len(models):
		model = models[i]
		i += 1
		try:
			return _call(model, prompt), model
		except IgAiError as e:
			if not e.retry:
				raise  # kvota yoki kalit — boshqa model ham o'tmaydi
			last = e
			errors.append(f"{model}: {e}")
		if i == len(models) and not auto_added and last and last.missing:
			auto_added = True
			models += [m for m in stt.auto_models() if m not in models][:2]
	raise IgAiError("; ".join(errors)[:480], retry=True)


def answer(shop, matn, turi="Izoh", tarix=None, post_matni=None):
	"""Mijoz yozuviga javob: parse_reply natijasi + "model". Telefon AI topmasa — matndan olinadi.
	post_matni — izoh yozilgan post/reklama matni: katalogda shu postdagi tovar birinchi turadi."""
	info = frappe.db.get_value("Shop", shop, ["shop_name", "ig_ai_malumot"], as_dict=True) or {}
	hint = "\n".join(t for t in (post_matni, matn) if t)
	prompt = build_prompt(info.get("shop_name") or shop, info.get("ig_ai_malumot"), catalog(shop, hint=hint), matn, turi,
		tarix, post_matni)
	raw, model = _ask(prompt)
	out = parse_reply(raw)
	out["telefon"] = normalize_phone(out["telefon"]) if out["telefon"] else extract_phone(matn)
	out["model"] = model
	return out
