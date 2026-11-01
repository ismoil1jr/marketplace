"""Platformaning o'z Telegram boti.

Ikki vazifa:
1. Mijozning saytga kirishi (tg_login.py): saytda "Telegram orqali tasdiqlash" botni t.me/<bot>?start=l<id> bilan ochadi;
   botda "📱 Raqamni yuborish" bosiladi; bot raqam o'ziniki ekanini (contact.user_id == from.id) tekshiradi va
   raqam, ism, familiyani so'rovga yozadi — sayt o'zi kirib ketadi, mijoz hech narsa yozmaydi.
   Raqam ↔ chat Telegram Contact'da qoladi.
2. Do'konchilarga "Yangi buyurtma" xabari va "Buyurtmani ko'rish" tugmasi. Kimga yuborishni Shop'dagi
   telegram_ids (admin kiritadi) va Marketplace Settings'dagi admin ID belgilaydi.
3. Do'kon egasi botda omborini ko'radi: "📦 Ombor" -> tovar -> variantlar qoldig'i (telegram_ombor.py, faqat ko'rish:
   kirim — Desk'dagi tovar formasida). "Kam qoldi / tugadi" xabarlari ham shu ID'ga keladi (inventory.py).

Telegram bilan aloqa:
* production: webhook — https://<sayt>/api/method/marketplace.telegram_bot.webhook
  (sozlamalarda "Webhook'ni o'rnatish"; so'rov maxfiy kalit sarlavhasi bilan tekshiriladi);
* lokal (127.0.0.1, internetdan ochilmaydi): `bench --site <sayt> execute marketplace.telegram_bot.poll`
  alohida terminalda ishlab turadi.
"""

import html
import json
import secrets
import socket
import time

import frappe
import requests
from frappe import _
from frappe.utils import cint, get_url
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool

API = "https://api.telegram.org/bot{token}/{method}"


# ---------- Telegram'ga faqat IPv4 orqali ----------
# Ba'zi tarmoqlarda (shu jumladan lokal server) IPv6 manzil bor, lekin yo'l yo'q: Python avval IPv6'ni sinab,
# har so'rovda 15-40 soniya qotadi — bot /start'ga javob bermaydi, kod kech keladi. Telegram IPv4'da doim ishlaydi.


class _IPv4Connection(HTTPSConnection):
	def _new_conn(self):
		host = self._dns_host
		try:
			self._dns_host = socket.getaddrinfo(host, self.port, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
		except OSError:
			pass  # nom topilmasa — urllib3 o'zi tushunarli xato beradi
		try:
			# TLS va sertifikat tekshiruvi self.host (asl domen) bilan qoladi
			return super()._new_conn()
		finally:
			self._dns_host = host


class _IPv4Pool(HTTPSConnectionPool):
	ConnectionCls = _IPv4Connection


class _IPv4Adapter(HTTPAdapter):
	def init_poolmanager(self, *args, **kwargs):
		super().init_poolmanager(*args, **kwargs)
		self.poolmanager.pool_classes_by_scheme = {**self.poolmanager.pool_classes_by_scheme, "https": _IPv4Pool}


http = requests.Session()
http.mount("https://api.telegram.org", _IPv4Adapter())
http.mount("https://gatewayapi.telegram.org", _IPv4Adapter())
# callback_query — Ombor tugmalari (inline keyboard) bosilganda keladi
ALLOWED_UPDATES = ["message", "callback_query"]


class TelegramError(Exception):
	def __init__(self, description, code=None):
		super().__init__(description)
		self.code = code


# ---------- Sozlamalar va API ----------


def settings():
	return frappe.get_cached_doc("Marketplace Settings")


def token():
	from frappe.utils.password import get_decrypted_password

	return get_decrypted_password(
		"Marketplace Settings", "Marketplace Settings", "telegram_bot_token", raise_exception=False
	)


def call(method, http_timeout=15, **params):
	"""Bot API chaqiruvi. Xato bo'lsa TelegramError (description va error_code bilan)."""
	tok = token()
	if not tok:
		raise TelegramError("Bot token kiritilmagan")
	try:
		r = http.post(API.format(token=tok, method=method), json=params, timeout=http_timeout)
		data = r.json()
	except Exception as e:
		raise TelegramError(f"Telegram'ga ulanib bo'lmadi: {e}") from e
	if not data.get("ok"):
		raise TelegramError(data.get("description") or "Telegram xatosi", data.get("error_code"))
	return data.get("result")


def send(chat_id, text, **params):
	return call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True, **params)


def site_url():
	return (settings().site_url or get_url()).rstrip("/")


def bot_link(start=None):
	username = settings().telegram_bot_username
	if not username:
		return None
	return f"https://t.me/{username}" + (f"?start={start}" if start else "")


# ---------- Kirish nuqtalari: webhook va polling ----------


@frappe.whitelist(allow_guest=True, methods=["POST"])
def webhook():
	secret = settings().telegram_webhook_secret
	header = frappe.get_request_header("X-Telegram-Bot-Api-Secret-Token") or ""
	if not secret or not secrets.compare_digest(secret, header):
		raise frappe.PermissionError
	try:
		handle_update(json.loads(frappe.request.get_data(as_text=True) or "{}"))
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Telegram bot: update xatosi")
	# Telegram 200 olmasa, shu update'ni qayta-qayta yuboraveradi
	return "ok"


def poll():
	"""Lokal ishlab chiqish uchun: getUpdates bilan uzluksiz o'qiydi.

	`bench start` bilan birga ishlashi uchun Procfile'ga qo'shiladi:
	    telegram: bench --site marketplace.local execute marketplace.telegram_bot.poll
	Jarayon hech qachon o'zi tugamaydi (token yo'q, internet uzildi, baza qayta ulandi — kutib, qayta uriniladi):
	Procfile'dagi bitta jarayon tugasa, honcho butun `bench start`ni to'xtatadi.
	"""
	offset, announced = None, False
	code_seen = _code_mtime()
	while True:
		try:
			frappe.clear_document_cache("Marketplace Settings", "Marketplace Settings")
			if not token():
				time.sleep(15)
				continue
			if not announced:
				call("deleteWebhook")
				frappe.db.set_single_value("Marketplace Settings", "telegram_mode", "Polling (lokal)")
				frappe.db.commit()
				print(f"@{call('getMe')['username']} ishga tushdi (polling)", flush=True)
				announced = True
			updates = call("getUpdates", http_timeout=40, timeout=30, offset=offset, allowed_updates=ALLOWED_UPDATES)
		except TelegramError as e:
			print("Telegram:", e, flush=True)
			time.sleep(5)
			continue
		except Exception:
			_reconnect()
			time.sleep(5)
			continue
		for update in updates or []:
			offset = update["update_id"] + 1
			try:
				handle_update(update)
				frappe.db.commit()
			except Exception:
				_reconnect()
				frappe.log_error("Telegram bot: update xatosi")
				frappe.db.commit()
		code_seen = _reload_if_changed(code_seen, offset)


def _code_mtime():
	"""Ilova .py fayllaridan eng oxirgi o'zgargani (vaqti)."""
	import os

	latest = 0.0
	for folder, dirs, files in os.walk(frappe.get_app_path("marketplace")):
		dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", "public")]
		for f in files:
			if f.endswith(".py"):
				latest = max(latest, os.path.getmtime(os.path.join(folder, f)))
	return latest


def _reload_if_changed(seen, offset):
	"""Kod o'zgarsa (lokal ishlab chiqish), bot o'zini yangi kod bilan qayta ishga tushiradi — `bench start`ni
	qayta ishga tushirish shart emas. os.execv: PID o'sha qoladi, honcho buni sezmaydi.
	Yangi kod xato bo'lsa (import bo'lmasa) — qayta ishga tushmaydi, eskisi bilan ishlab turadi: honcho'da bitta
	jarayon yiqilsa, butun `bench start` to'xtaydi."""
	import os
	import subprocess
	import sys

	latest = _code_mtime()
	if latest <= seen or time.time() - latest < 2:  # fayl hali saqlanayotgan bo'lishi mumkin
		return seen
	check = subprocess.run(
		[sys.executable, "-c", "import marketplace.telegram_bot, marketplace.tg_login, marketplace.telegram_ombor, marketplace.otp"],
		capture_output=True, text=True, timeout=60,
	)
	if check.returncode:
		print("Bot: yangi kodda xato — eski kod bilan ishlashda davom etadi:\n" + check.stderr[-800:], flush=True)
		return latest
	if offset:
		try:
			call("getUpdates", offset=offset, timeout=0)  # ishlangan xabarlar Telegram'da tasdiqlanadi — qayta kelmaydi
		except TelegramError:
			pass
	print("Bot: kod o'zgardi — yangi kod bilan qayta ishga tushmoqda", flush=True)
	try:
		with open("/proc/self/cmdline", "rb") as f:
			argv = [x.decode() for x in f.read().split(b"\0") if x]
	except OSError:
		argv = [sys.executable, "-m", "frappe.utils.bench_helper", *sys.argv[1:]]
	os.execv(argv[0], argv)


def _reconnect():
	"""Uzoq ishlaydigan jarayon: baza ulanishi uzilgan bo'lsa (wait_timeout), qayta ulanadi."""
	try:
		frappe.db.rollback()
		frappe.db.sql("select 1")
	except Exception:
		try:
			frappe.db.close()
		except Exception:
			pass
		frappe.connect(site=frappe.local.site)


@frappe.whitelist()
def set_webhook():
	"""Sozlamalar formasidagi tugma: Telegram'ga webhook manzilini aytadi (sayt internetdan ochiq bo'lishi kerak)."""
	frappe.only_for(("System Manager", "Marketplace Manager"))
	url = f"{site_url()}/api/method/marketplace.telegram_bot.webhook"
	if not url.startswith("https://"):
		frappe.throw(_("Webhook faqat https manzil bilan ishlaydi. Lokal kompyuterda polling'ni ishlating."))
	secret = settings().telegram_webhook_secret or secrets.token_urlsafe(32)
	call("setWebhook", url=url, secret_token=secret, allowed_updates=ALLOWED_UPDATES, drop_pending_updates=True)
	frappe.db.set_single_value("Marketplace Settings", {"telegram_webhook_secret": secret, "telegram_mode": f"Webhook: {url}"})
	return url


# ---------- Kelgan xabarlarni qayta ishlash ----------

CONTACT_KEYBOARD = {
	"keyboard": [[{"text": "📱 Raqamni yuborish", "request_contact": True}]],
	"resize_keyboard": True,
	"one_time_keyboard": True,
}
REMOVE_KEYBOARD = {"remove_keyboard": True}


def handle_update(update):
	from marketplace import telegram_ombor

	if update.get("callback_query"):
		if (update["callback_query"].get("data") or "").startswith("tgl:"):
			on_login_callback(update["callback_query"])
		else:
			telegram_ombor.on_callback(update["callback_query"])
		return
	msg = update.get("message")
	if not msg or msg.get("chat", {}).get("type") != "private":
		return
	chat_id = str(msg["chat"]["id"])
	text = (msg.get("text") or "").strip()
	if msg.get("contact"):
		on_contact(chat_id, msg)
	elif text.startswith("/start"):
		on_start(chat_id, msg)
	elif text in ("/id", "/myid"):
		# Admin do'kon yaratganda egasining ID'si kerak: egasi botga /id yozib, shu raqamni beradi
		send(chat_id, f"Sizning Telegram ID'ingiz: <code>{chat_id}</code>\n\nShu raqamni platforma administratoriga yuboring.")
	elif telegram_ombor.on_text(chat_id, text):
		pass
	else:
		send(chat_id, "Saytga kirish uchun saytdagi <b>«Telegram orqali tasdiqlash»</b> tugmasini bosing.", reply_markup=CONTACT_KEYBOARD)


def on_start(chat_id, msg):
	name = html.escape(msg.get("from", {}).get("first_name") or "")
	payload = (msg.get("text") or "").partition(" ")[2].strip()
	if payload.startswith("l"):
		on_login_start(chat_id, payload[1:], name)
		return
	if payload.startswith("k") and on_code_start(chat_id, payload[1:], name):
		return
	# Do'konchi — Telegram ID'si do'kon sozlamasida bor (yoki platforma admini): do'koni haqida va buyruqlar.
	# Qolgan hamma (mijoz) — darrov "📱 Raqamni yuborish"
	is_admin = chat_id in admin_ids()
	shops = allowed_shops_for(chat_id, is_admin)
	if shops:
		from marketplace.telegram_ombor import SELLER_KEYBOARD, set_seller_commands

		set_seller_commands(chat_id)
		send(chat_id, seller_greeting(name, chat_id), reply_markup=SELLER_KEYBOARD)
		return
	send(
		chat_id,
		f"Assalomu alaykum{', ' + name if name else ''}! 👋\n\n"
		"Do'kon saytiga kirish uchun saytdagi <b>«Telegram orqali tasdiqlash»</b> tugmasini bosing — "
		"keyin shu yerda bir marta <b>📱 Raqamni yuborish</b> bosasiz.",
		reply_markup=CONTACT_KEYBOARD,
	)


def _login_text(data, phone=None):
	shop_name = frappe.db.get_value("Shop", data.get("shop"), "shop_name") if data.get("shop") else None
	return (
		f"🔐 <b>{html.escape(shop_name or 'Do‘kon')}</b> saytiga kirish\n\n"
		f"Kirish kodi: <b>{data.get('code') or '—'}</b>\n"
		f"Qurilma: {html.escape(data.get('device') or '')}, {data.get('time') or ''}"
		+ (f"\nRaqam: {html.escape(phone_mask(phone))}" if phone else "")
	)


def phone_mask(phone):
	from marketplace.otp import mask_phone

	return mask_phone(phone)


def phone_for_chat(chat_id):
	"""Shu Telegram bog'langan raqam (bir marta "📱 Raqamni yuborish" bosilgan bo'lsa)."""
	return frappe.db.get_value("Telegram Contact", {"chat_id": chat_id, "blocked": 0}, "phone")


def on_login_start(chat_id, login_id, name):
	"""Saytdagi "Telegram orqali tasdiqlash" (start=l<id>), Pont kabi: kod, qurilma va «✅ Ha, kirish» / «❌ Bekor qilish».
	Raqam so'ralmaydi — u Telegram Contact'da bor. Faqat birinchi marta (Telegram hali raqamga bog'lanmagan)
	bir marta "📱 Raqamni yuborish": Telegram botga raqamni faqat odamning o'zi ulashsa beradi."""
	from marketplace import tg_login

	data = tg_login.open_in_chat(login_id, chat_id)
	if not data:
		send(chat_id, "Bu havolaning muddati o'tgan. Saytda «Telegram orqali tasdiqlash» tugmasini qaytadan bosing.", reply_markup=REMOVE_KEYBOARD)
		return
	phone = phone_for_chat(chat_id)
	if phone:
		send(
			chat_id,
			_login_text(data, phone) + "\n\n"
			"«Ha, kirish» tugmasini faqat saytda <b>xuddi shu kodni</b> ko'rsangiz bosing. "
			"Kirishni siz boshlamagan bo'lsangiz — «Bekor qilish» bosing va hech kimga kod yoki havola bermang.",
			reply_markup={"inline_keyboard": [[
				{"text": "✅ Ha, kirish", "callback_data": f"tgl:y:{login_id}"},
				{"text": "❌ Bekor qilish", "callback_data": f"tgl:n:{login_id}"},
			]]},
		)
		return
	send(
		chat_id,
		_login_text(data) + "\n\n"
		f"Assalomu alaykum{', ' + name if name else ''}! Siz birinchi marta kiryapsiz: pastdagi <b>📱 Raqamni yuborish</b> tugmasini "
		"<b>bir marta</b> bosing — keyingi safar faqat «Ha, kirish» bosasiz.\n\n"
		"<i>Saytda boshqa kod ko'rinayotgan bo'lsa yoki kirishni siz boshlamagan bo'lsangiz — hech narsa bosmang.</i>",
		reply_markup=CONTACT_KEYBOARD,
	)


def on_login_callback(cq):
	"""«✅ Ha, kirish» / «❌ Bekor qilish» (callback tgl:y:<id> / tgl:n:<id>): xabar natija bilan almashadi."""
	from marketplace import tg_login

	chat_id = str(cq.get("message", {}).get("chat", {}).get("id") or cq["from"]["id"])
	message_id = cq.get("message", {}).get("message_id")
	_kind, action, login_id = (cq.get("data") or "::").split(":", 2)
	notice, text, markup = "", None, None
	if action == "n":
		data = tg_login.cancel(login_id, chat_id)
		notice = "Bekor qilindi"
		text = (_login_text(data) + "\n\n" if data else "") + "❌ Kirish bekor qilindi."
	else:
		phone = phone_for_chat(chat_id)
		data = phone and tg_login.confirm(login_id, chat_id, phone, cq.get("from") or {})
		if data:
			notice = "Kirish tasdiqlandi"
			text = _login_text(data, phone) + "\n\n✅ Kirish tasdiqlandi — saytga qayting, buyurtmangiz davom etadi."
			markup = return_button(data.get("return_path"))
		else:
			notice = "So'rov eskirgan"
			text = "Bu so'rovning muddati o'tgan. Saytda «Telegram orqali tasdiqlash» tugmasini qaytadan bosing."
	try:
		if message_id and text:
			call("editMessageText", chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
				 **({"reply_markup": markup} if markup else {}))
	finally:
		try:
			call("answerCallbackQuery", callback_query_id=cq["id"], text=notice)
		except TelegramError:
			pass


def on_login_contact(chat_id, phone, contact, sender):
	"""Birinchi marta kirayotgan mijoz raqamini yubordi: shu chat'dagi kirish so'rovi tasdiqlanadi. So'rov bo'lmasa — False."""
	from marketplace import tg_login

	user = {
		**sender,
		"first_name": sender.get("first_name") or contact.get("first_name"),
		"last_name": sender.get("last_name") or contact.get("last_name"),
	}
	data = tg_login.confirm(tg_login.login_for_chat(chat_id), chat_id, phone, user)
	if not data:
		return False
	button = return_button(data.get("return_path"))
	send(chat_id, "✅ Kirish tasdiqlandi — saytga qayting, buyurtmangiz davom etadi.", reply_markup=REMOVE_KEYBOARD)
	if button:
		send(chat_id, "Saytga qaytish uchun pastdagi tugmani bosing.", reply_markup=button)
	return True


CODE_REQUEST_KEY = "mp_tg_code_request:{}"


def on_code_start(chat_id, request, name):
	"""Saytdagi "Telegram'da kodni olish" havolasi (start=k<so'rov>). Raqam shu Telegram'ga avval
	tasdiqlangan bo'lsa — kod darhol. Aks holda bir marta "📱 Raqamni yuborish": bot raqamni faqat
	shu tugma orqali bila oladi, havoladagi raqamga ishonib bo'lmaydi (birov boshqaning raqamini yozishi mumkin)."""
	from marketplace import otp

	row = frappe.db.get_value(
		"OTP Request",
		{"name": request, "channel": "Telegram Bot", "used": 0, "expires_at": [">", frappe.utils.now_datetime()]},
		["name", "phone", "code_hash"],
		as_dict=True,
	)
	if not row:
		send(chat_id, "Bu havolaning muddati o'tgan. Saytda «Kodni olish» tugmasini qaytadan bosing.")
		return True
	if chat_for_phone(row.phone) == chat_id:
		if row.code_hash:
			send(chat_id, "Kod yuqorida yuborilgan ☝️ Uni saytdagi katakchalarga yozing.")
		else:
			otp.deliver_bot_code(row.name, chat_id)
		return True
	frappe.cache.set_value(CODE_REQUEST_KEY.format(chat_id), row.name, expires_in_sec=900)
	send(
		chat_id,
		f"Assalomu alaykum{', ' + name if name else ''}! 👋\n\n"
		f"Saytda <b>{otp.mask_phone(row.phone)}</b> raqami uchun kod so'raldi.\n"
		"Raqam sizniki ekanini tasdiqlash uchun pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing — "
		"kod darhol keladi. Bu faqat birinchi marta, keyingi safar kod o'zi keladi.",
		reply_markup=CONTACT_KEYBOARD,
	)
	return True


def allowed_shops_for(chat_id, is_admin):
	"""{shop: shop_name}: do'konchiga o'z do'kon(lar)i, adminga hammasi, mijozga — bo'sh."""
	if is_admin:
		return dict(frappe.get_all("Shop", fields=["name", "shop_name"], order_by="shop_name", as_list=True))
	return seller_shop_names(chat_id)


def seller_greeting(name, chat_id):
	"""Do'konchi /start bossa: o'z do'koni haqida (sayt, ombordagi qoldiq), bugungi buyurtmalar va buyruqlar.
	Platforma admini — barcha do'konlar bo'yicha ham (admin o'zi do'konchi bo'lsa, avval o'z do'koni)."""
	from frappe.utils import getdate, today

	from marketplace.stock_page import shop_products

	esc = html.escape
	day = getdate(today())
	lines = [f"Assalomu alaykum{', ' + name if name else ''}! 👋"]
	for shop, shop_name in seller_shop_names(chat_id).items():
		products = shop_products(shop)["products"]
		low = sum(1 for p in products if p["status"] or p["low_variants"])
		lines += ["", f"🏪 <b>{esc(shop_name)}</b> — {site_url()}/s/{shop}"]
		lines.append(
			f"📦 Omborda: <b>{cint(sum(p['available'] for p in products))}</b> dona · {len(products)} ta tovar"
			+ (f" · ⚠️ {low} tasi kam/tugagan" if low else "")
		)
		lines += _day_lines(shop, day)
	if chat_id in admin_ids():
		lines += ["", f"🛠 Barcha do'konlar: <b>{frappe.db.count('Shop')}</b> ta"]
		lines += _day_lines(None, day)
	lines += [
		"",
		"Buyruqlar (pastdagi tugmalar):",
		"📦 <b>Ombor</b> — tovarlar qoldig'i",
		"⚠️ <b>Kam qolganlar</b> — tugayotgan va tugagan tovarlar",
		"📊 <b>Bugungi sotuvlar</b> — buyurtmalar, tushgan pul, sotilgan tovarlar",
		"Yangi buyurtmalar va \"kam qoldi\" xabarlari shu yerga o'zi keladi.",
	]
	return "\n".join(lines)


def _day_lines(shop, day):
	"""Bugun nechta buyurtma va qancha tushdi (Hisobot bilan bir xil hisob), hali to'lanmagan va topshirilmaganlari.
	shop=None — barcha do'konlar."""
	from marketplace import reports
	from marketplace.storefront import fmt_sum

	s = reports._summary(shop, day, day)
	# Do'kon ko'radigan buyurtmalar: mijoz tasdiqlaganlari (mp_placed)
	filters = {"docstatus": 1, "mp_placed": 1, **({"shop": shop} if shop else {})}
	waiting = frappe.db.count("Sales Order", {**filters, "payment_status": "Kutilmoqda"})
	undelivered = frappe.db.count("Sales Order", {**filters, "payment_status": ["!=", "Bekor"], "per_delivered": ["<", 100]})
	return [
		f"📅 Bugun: <b>{s['orders']}</b> ta buyurtma · {fmt_sum(s['revenue'])} tushdi",
		f"⏳ To'lov kutilmoqda: <b>{waiting}</b> · 🚚 Hali topshirilmagan: <b>{undelivered}</b>",
	]


def today_sales(chat_id):
	"""📊 Bugungi sotuvlar: buyurtmalar, kassaga tushgan pul (Payme / Click / Naqd) va sotilgan tovarlar —
	do'konchining o'z do'kon(lar)i bo'yicha, admin uchun barcha do'konlar bo'yicha ham. Hisob Hisobot bilan bir xil."""
	from frappe.utils import formatdate, getdate, today

	from marketplace import reports
	from marketplace.storefront import fmt_sum

	esc = html.escape
	day = getdate(today())
	targets = list(seller_shop_names(chat_id).items()) + ([(None, "Barcha do‘konlar")] if chat_id in admin_ids() else [])
	lines = [f"📊 <b>Bugungi sotuvlar</b> — {formatdate(day, 'dd.MM.yyyy')}"]
	for shop, shop_name in targets:
		s = reports._summary(shop, day, day)
		lines += ["", f"🏪 <b>{esc(shop_name)}</b>"]
		lines.append(
			f"🧾 Buyurtmalar: <b>{s['orders']}</b> ta (to'langan {s['paid']}, kutilmoqda {s['pending']}, bekor {s['cancelled']})"
		)
		lines.append(f"💰 Kassaga tushdi: <b>{fmt_sum(s['revenue'])}</b>")
		paid = [f"{p['method']}: {fmt_sum(p['paid_amount'])}" for p in reports._payment_methods(shop, day, day) if p["paid_amount"]]
		if paid:
			lines.append("      " + " · ".join(paid))
		if s["pending_amount"]:
			lines.append(f"⏳ To'lanishi kutilmoqda: {fmt_sum(s['pending_amount'])}")
		sold = [p for p in reports._top_products(shop, day, day)["by_qty"] if p["qty"]]
		if sold:
			lines.append("🛍 Sotilgan tovarlar:")
			lines += [f"  • {esc(p['item_name'])} — {cint(p['qty'])} ta, {fmt_sum(p['amount'])}" for p in sold]
		elif not s["orders"]:
			lines.append("Bugun hali buyurtma bo'lmadi")
	return "\n".join(lines)


def on_contact(chat_id, msg):
	from marketplace import otp

	contact = msg["contact"]
	# Faqat o'z raqami: boshqa odamning kontaktini ulashib, uning nomidan kod olib bo'lmaydi
	if str(contact.get("user_id") or "") != str(msg["from"]["id"]):
		send(chat_id, "Iltimos, <b>o'zingizning</b> raqamingizni pastdagi tugma orqali yuboring.", reply_markup=CONTACT_KEYBOARD)
		return
	try:
		phone = otp.normalize_phone(contact.get("phone_number"))
	except frappe.ValidationError:
		frappe.clear_last_message()
		send(chat_id, "Hozircha faqat O'zbekiston raqamlari (+998) qo'llab-quvvatlanadi.", reply_markup=REMOVE_KEYBOARD)
		return

	full_name = " ".join(x for x in (contact.get("first_name"), contact.get("last_name")) if x)
	link_contact(phone, chat_id, full_name)
	if on_login_contact(chat_id, phone, contact, msg.get("from") or {}):
		return

	# Saytda boshqa raqam yozilgan bo'lsa — kod u raqamga emas: mijozga aniq aytamiz
	asked = frappe.cache.get_value(CODE_REQUEST_KEY.format(chat_id))
	asked_phone = asked and frappe.db.get_value("OTP Request", asked, "phone")
	if asked_phone and asked_phone != phone:
		send(
			chat_id,
			f"Saytda <b>{otp.mask_phone(asked_phone)}</b> yozilgan, Telegram'ingiz esa <b>{otp.mask_phone(phone)}</b> raqamida.\n\n"
			"Saytda Telegram'ingizdagi raqamni yozib, kodni qaytadan so'rang.",
			reply_markup=REMOVE_KEYBOARD,
		)
		return

	# Eski usul (saytda kod so'ralgan, hali yuborilmagan) — kod; aks holda raqam shunchaki saqlanadi
	name = otp.pending_bot_request(phone)
	if name:
		otp.deliver_bot_code(name, chat_id)
	else:
		send(
			chat_id,
			"Raqamingiz saqlandi ✅\n\nDo'kon saytiga kirish uchun saytdagi <b>«Telegram orqali tasdiqlash»</b> tugmasini bosing.",
			reply_markup=REMOVE_KEYBOARD,
		)


def link_contact(phone, chat_id, full_name=None):
	if frappe.db.exists("Telegram Contact", phone):
		frappe.db.set_value("Telegram Contact", phone, {"chat_id": chat_id, "full_name": full_name, "blocked": 0})
	else:
		frappe.get_doc(
			{"doctype": "Telegram Contact", "phone": phone, "chat_id": chat_id, "full_name": full_name}
		).insert(ignore_permissions=True)
	# Bitta Telegram akkaunt bitta raqamga: eski bog'lanishlar o'chadi
	for old in frappe.get_all("Telegram Contact", filters={"chat_id": chat_id, "phone": ["!=", phone]}, pluck="name"):
		frappe.delete_doc("Telegram Contact", old, ignore_permissions=True, force=True)


def return_button(path):
	"""Kod xabari tagidagi "Saytga qaytish". Lokal manzilni (127.0.0.1) Telegram tugmaga qabul qilmaydi."""
	url = f"{site_url()}{path}" if path else None
	if not url or not url.startswith("https://"):
		return None
	return {"inline_keyboard": [[{"text": "↩️ Saytga qaytish", "url": url}]]}


def chat_for_phone(phone):
	row = frappe.db.get_value("Telegram Contact", phone, ["chat_id", "blocked"], as_dict=True)
	return row.chat_id if row and not row.blocked else None


def mark_blocked(phone):
	frappe.db.set_value("Telegram Contact", phone, "blocked", 1)


# ---------- Do'konchilarga buyurtma xabari ----------


def _ids(value):
	return [x.strip() for x in (value or "").replace("\n", ",").split(",") if x.strip()]


def admin_ids():
	return _ids(settings().telegram_admin_id)


def seller_shop_names(chat_id):
	"""{shop: shop_name} — shu Telegram ID qaysi do'konlarga biriktirilgan."""
	return {
		s.name: s.shop_name
		for s in frappe.get_all(
			"Shop", filters={"telegram_ids": ["like", f"%{chat_id}%"]}, fields=["name", "shop_name", "telegram_ids"]
		)
		if chat_id in _ids(s.telegram_ids)
	}


def send_to_shop(shop, text, with_admin=True, **params):
	"""Do'kon egasi(lari)ga (Shop.telegram_ids) va xohlansa platforma adminiga xabar."""
	ids = _ids(frappe.db.get_value("Shop", shop, "telegram_ids")) + (admin_ids() if with_admin else [])
	for chat_id in dict.fromkeys(ids):
		try:
			send(chat_id, text, **params)
		except TelegramError as e:
			frappe.log_error(f"Telegram: {chat_id} ga yuborilmadi: {e}", "Telegram bot")


def notify_new_order(order):
	"""Navbatdan (worker) chaqiriladi: buyurtma ma'lumoti bilan xabar + "Buyurtmani ko'rish" tugmasi."""
	if not token():
		return
	so = frappe.get_doc("Sales Order", order)
	shop = frappe.db.get_value("Shop", so.shop, ["shop_name", "telegram_ids"], as_dict=True)
	if not shop:
		return
	text = order_text(so, shop.shop_name)
	button = {"inline_keyboard": [[{"text": "📦 Buyurtmani ko'rish", "url": f"{site_url()}/desk/sales-order/{so.name}"}]]}
	for chat_id in dict.fromkeys(_ids(shop.telegram_ids) + admin_ids()):
		try:
			send(chat_id, text, reply_markup=button)
		except TelegramError as e:
			if e.code == 400 and ("button" in str(e).lower() or "url" in str(e).lower()):
				# Lokal manzil (127.0.0.1) tugmaga qabul qilinmaydi: havolani matnda beramiz
				try:
					send(chat_id, f"{text}\n\n{site_url()}/desk/sales-order/{so.name}")
				except TelegramError as e2:
					frappe.log_error(f"Telegram: {chat_id} ga yuborilmadi: {e2}", "Telegram bot")
			else:
				frappe.log_error(f"Telegram: {chat_id} ga yuborilmadi: {e}", "Telegram bot")


def order_text(so, shop_name):
	from marketplace.storefront import fmt_sum

	esc = html.escape
	lines = [f"🛒 <b>Yangi buyurtma</b> · {esc(shop_name)}", f"<code>{esc(so.name)}</code>", ""]
	lines.append(f"👤 {esc(so.customer_name or '')}" + (f", {esc(so.customer_phone)}" if so.get("customer_phone") else ""))
	lines.append("")
	for i in so.items:
		lines.append(f"• {esc(i.item_name)} × {cint(i.qty)} — {fmt_sum(i.amount)}")
	lines.append("")
	lines.append(f"💰 Jami: <b>{fmt_sum(so.grand_total)}</b>")
	pay = {"Naqd": "naqd (topshirishda)", "Payme": "Payme", "Click": "Click"}.get(so.get("payment_method"), "hali tanlanmagan")
	if so.get("payment_status") == "To'langan":
		pay = f"✅ to'langan ({so.payment_method})" if so.get("payment_method") else "✅ to'langan"
	lines.append(f"💳 To'lov: {pay}")
	if so.get("delivery_method"):
		addr = f" — {esc(so.delivery_address)}" if so.get("delivery_address") else ""
		if so.delivery_method == "O'zim olaman":
			addr = " — mijoz do'kondan o'zi olib ketadi"
		lines.append(f"🚚 {esc(so.delivery_method)}{addr}")
	return "\n".join(lines)


def enqueue_order_notification(doc, method=None):
	"""Sales Order on_submit: Telegram'ga yuborish navbatga qo'yiladi — mijoz buyurtmasi Telegram'ni kutmaydi."""
	if doc.get("shop"):
		frappe.enqueue(
			"marketplace.telegram_bot.notify_new_order",
			order=doc.name,
			queue="short",
			enqueue_after_commit=True,
			job_id=f"tg-order-{doc.name}",
			deduplicate=True,
		)


# ---------- Sozlamalar saqlanganda ----------


def on_settings_update(doc, method=None):
	"""Token o'zgarsa: getMe bilan tekshiramiz va bot username'ni yozib qo'yamiz."""
	if not doc.has_value_changed("telegram_bot_token") and doc.telegram_bot_username:
		return
	tok = doc.get_password("telegram_bot_token", raise_exception=False)
	if not tok:
		return
	try:
		r = http.get(API.format(token=tok, method="getMe"), timeout=10).json()
	except Exception:
		frappe.msgprint(_("Telegram'ga ulanib bo'lmadi, token keyinroq tekshiriladi"), indicator="orange")
		return
	if not r.get("ok"):
		frappe.throw(_("Bot token noto'g'ri: {0}").format(r.get("description")))
	frappe.db.set_single_value("Marketplace Settings", "telegram_bot_username", r["result"]["username"])
	frappe.msgprint(_("Bot ulandi: @{0}").format(r["result"]["username"]), indicator="green", alert=True)


@frappe.whitelist()
def send_test(chat_id):
	"""Sozlamalardagi "Sinov xabari": admin ID ga xabar yetib borishini tekshirish."""
	frappe.only_for(("System Manager", "Marketplace Manager"))
	send(chat_id, "✅ Bot ishlayapti. Yangi buyurtmalar shu yerga keladi.")
	return True
