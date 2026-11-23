"""Chegirma soat (avval «chegirma barabani» edi — baraban olib tashlandi, nom ichki qoldi).

Tovar formasida «Chegirma soat qo'shish» yoqilsa (Item.mp_chegirma_soat, soati, narxi): do'konga kirgan yangi mijozga
«Tabriklaymiz! N soatlik chegirma» oynasi chiqadi, tovar chegirma narxida savatga tushadi, taymer yuradi
(public/js/baraban.js). Qolgan vaqt va narx serverda — brauzer cookie'si bo'yicha (Baraban Chegirma)."""

import hashlib

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, now_datetime, time_diff_in_seconds

COOKIE_PREFIX = "mp_baraban_"
MAX_STEP = 20
MAX_SOAT = 99  # taymer HH:MM:SS — ikki xonali soat


def validate_item(doc, method=None):
	"""Item.validate: «Chegirma soat qo'shish» — soat va narx to'g'ri, do'konda faqat bitta tovarda."""
	if not cint(doc.get("mp_chegirma_soat")):
		return
	if doc.get("variant_of"):
		doc.mp_chegirma_soat = 0  # andozada belgilanadi, chegirma hamma rangga o'zi tushadi
		return
	soat = cint(doc.get("mp_chegirma_soati"))
	if not 1 <= soat <= MAX_SOAT:
		frappe.throw(_("Chegirma necha soat: 1 dan {0} gacha yozing").format(MAX_SOAT))
	narx = flt(doc.get("mp_chegirma_narxi"))
	if narx <= 0:
		frappe.throw(_("Chegirma narxini yozing"))
	if not doc.get("shop"):
		frappe.throw(_("Chegirma soat faqat do'kon tovarida bo'ladi"))
	other = frappe.db.get_value(
		"Item",
		{"shop": doc.shop, "mp_chegirma_soat": 1, "name": ["!=", doc.name or ""], "variant_of": ["is", "not set"]},
		["name", "item_name"],
		as_dict=True,
	)
	if other:
		frappe.throw(
			_("Bu do'konda chegirma soat «{0}» tovarida yoqilgan. Avval o'sha tovarda o'chiring — bir vaqtda bitta tovar bo'ladi").format(
				other.item_name or other.name
			)
		)
	oddiy = flt(doc.get("variant_price") if doc.get("has_variants") else doc.get("standard_rate"))
	if oddiy and narx >= oddiy:
		frappe.msgprint(
			_("Chegirma narxi oddiy narxdan ({0} so'm) arzon emas — saytda chegirma ko'rinmaydi").format(f"{oddiy:,.0f}".replace(",", " ")),
			indicator="orange",
			alert=True,
		)


def _cookie_name(shop):
	return COOKIE_PREFIX + hashlib.sha1(str(shop).encode()).hexdigest()[:12]


def _base_config(shop):
	"""Arzon tekshiruv (bitta Item so'rovi). Do'konda chegirma soatli sotuvdagi tovar bo'lmasa None; xato bersa ham None."""
	try:
		rows = frappe.get_all(
			"Item",
			filters={
				"shop": shop, "mp_chegirma_soat": 1, "disabled": 0, "is_published": 1, "mp_tez_kunda": 0,
				"variant_of": ["is", "not set"],
			},
			fields=["name", "item_name", "image", "has_variants", "mp_chegirma_soati", "mp_chegirma_narxi"],
			order_by="modified desc",
			limit=1,
		)
		if not rows:
			return None
		item = rows[0]
		soat, narx = cint(item.mp_chegirma_soati), flt(item.mp_chegirma_narxi)
		if soat <= 0 or narx <= 0:
			return None
		return frappe._dict(
			tovar=item.name, narx=narx, soat=min(soat, MAX_SOAT), tovar_nomi=item.item_name, rasm=item.image,
			has_variants=cint(item.has_variants),
		)
	except Exception:
		frappe.log_error(title="Chegirma soat: config", message=frappe.get_traceback())
		return None


def enabled(shop):
	"""Do'konda chegirma soat yoqilganmi — sahifa baraban.js/css ni yuklashi uchun (get_shop). Hech qachon xato bermaydi."""
	try:
		return bool(frappe.db.exists(
			"Item",
			{"shop": shop, "mp_chegirma_soat": 1, "disabled": 0, "is_published": 1, "mp_tez_kunda": 0,
			 "variant_of": ["is", "not set"]},
		))
	except Exception:
		return False


def config(shop):
	"""To'liq config (state uchun): base + eski narx. Hech qachon xato bermaydi."""
	try:
		cfg = _base_config(shop)
		if not cfg:
			return None
		from marketplace.storefront import _get_prices, _get_stock, variant_labels

		# Variantli tovar (masalan, Panda books: Ko'k/Sariq/Yashil): chegirma har bir variantga; savatga qoldig'i
		# bor birinchi variant qo'shiladi (shablonning o'zi savatga tushmaydi)
		cfg.kodlar, cfg.qoshish, cfg.qoshish_nomi = [cfg.tovar], cfg.tovar, None
		if cfg.has_variants:
			rows = frappe.get_all(
				"Item",
				filters={"variant_of": cfg.tovar, "disabled": 0, "is_published": 1},
				fields=["name", "is_stock_item"],
				order_by="name asc",
			)
			if not rows:
				return None
			codes = [r.name for r in rows]
			stock = _get_stock(codes, frappe.db.get_value("Shop", shop, "warehouse"))
			bor = [r.name for r in rows if not cint(r.is_stock_item) or stock.get(r.name, 0) > 0]
			cfg.kodlar += codes
			cfg.qoshish = (bor or codes)[0]
			cfg.qoshish_nomi = variant_labels([cfg.qoshish]).get(cfg.qoshish)
		narxlar = _get_prices(cfg.kodlar)
		cfg.qoshish_narx = flt(narxlar.get(cfg.qoshish))  # muddat tugagach yon savatda oddiy narx ko'rinsin
		eski = max([flt(v) for v in narxlar.values()] or [0])
		cfg.eski_narx = eski if eski > cfg.narx else None
		return cfg
	except Exception:
		frappe.log_error(title="Chegirma soat: config", message=frappe.get_traceback())
		return None


def _row(shop):
	token = getattr(frappe.request, "cookies", None) and frappe.request.cookies.get(_cookie_name(shop))
	if not token:
		return None
	row = frappe.db.get_value(
		"Baraban Chegirma",
		{"token": token},
		["name", "shop", "soat", "qolgan_soniya", "oxirgi_signal"],
		as_dict=True,
	)
	if not row or row.shop != shop:
		return None
	return row


def _live_shop(shop):
	"""Faol do'kon nomi yoki None — har 15 soniyadagi tick uchun arzon (get_shop banner va boshqalarni ham yuklaydi)."""
	return frappe.db.get_value("Shop", {"name": shop, "status": "Active"}, "name") if shop else None


def _state(shop, cfg, row, claimed=False):
	return {
		"enabled": True,
		"claimed": claimed or bool(row),
		"soat": cfg.soat,
		"remaining": max(0, cint(row.qolgan_soniya)) if row else 0,
		"price": cfg.narx,
		"old_price": cfg.eski_narx,
		"product": {
			"code": cfg.tovar,
			"name": cfg.tovar_nomi,
			"thumb": cfg.rasm,
			"codes": cfg.kodlar,
			"add": cfg.qoshish,
			"variant": cfg.qoshish_nomi,
			"add_price": cfg.get("qoshish_narx") or 0,
		},
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def state(shop):
	shop = _live_shop(shop)
	cfg = shop and config(shop)
	if not cfg:
		return {"enabled": False}
	return _state(shop, cfg, _row(shop))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=100, seconds=600)  # bir IP ortida ko'p mijoz (mobil operator, ofis Wi-Fi)
def start(shop):
	"""Yangi mijoz do'konga kirdi: chegirma taymeri boshlanadi (brauzerda bir marta — cookie)."""
	shop = _live_shop(shop)
	cfg = shop and config(shop)
	if not cfg:
		return {"enabled": False}
	row = _row(shop)
	if row:
		return _state(shop, cfg, row)
	token = frappe.generate_hash(length=32)
	now = now_datetime()
	frappe.get_doc(
		{
			"doctype": "Baraban Chegirma",
			"shop": shop,
			"token": token,
			"soat": cfg.soat,
			"qolgan_soniya": cfg.soat * 3600,
			"oxirgi_signal": now,
		}
	).insert(ignore_permissions=True)
	frappe.local.cookie_manager.set_cookie(
		_cookie_name(shop), token, max_age=30 * 86400, httponly=True, samesite="Lax"
	)
	return _state(shop, cfg, frappe._dict(qolgan_soniya=cfg.soat * 3600), claimed=True)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=300, seconds=60)
def tick(shop, resume=0):
	"""Mijoz saytda: qolgan vaqtni kamaytiradi. resume=1 — mijoz qaytdi: faqat hisobni shu daqiqadan boshlaydi
	(yo'q bo'lgan vaqt hisoblanmaydi; ketishda yuborilgan tick oxirgi soniyalarni allaqachon yozgan)."""
	shop = _live_shop(shop)
	row = shop and _row(shop)
	if not row:
		return {"remaining": 0}
	remaining = max(0, cint(row.qolgan_soniya))
	if remaining > 0:
		now = now_datetime()
		gap = time_diff_in_seconds(now, row.oxirgi_signal) if row.oxirgi_signal and not cint(resume) else 0
		remaining = max(0, remaining - int(min(max(0, gap), MAX_STEP)))
		frappe.db.set_value(
			"Baraban Chegirma",
			row.name,
			{"qolgan_soniya": remaining, "oxirgi_signal": now},
			update_modified=False,
		)
	return {"remaining": remaining}


def active(shop):
	"""(tovar, narx) agar chegirma taymeri hali amal qilsa, aks holda None. Hech qachon xato bermaydi."""
	try:
		row = _row(shop)
		if not row or cint(row.qolgan_soniya) <= 0:
			return None
		cfg = _base_config(shop)
		if cfg:
			return (cfg.tovar, cfg.narx)  # storefront: tovarning o'zi yoki uning varianti
	except Exception:
		frappe.log_error(title="Chegirma soat: active xatosi")
	return None


def cleanup():
	"""Kunlik: cookie (30 kun) muddati o'tgan qatorlarni o'chiradi. Ertaroq o'chirilsa, qaytgan mijozga «Tabriklaymiz»
	oynasi qayta chiqib, yangi chegirma olardi (tick modified'ni yangilamaydi — shuning uchun creation bo'yicha)."""
	frappe.db.delete("Baraban Chegirma", {"creation": ["<", add_days(now_datetime(), -31)]})
