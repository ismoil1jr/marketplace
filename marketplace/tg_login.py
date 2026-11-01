"""Saytga Telegram orqali kirish (Pont kabi): saytda kod, botda o'sha kod va «✅ Ha, kirish» tugmasi.
Mijoz hech narsa yozmaydi: telefon raqami Telegram Contact'dan, ism va familiya Telegram profilidan olinadi.

1. Sayt (api.telegram_login) -> start(): tasodifiy id (bot havolasida, t.me/<bot>?start=l<id>), secret (faqat shu
   brauzerda) va 4 xonali kirish kodi. Redis'da 10 daqiqa: {holat, secret xeshi, kod, qurilma, do'kon, qaytish sahifasi}.
2. Bot: /start l<id> -> "🔐 Saytga kirish, kod 6078, Firefox · Linux, 18:19" va «✅ Ha, kirish» / «❌ Bekor qilish»
   (telegram_bot.on_login_start). So'rov birinchi ochilgan chat'ga bog'lanadi — havolani boshqa odam ochsa ishlamaydi.
   Telegram botga raqamni faqat odam o'zi ulashsa beradi: shu Telegram hali raqamga bog'lanmagan bo'lsa (birinchi
   marta), bot bir marta "📱 Raqamni yuborish" so'raydi — keyingi safar faqat «Ha, kirish».
3. Sayt har 2 soniyada status(id, secret): tasdiqlangan bo'lsa Customer topiladi/yaratiladi va sessiya ochiladi.
   So'rov bir martalik: o'qilgach o'chadi.

Ism: do'kon mijozni "Doimiy mijoz" qilib ismini yozgan bo'lsa — o'sha qoladi (customers.get_or_create_customer).
"""

import hashlib
import hmac
import re
import secrets

import frappe
from frappe import _
from frappe.utils import now_datetime

TTL = 600
KEY = "mp_tg_login:{}"
CHAT_KEY = "mp_tg_login_chat:{}"


def _hash(secret):
	return hashlib.sha256((secret or "").encode()).hexdigest()


def device_label(user_agent):
	"""'Mozilla/5.0 (X11; Linux x86_64; rv:157.0) ... Firefox/157.0' -> 'Firefox · Linux' (botdagi "Qurilma")."""
	ua = user_agent or ""
	browser = next(
		(name for pattern, name in (
			(r"YaBrowser", "Yandex Browser"), (r"Edg/", "Edge"), (r"OPR/|Opera", "Opera"), (r"Firefox/", "Firefox"),
			(r"Chrome/", "Chrome"), (r"Safari/", "Safari"),
		) if re.search(pattern, ua)),
		"Brauzer",
	)
	system = next(
		(name for pattern, name in (
			(r"Android", "Android"), (r"iPhone", "iPhone"), (r"iPad", "iPad"), (r"Windows", "Windows"),
			(r"Mac OS X|Macintosh", "Mac"), (r"Linux", "Linux"),
		) if re.search(pattern, ua)),
		"",
	)
	return f"{browser} · {system}" if system else browser


def clean_name(value):
	"""Telegram ismidagi ko'rinmas belgilar (\\u2060 va b.) olib tashlanadi: '\\u2060 \\u2060' -> ''."""
	return " ".join("".join(ch for ch in (value or "") if ch.isprintable()).split())


def start(shop, return_path=None):
	from marketplace import telegram_bot

	login_id = secrets.token_urlsafe(12)
	secret = secrets.token_urlsafe(24)
	code = str(1000 + secrets.randbelow(9000))
	link = telegram_bot.bot_link(start=f"l{login_id}")
	if not link:
		frappe.log_error("Telegram bot sozlanmagan (username yo'q)", "Marketplace Telegram kirish")
		frappe.throw(_("Telegram orqali kirish hozircha ishlamayapti. Birozdan keyin urinib ko‘ring."))
	_save(login_id, {
		"status": "pending",
		"secret": _hash(secret),
		"code": code,
		"device": device_label(frappe.get_request_header("User-Agent")),
		"time": now_datetime().strftime("%H:%M"),
		"shop": shop,
		"return_path": return_path if (return_path or "").startswith("/s/") else None,
	})
	return {"id": login_id, "secret": secret, "link": link, "ttl": TTL, "code": code}


def get(login_id):
	return frappe.cache.get_value(KEY.format(login_id)) if login_id else None


def _save(login_id, data):
	frappe.cache.set_value(KEY.format(login_id), data, expires_in_sec=TTL)


def open_in_chat(login_id, chat_id):
	"""Bot: /start l<id>. So'rov birinchi ochgan chat'ga bog'lanadi; boshqa chat yoki eskirgan bo'lsa — None."""
	data = get(login_id)
	if not data or data["status"] != "pending" or data.get("chat") not in (None, chat_id):
		return None
	data["chat"] = chat_id
	_save(login_id, data)
	# Birinchi marta kirayotgan mijoz raqamini yuborganda qaysi so'rovga yozishni bilish uchun
	frappe.cache.set_value(CHAT_KEY.format(chat_id), login_id, expires_in_sec=TTL)
	return data


def login_for_chat(chat_id):
	return frappe.cache.get_value(CHAT_KEY.format(chat_id))


def confirm(login_id, chat_id, phone, user):
	"""Bot: «Ha, kirish» bosildi (yoki birinchi marta raqam yuborildi). user — Telegram profili
	{id, first_name, last_name, username}. So'rov shu chat'niki bo'lmasa — None."""
	data = get(login_id)
	if not data or data["status"] != "pending" or data.get("chat") != chat_id:
		return None
	data.update(
		status="confirmed", phone=phone, telegram_id=str(user.get("id") or chat_id), username=user.get("username") or "",
		first_name=clean_name(user.get("first_name")), last_name=clean_name(user.get("last_name")),
	)
	_save(login_id, data)
	frappe.cache.delete_value(CHAT_KEY.format(chat_id))
	return data


def cancel(login_id, chat_id):
	"""Bot: «Bekor qilish» — sayt "Kirish bekor qilindi" deydi."""
	data = get(login_id)
	if not data or data["status"] != "pending" or data.get("chat") != chat_id:
		return None
	data["status"] = "cancelled"
	_save(login_id, data)
	frappe.cache.delete_value(CHAT_KEY.format(chat_id))
	return data


def status(login_id, secret):
	"""Sayt: {"status": "pending" | "cancelled" | "expired" | "ok", ...}. ok — sessiya ochildi (cookie javob bilan ketadi)."""
	from marketplace import customers, otp

	data = get(login_id)
	if not data or not hmac.compare_digest(data["secret"], _hash(secret)):
		return {"status": "expired"}
	if data["status"] == "pending":
		return {"status": "pending"}
	frappe.cache.delete_value(KEY.format(login_id))
	if data["status"] != "confirmed":
		return {"status": "cancelled"}
	customer = customers.get_or_create_customer(data["phone"], data["first_name"], data["last_name"], shop=data["shop"])
	customers.start_session(customer, data["phone"])
	remember(data, customer)
	return {
		"status": "ok",
		"name": frappe.db.get_value("Customer", customer, "customer_name"),
		"phone_masked": otp.mask_phone(data["phone"]),
	}


# ---------- Do'kondagi "Telegram mijozlar" ro'yxati ----------
# Saytda ro'yxatdan o'tgan har bir mijoz (Customer.mp_phone) do'kon ro'yxatida: shu do'kon saytiga kirgan yoki
# undan buyurtma bergan bo'lsa. Bitta mijoz — bitta do'konda bitta qator (do'kon + telefon).


def _listed(shop, phone):
	doc_name = frappe.db.get_value("Telegram Mijoz", {"shop": shop or ["is", "not set"], "phone": phone})
	doc = frappe.get_doc("Telegram Mijoz", doc_name) if doc_name else frappe.new_doc("Telegram Mijoz")
	if not doc_name:
		doc.update({"shop": shop, "phone": phone, "first_login": now_datetime(), "login_count": 0})
	return doc


def _save_listed(doc):
	doc.doimiy_mijoz = frappe.db.get_value("Doimiy Mijoz", {"shop": doc.shop, "phone": doc.phone}) if doc.shop else None
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.telegram_id:
		frappe.enqueue(
			"marketplace.tg_login.fetch_photo", name=doc.name, telegram_id=doc.telegram_id,
			queue="short", enqueue_after_commit=True,
		)


def remember(data, customer):
	"""Telegram orqali kirdi: ism, @username, telefon, qachon va necha marta kirgani. Profil rasmi fonda (fetch_photo)."""
	if not data.get("shop"):
		return
	doc = _listed(data["shop"], data["phone"])
	doc.update(
		{
			"telegram_id": data.get("telegram_id") or doc.telegram_id,
			# Telegram ismi bo'sh bo'lishi mumkin (faqat ko'rinmas belgilar) — unda mijozning saytdagi ismi
			"full_name": " ".join(x for x in (data.get("first_name"), data.get("last_name")) if x)
			or frappe.db.get_value("Customer", customer, "customer_name") or data["phone"],
			"username": f"@{data['username']}" if data.get("username") else doc.username,
			"customer": customer,
			"device": data.get("device"),
			"last_login": now_datetime(),
			"login_count": (doc.login_count or 0) + 1,
		}
	)
	_save_listed(doc)


def remember_order(shop, customer):
	"""Kirgan mijoz boshqa do'kondan buyurtma berdi (sessiya hamma do'konga bitta): shu do'kon ro'yxatiga ham."""
	if not frappe.db.exists("Telegram Mijoz", {"shop": shop, "phone": customer.phone}):
		_backfill_one(frappe.db.get_value("Customer", customer.customer, ["name", "customer_name", "mp_phone", "creation"], as_dict=True), shop)


def _backfill_one(c, shop):
	"""Kirish ma'lumoti saqlanmagan mijoz: Customer, uning sessiyalari va (bo'lsa) Telegram Contact'idan."""
	chat = frappe.db.get_value("Telegram Contact", c.mp_phone, ["chat_id", "full_name"], as_dict=True) or frappe._dict()
	sessions = frappe.get_all(
		"Customer Session", filters={"customer": c.name}, fields=["creation", "last_seen", "user_agent"], order_by="creation asc"
	)
	last = sessions[-1] if sessions else None
	doc = _listed(shop, c.mp_phone)
	doc.update(
		{
			"telegram_id": chat.chat_id,
			"full_name": clean_name(chat.full_name) or c.customer_name,
			"customer": c.name,
			"first_login": c.creation,
			"last_login": (last and (last.last_seen or last.creation)) or c.creation,
			"login_count": max(len(sessions), 1),
			"device": device_label(last.user_agent) if last and last.user_agent else None,
		}
	)
	_save_listed(doc)


def sync_registered():
	"""Bir marta (patch) va istalgan payt: saytda ro'yxatdan o'tgan barcha mijozlar ro'yxatga. Do'koni — buyurtma
	bergan do'konlari va kirgan sahifasi (OTP so'rovidagi /s/<do'kon>/...); hech biri bo'lmasa — do'konsiz
	(faqat platforma adminiga ko'rinadi). Ro'yxatda bor qatorlarga tegilmaydi. Qaytaradi: nechta qo'shildi."""
	added = 0
	for c in frappe.get_all("Customer", filters={"mp_phone": ["is", "set"]}, fields=["name", "customer_name", "mp_phone", "creation"]):
		shops = set(frappe.get_all("Sales Order", filters={"customer": c.name}, pluck="shop", distinct=True))
		shops |= {
			path.split("/")[2]
			for path in frappe.get_all("OTP Request", filters={"phone": c.mp_phone, "return_path": ["like", "/s/%/%"]}, pluck="return_path")
		}
		shops = {s for s in shops if s and frappe.db.exists("Shop", s)}
		listed = set(frappe.get_all("Telegram Mijoz", filters={"phone": c.mp_phone}, pluck="shop"))
		for shop in shops or ({None} if not listed else set()):
			if shop in listed:
				continue
			_backfill_one(c, shop)
			added += 1
	return added


def fetch_photo(name, telegram_id):
	"""Telegram profil rasmi (Bot API getUserProfilePhotos). Rasm o'zgarmagan bo'lsa qayta yuklanmaydi;
	rasmi yo'q yoki maxfiylik sozlamasi bilan yopgan mijozda — hech narsa qilinmaydi."""
	from marketplace import telegram_bot

	try:
		if not frappe.db.get_value("Telegram Mijoz", name, "username"):
			# Ro'yxatga keyin qo'shilgan (eski) mijoz: @username Telegram'dan
			username = (telegram_bot.call("getChat", chat_id=int(telegram_id)) or {}).get("username")
			if username:
				frappe.db.set_value("Telegram Mijoz", name, "username", f"@{username}", update_modified=False)
		photos = telegram_bot.call("getUserProfilePhotos", user_id=int(telegram_id), limit=1)
		if not photos or not photos.get("total_count"):
			return
		# Ro'yxat uchun o'rta o'lcham yetarli (~320px), eng kattasi kerak emas
		sizes = sorted(photos["photos"][0], key=lambda p: p.get("width", 0))
		size = next((p for p in sizes if p.get("width", 0) >= 300), sizes[-1])
		if frappe.db.get_value("Telegram Mijoz", name, "photo_id") == size["file_unique_id"]:
			return
		path = telegram_bot.call("getFile", file_id=size["file_id"])["file_path"]
		content = telegram_bot.http.get(f"https://api.telegram.org/file/bot{telegram_bot.token()}/{path}", timeout=20).content
	except (telegram_bot.TelegramError, KeyError, ValueError, OSError) as e:
		frappe.log_error(f"Telegram profil rasmi olinmadi ({telegram_id}): {e}", "Marketplace Telegram kirish")
		return
	old = frappe.get_all("File", filters={"attached_to_doctype": "Telegram Mijoz", "attached_to_name": name, "attached_to_field": "photo"}, pluck="name")
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"telegram-{telegram_id}.jpg",
			"attached_to_doctype": "Telegram Mijoz",
			"attached_to_name": name,
			"attached_to_field": "photo",
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value("Telegram Mijoz", name, {"photo": file.file_url, "photo_id": size["file_unique_id"]}, update_modified=False)
	for f in old:
		frappe.delete_doc("File", f, ignore_permissions=True, force=True)

