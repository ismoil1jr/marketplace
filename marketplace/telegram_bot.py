"""Platformaning o'z Telegram boti.

Ikki vazifa:
1. Mijozlarga tasdiqlash kodi. Telegram qoidasi: bot faqat o'zini bir marta ochgan odamga yoza oladi,
   telefon raqami bo'yicha birinchi bo'lib yozolmaydi. Shuning uchun:
   * mijoz saytda raqamini yozadi -> "Telegram'da kodni olish" tugmasi botni ochadi;
   * botda "📱 Raqamni yuborish" bosadi; bot raqam o'ziniki ekanini (contact.user_id == from.id) va
     saytdagi raqamga tengligini tekshiradi, kod yaratib yuboradi;
   * raqam ↔ chat Telegram Contact'da qoladi: keyingi safar kod darhol keladi.
   Kodning o'zi hech qayerda saqlanmaydi: u bot yuborgan paytda yaratiladi, bazaga faqat xeshi yoziladi.
2. Do'konchilarga "Yangi buyurtma" xabari va "Buyurtmani ko'rish" tugmasi. Kimga yuborishni Shop'dagi
   telegram_ids (admin kiritadi) va Marketplace Settings'dagi admin ID belgilaydi.

Telegram bilan aloqa:
* production: webhook — https://<sayt>/api/method/marketplace.telegram_bot.webhook
  (sozlamalarda "Webhook'ni o'rnatish"; so'rov maxfiy kalit sarlavhasi bilan tekshiriladi);
* lokal (127.0.0.1, internetdan ochilmaydi): `bench --site <sayt> execute marketplace.telegram_bot.poll`
  alohida terminalda ishlab turadi.
"""

import html
import json
import secrets
import time

import frappe
import requests
from frappe import _
from frappe.utils import cint, get_url

API = "https://api.telegram.org/bot{token}/{method}"


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
		r = requests.post(API.format(token=tok, method=method), json=params, timeout=http_timeout)
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
			updates = call("getUpdates", http_timeout=40, timeout=30, offset=offset, allowed_updates=["message"])
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
	call("setWebhook", url=url, secret_token=secret, allowed_updates=["message"], drop_pending_updates=True)
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
	msg = update.get("message")
	if not msg or msg.get("chat", {}).get("type") != "private":
		return
	chat_id = str(msg["chat"]["id"])
	if msg.get("contact"):
		on_contact(chat_id, msg)
	elif (msg.get("text") or "").startswith("/start"):
		on_start(chat_id, msg)
	else:
		send(chat_id, "Kod olish uchun pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing.", reply_markup=CONTACT_KEYBOARD)


def on_start(chat_id, msg):
	name = html.escape(msg.get("from", {}).get("first_name") or "")
	shops = seller_shop_names(chat_id)
	is_admin = chat_id in admin_ids()
	if shops or is_admin:
		send(chat_id, seller_greeting(name, shops, is_admin))
		return
	send(
		chat_id,
		f"Assalomu alaykum{', ' + name if name else ''}! 👋\n\n"
		"Tasdiqlash kodini olish uchun pastdagi <b>📱 Raqamni yuborish</b> tugmasini bosing — kod shu yerga keladi.",
		reply_markup=CONTACT_KEYBOARD,
	)


def seller_greeting(name, shops, is_admin):
	"""Sotuvchi /start bossa: bugungi buyurtmalar va e'tibor talab qiladiganlari."""
	from frappe.utils import today

	filters = {"docstatus": 1}
	if not is_admin:
		filters["shop"] = ["in", list(shops)]
	today_count = frappe.db.count("Sales Order", {**filters, "transaction_date": today()})
	waiting = frappe.db.count("Sales Order", {**filters, "payment_status": "Kutilmoqda"})
	undelivered = frappe.db.count(
		"Sales Order", {**filters, "payment_status": ["!=", "Bekor"], "per_delivered": ["<", 100]}
	)
	where = "barcha do'konlar" if is_admin else ", ".join(f"<b>{html.escape(s)}</b>" for s in shops.values())
	lines = [f"Assalomu alaykum{', ' + name if name else ''}! 👋", f"🏪 {where}", ""]
	lines.append(f"📅 Bugun: <b>{today_count}</b> ta buyurtma")
	lines.append(f"⏳ To'lov kutilmoqda: <b>{waiting}</b>")
	lines.append(f"📦 Hali topshirilmagan: <b>{undelivered}</b>")
	lines.append("")
	lines.append("Iltimos, xaridorlarga o'z vaqtida javob bering 🙏" if (waiting or undelivered) else "Hammasi joyida ✅")
	lines.append("Yangi buyurtmalar shu yerga keladi.")
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

	# Saytda kod so'ralgan bo'lsa o'shani, bo'lmasa yangisini yaratib yuboradi
	name = otp.pending_bot_request(phone) or otp.create_bot_request(phone)
	if name:
		otp.deliver_bot_code(name, chat_id)
	else:
		send(chat_id, "Bu raqamga juda ko'p kod so'raldi. Birozdan keyin urinib ko'ring.", reply_markup=REMOVE_KEYBOARD)


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
	lines.append(f"💳 To'lov: {pay}")
	if so.get("delivery_method"):
		addr = f" — {esc(so.delivery_address)}" if so.get("delivery_address") else ""
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
		r = requests.get(API.format(token=tok, method="getMe"), timeout=10).json()
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
