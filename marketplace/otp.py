"""Telefon raqamini tasdiqlash kodi (OTP).

Kod Telegram Gateway orqali yuboriladi: mijozga "Verification Codes" rasmiy akkauntidan
xabar keladi, botga /start bosish shart emas. Hujjat: https://core.telegram.org/gateway/api

Xavfsizlik:
  * bazada kodning o'zi emas, faqat HMAC xeshi saqlanadi;
  * har kodga ko'pi bilan 5 ta urinish, muddati (default 5 daqiqa);
  * bitta raqamga qayta yuborish 60 soniyadan keyin, soatiga ko'pi bilan 5 ta kod
    (aks holda kimdir Telegram balansimizni bir kechada tugatishi mumkin).
"""

import hashlib
import hmac
import re
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

GATEWAY_URL = "https://gatewayapi.telegram.org/sendVerificationMessage"
MAX_ATTEMPTS = 5
MAX_PER_HOUR = 5


def normalize_phone(raw):
	"""'90 123-45-67', '998901234567', '+998 (90) 123 45 67' -> '+998901234567'. Noto'g'ri bo'lsa xato."""
	digits = re.sub(r"\D", "", raw or "")
	if len(digits) == 9:
		digits = "998" + digits
	if not re.fullmatch(r"998\d{9}", digits):
		frappe.throw(_("Telefon raqami noto‘g‘ri. Masalan: 90 123 45 67"), title=_("Telefon"))
	return "+" + digits


def mask_phone(phone):
	"""+998901234567 -> +998 90 *** 45 67"""
	return f"{phone[:4]} {phone[4:6]} *** {phone[9:11]} {phone[11:13]}"


def settings():
	return frappe.get_cached_doc("Marketplace Settings")


def send_code(phone, return_path=None):
	"""Yangi kod yaratadi va yuboradi. Qaytaradi: {masked, ttl, resend_after, channel, [dev_code]}."""
	cfg = settings()
	resend_after = cint(cfg.otp_resend_after) or 60
	ttl = cint(cfg.otp_ttl) or 300

	last = frappe.db.get_value(
		"OTP Request", {"phone": phone}, ["creation"], order_by="creation desc", as_dict=True
	)
	if last:
		wait = resend_after - int((now_datetime() - get_datetime(last.creation)).total_seconds())
		if wait > 0:
			frappe.throw(_("Yangi kodni {0} soniyadan keyin so‘rash mumkin").format(wait), title=_("Biroz kuting"))

	sent_last_hour = frappe.db.count(
		"OTP Request", {"phone": phone, "creation": [">", add_to_date(now_datetime(), hours=-1)]}
	)
	if sent_last_hour >= MAX_PER_HOUR:
		frappe.throw(_("Bu raqamga juda ko‘p kod yuborildi. 1 soatdan keyin urinib ko‘ring."), title=_("Cheklov"))

	length = min(max(cint(cfg.otp_length) or 6, 4), 8)
	code = "".join(secrets.choice("0123456789") for _ in range(length))

	channel = {"Telegram Gateway": "Telegram", "Telegram Bot": "Telegram Bot"}.get(cfg.otp_provider, "Test")
	otp = frappe.get_doc(
		{
			"doctype": "OTP Request",
			"phone": phone,
			"expires_at": add_to_date(now_datetime(), seconds=ttl),
			"ip": frappe.local.request_ip,
			"channel": channel,
			"return_path": return_path if (return_path or "").startswith("/s/") else None,
		}
	)
	otp.insert(ignore_permissions=True)

	out = {"masked": mask_phone(phone), "ttl": ttl, "resend_after": resend_after, "channel": otp.channel, "length": length}
	if channel == "Telegram Bot":
		# Kod shu yerda yaratilmaydi: bot uni yuborayotgan paytda yaratadi (deliver_bot_code)
		from marketplace import telegram_bot

		out["bot_username"] = cfg.telegram_bot_username
		chat_id = telegram_bot.chat_for_phone(phone)
		if chat_id and deliver_bot_code(otp.name, chat_id):
			out["bot_sent"] = True
		else:
			# Havolada so'rov ID'si: bot Start'da qaysi raqam uchun kod so'ralganini biladi (telegram_bot.on_start)
			out["bot_link"] = telegram_bot.bot_link(start=f"k{otp.name}")
			if not out["bot_link"]:
				frappe.log_error("Telegram bot sozlanmagan (token/username yo'q)", "Marketplace OTP")
				frappe.throw(_("Kod yuborib bo‘lmadi. Birozdan keyin urinib ko‘ring."))
		return out

	otp.db_set("code_hash", _hash(otp.name, code))
	if otp.channel == "Telegram":
		otp.db_set("provider_request_id", _send_telegram(cfg, phone, code, ttl))
	else:
		# Test rejimi: token'siz ishlab chiqish va demo uchun
		frappe.logger("marketplace").info(f"OTP {phone}: {code}")
		print(f"\n*** TEST OTP {phone}: {code} ***\n")
		if frappe.conf.developer_mode:
			out["dev_code"] = code
	return out


def verify_code(phone, code):
	"""To'g'ri bo'lsa True. Noto'g'ri bo'lsa xato (qolgan urinishlar soni bilan)."""
	otp = frappe.db.get_value(
		"OTP Request",
		{"phone": phone, "used": 0},
		["name", "code_hash", "expires_at", "attempts"],
		order_by="creation desc",
		as_dict=True,
		for_update=True,  # bir vaqtda ikki so'rov bir kodni ikki marta ishlatmasin
	)
	if not otp or get_datetime(otp.expires_at) < now_datetime():
		frappe.throw(_("Kod muddati tugagan. Yangi kod so‘rang."), title=_("Kod"))
	if not otp.code_hash:
		frappe.throw(_("Avval Telegram botda «📱 Raqamni yuborish» tugmasini bosing — kod o‘sha yerga keladi."), title=_("Kod"))
	if otp.attempts >= MAX_ATTEMPTS:
		frappe.throw(_("Urinishlar tugadi. Yangi kod so‘rang."), title=_("Kod"))

	code = re.sub(r"\D", "", code or "")
	if not hmac.compare_digest(otp.code_hash or "", _hash(otp.name, code)):
		frappe.db.set_value("OTP Request", otp.name, "attempts", otp.attempts + 1)
		frappe.db.commit()  # urinish soni xato qaytsa ham saqlansin
		left = MAX_ATTEMPTS - otp.attempts - 1
		frappe.throw(_("Kod noto‘g‘ri. Yana {0} ta urinish qoldi.").format(left), title=_("Kod"))

	frappe.db.set_value("OTP Request", otp.name, "used", 1)
	return True


def pending_bot_request(phone):
	"""Bot orqali kod kutayotgan (hali yuborilmagan, muddati o'tmagan) so'rov."""
	return frappe.db.get_value(
		"OTP Request",
		{
			"phone": phone,
			"channel": "Telegram Bot",
			"used": 0,
			"code_hash": ["is", "not set"],
			"expires_at": [">", now_datetime()],
		},
		"name",
		order_by="creation desc",
	)


def create_bot_request(phone):
	"""Mijoz saytda kod so'ramay, to'g'ridan-to'g'ri botga raqamini yuborgan bo'lsa. Soatlik cheklov amal qiladi."""
	cfg = settings()
	sent_last_hour = frappe.db.count(
		"OTP Request", {"phone": phone, "creation": [">", add_to_date(now_datetime(), hours=-1)]}
	)
	if sent_last_hour >= MAX_PER_HOUR:
		return None
	last_path = frappe.db.get_value(
		"OTP Request", {"phone": phone, "return_path": ["is", "set"]}, "return_path", order_by="creation desc"
	)
	return (
		frappe.get_doc(
			{
				"doctype": "OTP Request",
				"phone": phone,
				"channel": "Telegram Bot",
				"expires_at": add_to_date(now_datetime(), seconds=cint(cfg.otp_ttl) or 300),
				"return_path": last_path,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def deliver_bot_code(name, chat_id):
	"""Kodni yaratib, bot orqali yuboradi. Bazaga faqat xeshi yoziladi. Yuborilmasa False."""
	from marketplace import telegram_bot

	cfg = settings()
	length = min(max(cint(cfg.otp_length) or 6, 4), 8)
	code = "".join(secrets.choice("0123456789") for _ in range(length))
	minutes = max(1, (cint(cfg.otp_ttl) or 300) // 60)
	path = frappe.db.get_value("OTP Request", name, "return_path")
	text = f"🔐 Tasdiqlash kodingiz: <code>{code}</code>\n\nKodni saytdagi katakchalarga yozing. U {minutes} daqiqa amal qiladi, hech kimga bermang."
	button = telegram_bot.return_button(path)
	try:
		if button:
			telegram_bot.send(chat_id, "✅ Raqamingiz tasdiqlandi.", reply_markup=telegram_bot.REMOVE_KEYBOARD)
		telegram_bot.send(chat_id, text, reply_markup=button or telegram_bot.REMOVE_KEYBOARD)
	except telegram_bot.TelegramError as e:
		phone = frappe.db.get_value("OTP Request", name, "phone")
		if e.code == 403 and phone:  # mijoz botni bloklagan
			telegram_bot.mark_blocked(phone)
		frappe.log_error(f"Telegram bot kodi yuborilmadi: {e}", "Marketplace OTP")
		return False
	frappe.db.set_value("OTP Request", name, "code_hash", _hash(name, code))
	return True


def cleanup_expired():
	"""Soatlik scheduler: 1 kundan eski kodlarni o'chiradi."""
	frappe.db.delete("OTP Request", {"creation": ["<", add_to_date(now_datetime(), days=-1)]})


def _hash(name, code):
	key = frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret") or "marketplace"
	return hmac.new(key.encode(), f"{name}:{code}".encode(), hashlib.sha256).hexdigest()


def _send_telegram(cfg, phone, code, ttl):
	from frappe.utils.password import get_decrypted_password

	# Single DocType keshidagi hujjatda get_password ba'zan bo'sh qaytaradi: to'g'ridan-to'g'ri o'qiymiz
	token = get_decrypted_password("Marketplace Settings", "Marketplace Settings", "telegram_gateway_token", raise_exception=False)
	if not token:
		frappe.log_error("Telegram Gateway token kiritilmagan", "Marketplace OTP")
		frappe.throw(_("Kod yuborib bo‘lmadi. Birozdan keyin urinib ko‘ring."))
	try:
		from marketplace.telegram_bot import http  # faqat IPv4: IPv6 yo'li yo'q tarmoqda 10 s qotmasin

		resp = http.post(
			GATEWAY_URL,
			headers={"Authorization": f"Bearer {token}"},
			json={"phone_number": phone, "code": code, "ttl": max(30, min(ttl, 3600))},
			timeout=10,
		)
		data = resp.json()
	except Exception:
		frappe.log_error("Telegram Gateway'ga ulanib bo'lmadi", "Marketplace OTP")
		frappe.throw(_("Kod yuborib bo‘lmadi. Internet yoki xizmatda muammo, birozdan keyin urinib ko‘ring."))

	if not data.get("ok"):
		error = data.get("error", "UNKNOWN")
		frappe.log_error(f"Telegram Gateway xatosi: {error}", "Marketplace OTP")
		if "PHONE" in error:
			frappe.throw(_("Bu raqamga Telegram orqali kod yuborib bo‘lmadi. Raqamda Telegram borligini tekshiring."))
		frappe.throw(_("Kod yuborib bo‘lmadi. Birozdan keyin urinib ko‘ring."))
	return data["result"].get("request_id")
