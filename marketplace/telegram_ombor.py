"""Telegram botdagi Ombor: do'kon egasi telefondan qoldiqni ko'radi (faqat ko'rish).

📦 Ombor -> tovarlar ro'yxati (soni bilan) -> tovar -> variantlar (Qora · M — 5 ta).
Kirim botda qilinmaydi: unga kimdan olingani va necha puldan olingani kerak, shuning uchun u faqat
Desk'dagi tovar formasida (Ombor tabi). Aks holda oylik chiqim (reports.get_month_summary) noto'g'ri chiqadi.

Kim nimani ko'radi: Shop.telegram_ids'dagi ID — faqat o'sha do'konni, Marketplace Settings'dagi admin ID —
barcha do'konlarni (avval do'kon tanlanadi). Har bir tugma bosilganda tovar shu ID'ning do'koniga
tegishli ekani qayta tekshiriladi.

Telegram callback_data 64 baytdan oshmasligi kerak, tovar kodi esa uzun bo'lishi mumkin
("nafis-tekstil-kuzgi-kurtka-oq-42"). Shuning uchun tugmada qisqa kalit, kodning o'zi keshda.
"""

import hashlib
import html

import frappe
from frappe.utils import cint

from marketplace import telegram_bot as bot

PAGE_SIZE = 8
MAX_VARIANT_LINES = 60  # Telegram xabari 4096 belgidan oshmasin
KIRIM_HINT = "➕ Kirim: Desk → Tovarlar → tovarni oching → <b>Ombor</b> tabi (kimdan olindi, nechta, necha puldan)"

BTN_OMBOR = "📦 Ombor"
BTN_LOW = "⚠️ Kam qolganlar"
BTN_TODAY = "📊 Bugungi sotuvlar"
OLD_BTN_TODAY = "📊 Bugungi holat"  # do'konchilar telefonida qolgan eski klaviatura
SELLER_KEYBOARD = {
	"keyboard": [[{"text": BTN_OMBOR}, {"text": BTN_LOW}], [{"text": BTN_TODAY}]],
	"resize_keyboard": True,
	"is_persistent": True,
}
# Telegram'dagi "Menu" tugmasi — faqat do'konchi chatida (mijozlar ko'rmaydi)
SELLER_COMMANDS = [
	{"command": "start", "description": "Do'konim haqida"},
	{"command": "ombor", "description": "Ombordagi qoldiqlar"},
	{"command": "kam", "description": "Kam qolgan va tugagan tovarlar"},
	{"command": "bugun", "description": "Bugungi sotuvlar"},
]

esc = html.escape


# ---------- Qisqa kalitlar va ruxsat ----------


def _key(value):
	key = hashlib.sha1(value.encode()).hexdigest()[:10]
	frappe.cache.set_value(f"mp_tg_key:{key}", value, expires_in_sec=30 * 24 * 3600)
	return key


def _value(key):
	return frappe.cache.get_value(f"mp_tg_key:{key}")


def allowed_shops(chat_id):
	"""{shop: shop_name}: egasiga o'z do'koni, adminga hammasi."""
	return bot.allowed_shops_for(chat_id, chat_id in bot.admin_ids())


def set_seller_commands(chat_id):
	"""Do'konchi chatidagi "Menu": /ombor, /kam, /bugun. Telegram javob bermasa ham /start ishlayveradi."""
	try:
		bot.call("setMyCommands", commands=SELLER_COMMANDS, scope={"type": "chat", "chat_id": int(chat_id)})
	except (bot.TelegramError, ValueError):
		pass


def _qty(n):
	return f"{cint(n)}"


def _mark(status):
	return {"Tugagan": "❌ ", "Kam qolgan": "⚠️ "}.get(status or "", "")


# ---------- Kirish: matnli tugmalar va son yozish ----------


def on_text(chat_id, text):
	"""Do'konchining matnli xabari (tugma yoki /buyruq). True — xabar shu yerda qayta ishlandi.
	Do'konchi boshqa narsa yozsa ham unga mijozning "📱 Raqamni yuborish" tugmasi emas, o'z buyruqlari chiqadi."""
	shops = allowed_shops(chat_id)
	if not shops:
		return False
	command = text.split("@")[0]  # guruhlardagi "/ombor@bot_nomi"
	if text == BTN_OMBOR or command == "/ombor":
		_shop_entry(chat_id, shops, only_low=False)
	elif text == BTN_LOW or command == "/kam":
		_shop_entry(chat_id, shops, only_low=True)
	elif text in (BTN_TODAY, OLD_BTN_TODAY) or command == "/bugun":
		bot.send(chat_id, bot.today_sales(chat_id), reply_markup=SELLER_KEYBOARD)
	else:
		bot.send(chat_id, "Pastdagi tugmalardan birini tanlang: 📦 Ombor, ⚠️ Kam qolganlar yoki 📊 Bugungi sotuvlar.", reply_markup=SELLER_KEYBOARD)
	return True


def _shop_entry(chat_id, shops, only_low):
	if len(shops) == 1:
		text, markup = product_list(next(iter(shops)), 0, only_low)
	else:
		text = "🏪 Qaysi do'kon ombori?"
		markup = {
			"inline_keyboard": [
				[{"text": name, "callback_data": f"p:{_key(shop)}:0:{int(only_low)}"}] for shop, name in shops.items()
			]
		}
	bot.send(chat_id, text, reply_markup=markup)


# ---------- Tugmalar (callback_query) ----------


def on_callback(cq):
	chat_id = str(cq.get("message", {}).get("chat", {}).get("id") or cq["from"]["id"])
	message_id = cq.get("message", {}).get("message_id")
	data = (cq.get("data") or "").split(":")
	notice = None
	try:
		shops = allowed_shops(chat_id)
		if not shops:
			notice = "Bu bo'lim faqat do'kon egasi uchun"
			return
		kind = data[0]
		if kind == "p":  # p:<shop>:<sahifa>:<faqat kam>
			shop = _value(data[1])
			if shop not in shops:
				notice = "Eskirgan tugma. 📦 Ombor'ni qayta oching"
				return
			_edit(chat_id, message_id, *product_list(shop, cint(data[2]), cint(data[3])))
		elif kind == "i":  # i:<tovar>:<sahifa>
			code = _owned(data[1], shops)
			_edit(chat_id, message_id, *item_card(code, cint(data[2]) if len(data) > 2 else 0))
		elif kind in ("a", "t", "x"):  # eski xabarlardagi "+N" / "Boshqa son" / "Hammasiga qo'shish" tugmalari
			notice = "Kirim endi faqat Desk'dagi tovar formasida: kimdan olindi va necha puldan"
	except PermissionError as e:
		notice = str(e)
	finally:
		try:
			bot.call("answerCallbackQuery", callback_query_id=cq["id"], text=notice or "")
		except bot.TelegramError:
			pass


def _owned(key, shops):
	code = _value(key)
	if not code or frappe.db.get_value("Item", code, "shop") not in shops:
		raise PermissionError("Eskirgan tugma. 📦 Ombor'ni qayta oching")
	return code


def _edit(chat_id, message_id, text, markup):
	try:
		bot.call(
			"editMessageText", chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
			reply_markup=markup, disable_web_page_preview=True,
		)
	except bot.TelegramError as e:
		if "not modified" not in str(e):
			bot.send(chat_id, text, reply_markup=markup)


# ---------- Ekranlar ----------


def product_list(shop, page=0, only_low=False):
	from marketplace.stock_page import shop_products

	data = shop_products(shop)
	products = data["products"]
	shop_name = frappe.db.get_value("Shop", shop, "shop_name")
	low = [p for p in products if p["status"] or p["low_variants"]]
	total_qty = sum(p["available"] for p in products)
	rows = low if only_low else products
	pages = max((len(rows) - 1) // PAGE_SIZE + 1, 1)
	page = min(max(page, 0), pages - 1)

	lines = [f"📦 <b>{esc(shop_name)}</b> — ombor", f"Tovarlar: <b>{len(products)}</b> · jami <b>{_qty(total_qty)}</b> dona"]
	if low:
		lines.append(f"⚠️ Kam qolgan / tugagan: <b>{len(low)}</b> (chegara: {data['low_stock']} dona)")
	lines.append("")
	if not rows:
		lines.append("Hammasi yetarli ✅" if only_low else "Hali tovar yo'q. Desk'da Tovarlar → yangi tovar qo'shing.")
	else:
		lines.append("Tovarni tanlang:" + (" (faqat kam qolganlar)" if only_low else ""))

	keyboard = []
	for p in rows[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
		mark = _mark(p["status"]) or ("⚠️ " if p["low_variants"] else "")
		label = f"{mark}{p['name']} — {_qty(p['available'])} ta"
		keyboard.append([{"text": label[:60], "callback_data": f"i:{_key(p['code'])}:{page}"}])
	shop_key = _key(shop)
	nav = []
	if page > 0:
		nav.append({"text": "◀️", "callback_data": f"p:{shop_key}:{page - 1}:{int(only_low)}"})
	if pages > 1:
		nav.append({"text": f"{page + 1}/{pages}", "callback_data": f"p:{shop_key}:{page}:{int(only_low)}"})
	if page < pages - 1:
		nav.append({"text": "▶️", "callback_data": f"p:{shop_key}:{page + 1}:{int(only_low)}"})
	if nav:
		keyboard.append(nav)
	keyboard.append(
		[{"text": "📋 Hammasi", "callback_data": f"p:{shop_key}:0:0"}]
		if only_low
		else [{"text": "⚠️ Faqat kam qolganlar", "callback_data": f"p:{shop_key}:0:1"}]
	)
	return "\n".join(lines), {"inline_keyboard": keyboard}


def _product(code):
	from marketplace.stock_page import shop_products

	shop, template = frappe.db.get_value("Item", code, ["shop", "variant_of"])
	base = template or code
	product = next((p for p in shop_products(shop)["products"] if p["code"] == base), None)
	if not product:
		raise PermissionError("Tovar topilmadi yoki sotuvdan olingan")
	return shop, product


def item_card(code, page=0):
	"""Tovar qoldig'i (faqat ko'rish): variantli tovarda har bir variant soni bilan.
	Variant kodi kelsa (eski tugma) — uning andozasi ko'rsatiladi."""
	shop, p = _product(code)
	lines = [
		f"👕 <b>{esc(p['name'])}</b>",
		esc(" · ".join(x for x in (p["category"], f"{_qty(p['price'])} so'm" if p["price"] else "") if x)),
	]
	if p["is_template"]:
		lines.append(f"Jami: <b>{_qty(p['available'])}</b> dona · {len(p['variants'])} ta variant")
		lines.append("")
		variants = p["variants"]
		lines += [f"{_mark(v['status'])}{esc(v['label'])} — <b>{_qty(v['available'])}</b>" for v in variants[:MAX_VARIANT_LINES]]
		if len(variants) > MAX_VARIANT_LINES:
			lines.append(f"… yana {len(variants) - MAX_VARIANT_LINES} ta variant")
		if not variants:
			lines.append("Hali kirim bo'lmagan")
	else:
		lines.append(f"Omborda: <b>{_qty(p['actual'])}</b> dona" + (f" (zaxirada {_qty(p['reserved'])})" if p["reserved"] else ""))
	lines += ["", KIRIM_HINT]
	keyboard = [[{"text": "⬅️ Ro'yxatga", "callback_data": f"p:{_key(shop)}:{page}:0"}]]
	return "\n".join(lines), {"inline_keyboard": keyboard}
