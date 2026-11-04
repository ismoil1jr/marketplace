"""Telefoniya: sotuv menejeri telefonidagi ASMIZ Call Agent ilovasi har bir qo'ng'iroqni (audio bilan) shu yerga yuboradi.

Ilova manzilni o'zi qo'shadi: /api/method/asmiz_call.api.ingest_call (yoki eski
target_zenit.telefoniya.api.ingest_call) — hooks.override_whitelisted_methods ikkalasini ham ingest_call'ga yo'naltiradi.
So'rov: "Authorization: token api_key:api_secret" (menejerning o'z API kaliti) va multipart:
phone_number, direction (incoming/outgoing), started_at, duration_sec, employee_id, target_number, target_sim_slot,
contact_name, device_model, client_call_id, file_hash + audio fayl.

Qo'ng'iroq mijozga RAQAM bo'yicha bog'lanadi: "998XXXXXXXXX" saytdagi buyurtmaning customer_phone'i bilan solishtiriladi
(shu menejer do'koni buyurtmalari ichida) — mos kelsa mijoz va uning oxirgi buyurtmasi qo'ng'iroqqa yoziladi.
Buyurtmada ham, murojaatda ham bo'lmagan raqam (shaxsiy qo'ng'iroq) saqlanmaydi — Telefoniya Sozlamalari'dagi
"Shaxsiy qo'ng'iroqlarni ham saqlash" yoqilmagan bo'lsa.
"""

import json
import logging
import re
from datetime import datetime, timezone

import frappe
from frappe import _
from frappe.utils import cint, convert_utc_to_system_timezone, get_datetime, now_datetime

from marketplace.permissions import get_user_shop

ALLOWED_ROLES = {"Shop Sales Manager", "Shop Seller", "System Manager", "Marketplace Manager"}
# Mijoz raqami: ilova versiyasiga qarab maydon nomi har xil bo'lishi mumkin — birinchi to'ldirilgani olinadi
PHONE_KEYS = ("phone_number", "phone", "number", "remote_number", "other_number", "callee", "caller", "msisdn", "contact_number")


def normalize_phone(raw):
	"""'+998 90 123-45-67', '901234567', '998901234567' -> '998901234567'. O'zbek raqami bo'lmasa — faqat raqamlar.
	Telefon jurnalida eski mahalliy ko'rinish ham uchraydi: '8 90 123 45 67', '0901234567' (10 raqam) — ular ham 998..."""
	digits = re.sub(r"\D", "", raw or "")
	if len(digits) == 10 and digits[0] in "08":
		digits = digits[1:]
	if len(digits) == 9:
		digits = "998" + digits
	return digits or None


@frappe.whitelist(methods=["POST"])
def ingest_call(**kwargs):
	"""Ilovadan kelgan bitta qo'ng'iroq. Qaytaradi: {"status": "ok", "name", "duplicate", "matched"}.
	Bir xil qo'ng'iroq qayta kelsa (client_call_id yoki fayl hash bo'yicha) — yangisi yaratilmaydi."""
	if frappe.session.user == "Guest":
		raise frappe.AuthenticationError(_("API token kerak"))
	if not ALLOWED_ROLES & set(frappe.get_roles()):
		raise frappe.PermissionError(_("Bu foydalanuvchi qo'ng'iroq yubora olmaydi (Sotuv menejer roli kerak)"))

	form = frappe.form_dict
	client_id = (form.get("client_call_id") or "").strip()[:140]
	file_hash = (form.get("file_hash") or "").strip()[:140]
	for field, value in (("client_call_id", client_id), ("yozuv_hash", file_hash)):
		if value and (old := frappe.db.get_value("Telefon Qongiroq", {field: value})):
			return {"status": "ok", "name": old, "duplicate": True, "matched": bool(frappe.db.get_value("Telefon Qongiroq", old, "mijoz"))}

	phone = next((str(form.get(k)).strip() for k in PHONE_KEYS if str(form.get(k) or "").strip()), "")
	normal = normalize_phone(phone)
	own_shop = get_user_shop()
	order = _match_order(normal, own_shop)
	lead = _match_lead(normal, order.shop if order else own_shop)
	if not (order or lead) and not cint(frappe.db.get_single_value("Telefoniya Sozlamalari", "hammasini_saqlash")):
		# Do'kon mijozi bo'lmagan raqam (shaxsiy qo'ng'iroq): yozuv ham, audio ham saqlanmaydi.
		# Javob 2xx — ilova faylni "yuborildi" deb hisoblaydi va qayta yubormaydi
		_log_skipped(phone, form)
		return {"status": "ok", "name": None, "duplicate": False, "matched": False, "skipped": True,
		        "sabab": _("Bu raqam do'kon mijozlari (buyurtma, murojaat) orasida yo'q — qo'ng'iroq saqlanmadi")}

	upload, content = _upload()
	limit_mb = cint(frappe.db.get_single_value("Telefoniya Sozlamalari", "maks_fayl_mb")) or 25
	if content and len(content) > limit_mb * 1024 * 1024:
		# 4xx: ilova qayta yubormaydi (5xx bo'lganda qayta urinadi)
		raise frappe.ValidationError(_("Yozuv fayli juda katta: {0} MB (chegara {1} MB)").format(round(len(content) / 1048576, 1), limit_mb))
	direction = (form.get("direction") or "").strip().lower()

	doc = frappe.get_doc(
		{
			"doctype": "Telefon Qongiroq",
			"telefon": phone[:140],
			"normal_telefon": normal,
			"yonalish": "Kiruvchi" if direction in ("incoming", "inbound", "in", "kiruvchi") else "Chiquvchi",
			"boshlandi": _parse_time(form.get("started_at")),
			"davomiyligi": cint(form.get("duration_sec")),
			"manba": "Android",
			"mijoz": order.customer if order else None,
			"mijoz_ismi": order.customer_name if order else (lead.mijoz_ismi if lead else (form.get("contact_name") or "")[:140] or None),
			"buyurtma": order.name if order else None,
			"murojaat": lead.name if lead else None,
			"shop": order.shop if order else (lead.shop if lead else own_shop),
			"menejer": frappe.session.user,
			"xodim_id": (form.get("employee_id") or "")[:140],
			"ish_raqami": (form.get("target_number") or "")[:140],
			"sim_slot": str(form.get("target_sim_slot") or "")[:20],
			"kontakt_ism": (form.get("contact_name") or "")[:140],
			"qurilma": (form.get("device_model") or "")[:140],
			"client_call_id": client_id or None,
			"yozuv_hash": file_hash or None,
			# Ilova nima yuborgani (fayldan tashqari) — raqam kelmasa sababini shu yerdan ko'ramiz
			"ilova_xom": json.dumps({k: v for k, v in form.items() if k != "cmd" and isinstance(v, str)}, ensure_ascii=False)[:2000],
		}
	)
	doc.insert(ignore_permissions=True)
	if content:
		_attach_audio(doc, upload, content)
		from marketplace.sotuv import stt

		stt.enqueue(doc.name)  # AI yoqilgan bo'lsa — yozuv fonda matnga aylanadi va qisqa tahlil yoziladi
	return {"status": "ok", "name": doc.name, "duplicate": False, "matched": bool(order or lead)}


def _log_skipped(phone, form):
	"""Saqlanmagan qo'ng'iroq — logs/telefoniya.log: mijoz qo'ng'irog'i "tushmadi" desa, ilova nima yuborganini shu yerdan
	ko'ramiz. Raqam yashiriladi (format va oxirgi 4 raqam), audio va kontakt nomi yozilmaydi."""
	digits = re.sub(r"\D", "", phone or "")
	masked = f"{phone[:1]}{'*' * max(len(digits) - 5, 0)}{digits[-4:]}" if digits else "bo'sh"
	log = frappe.logger("telefoniya")
	log.setLevel(logging.INFO)  # Frappe prod'da standart darajasi ERROR — bu diagnostika esa doim yozilsin
	log.info(
		f"saqlanmadi: user={frappe.session.user} raqam={masked} ({len(digits)} raqam) "
		f"yonalish={form.get('direction') or '-'} sek={form.get('duration_sec') or '-'} boshlandi={form.get('started_at') or '-'} "
		f"id={(form.get('client_call_id') or '')[:16]}"
	)


def _match_order(normal, shop):
	"""Shu raqamdan tushgan oxirgi buyurtma (menejer do'koni ichida): avval to'lanmagani, bo'lmasa istalgani."""
	if not normal or not normal.startswith("998") or len(normal) != 12:
		return None
	filters = {"customer_phone": "+" + normal, "docstatus": ["in", [1, 2]]}
	if shop:
		filters["shop"] = shop
	fields = ["name", "customer", "customer_name", "shop"]
	return (
		frappe.db.get_value("Sales Order", {**filters, "docstatus": 1, "payment_status": "Kutilmoqda"}, fields, as_dict=True, order_by="creation desc")
		or frappe.db.get_value("Sales Order", filters, fields, as_dict=True, order_by="creation desc")
	)


def _match_lead(normal, shop):
	"""Shu raqamdan kelgan oxirgi Instagram murojaati (menejer do'koni ichida)."""
	if not normal or len(normal) < 9 or not shop:
		return None
	return frappe.db.get_value(
		"Murojaat", {"normal_telefon": normal, "shop": shop}, ["name", "mijoz_ismi", "shop"], as_dict=True, order_by="creation desc"
	)


def _parse_time(value):
	"""Ilova vaqtni epoch (ms yoki s) yoki ISO ko'rinishda yuborishi mumkin. Bo'lmasa — hozir."""
	value = (str(value or "")).strip()
	if not value:
		return now_datetime()
	if value.isdigit():
		ts = int(value) / (1000 if len(value) > 11 else 1)
		utc = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
		return convert_utc_to_system_timezone(utc).replace(tzinfo=None)
	try:
		dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
	except ValueError:
		return get_datetime(value)
	if dt.tzinfo:
		return convert_utc_to_system_timezone(dt.astimezone(timezone.utc).replace(tzinfo=None)).replace(tzinfo=None)
	return dt


def _upload():
	"""Multipart'dagi audio fayl: (upload, bayt) yoki (None, None)."""
	request = getattr(frappe.local, "request", None)
	files = getattr(request, "files", None) or {}
	upload = files.get("file") or next(iter(files.values()), None)
	if not upload:
		return None, None
	return upload, upload.stream.read() or None


def _attach_audio(doc, upload, content):
	"""Audio fayl qo'ng'iroqqa yopiq (private) fayl bo'lib biriktiriladi.
	File'ni content bilan yaratamiz: eski frappe.utils.file_manager.save_file v16 da faylni ikki marta yozib, binary'ni buzadi."""
	saved = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": upload.filename or f"{doc.name}.m4a",
			"is_private": 1,
			"content": content,
			"attached_to_doctype": "Telefon Qongiroq",
			"attached_to_name": doc.name,
			"attached_to_field": "yozuv",
		}
	)
	saved.save(ignore_permissions=True)
	doc.db_set({"yozuv": saved.file_url, "yozuv_bor": 1, "fayl_hajmi": len(content), "holat": "Yozuv bor"})
