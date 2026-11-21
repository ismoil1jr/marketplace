"""Chegirma barabani: do'kon sozlamalarini tekshirish va yordamchilar."""

import hashlib

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, now_datetime, time_diff_in_seconds

COOKIE_PREFIX = "mp_baraban_"
MAX_STEP = 20


def variants(text):
	"""«1, 2,3» -> [1, 2, 3]: tartib saqlanadi, takror, raqam bo'lmagan va <= 0 tashlanadi."""
	out = []
	for part in str(text or "").split(","):
		part = part.strip()
		if not part.isdigit():
			continue
		n = int(part)
		if n > 0 and n not in out:
			out.append(n)
	return out


def validate_shop(doc, method=None):
	if not doc.get("baraban_yoqilgan"):
		return
	tovar = doc.get("baraban_tovar")
	if not tovar or frappe.db.get_value("Item", tovar, "shop") != doc.name:
		frappe.throw(_("Baraban tovari shu do'konning tovari bo'lishi kerak"))
	if (doc.get("baraban_narx") or 0) <= 0:
		frappe.throw(_("Chegirma narxi noldan katta bo'lishi kerak"))
	vs = variants(doc.get("baraban_variantlar"))
	if not vs:
		frappe.throw(_("Variantlar noto'g'ri: soatlarni vergul bilan yozing, masalan 1,2,3"))
	if doc.get("baraban_yutuq") not in vs:
		frappe.throw(_("Har doim tushadigan variant variantlar ichida bo'lishi kerak"))
	doc.baraban_variantlar = ",".join(map(str, vs))


def _cookie_name(shop):
	return COOKIE_PREFIX + hashlib.sha1(str(shop).encode()).hexdigest()[:12]


def _base_config(shop):
	"""Arzon tekshiruv (Shop + Item get_value). Yaroqsiz bo'lsa None; xato bersa ham None."""
	try:
		vals = frappe.db.get_value(
			"Shop",
			shop,
			["baraban_yoqilgan", "baraban_tovar", "baraban_narx", "baraban_variantlar", "baraban_yutuq"],
			as_dict=True,
		)
		if not vals or not vals.baraban_yoqilgan:
			return None
		tovar = vals.baraban_tovar
		narx = flt(vals.baraban_narx)
		vs = variants(vals.baraban_variantlar)
		yutuq = cint(vals.baraban_yutuq)
		if not tovar or narx <= 0 or not vs or yutuq not in vs:
			return None
		item = frappe.db.get_value(
			"Item", tovar, ["shop", "item_name", "image", "disabled", "is_published", "has_variants"], as_dict=True
		)
		if not item or item.shop != shop or cint(item.disabled) or not cint(item.is_published):
			return None
		return frappe._dict(
			tovar=tovar, narx=narx, variantlar=vs, yutuq=yutuq, tovar_nomi=item.item_name, rasm=item.image,
			has_variants=cint(item.has_variants),
		)
	except Exception:
		frappe.log_error(title="Baraban: config", message=frappe.get_traceback())
		return None


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
		frappe.log_error(title="Baraban: config", message=frappe.get_traceback())
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


def _state(shop, cfg, row, spun=False):
	return {
		"enabled": True,
		"spun": spun or bool(row),
		"variants": cfg.variantlar,
		"win": cfg.yutuq,
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
def spin(shop):
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
			"soat": cfg.yutuq,
			"qolgan_soniya": cfg.yutuq * 3600,
			"oxirgi_signal": now,
		}
	).insert(ignore_permissions=True)
	frappe.local.cookie_manager.set_cookie(
		_cookie_name(shop), token, max_age=30 * 86400, httponly=True, samesite="Lax"
	)
	return _state(shop, cfg, frappe._dict(qolgan_soniya=cfg.yutuq * 3600), spun=True)


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
	"""(tovar, narx) agar baraban yutuqi hali amal qilsa, aks holda None. Hech qachon xato bermaydi."""
	try:
		row = _row(shop)
		if not row or cint(row.qolgan_soniya) <= 0:
			return None
		cfg = _base_config(shop)
		if cfg:
			return (cfg.tovar, cfg.narx)  # storefront: tovarning o'zi yoki uning varianti
	except Exception:
		frappe.log_error(title="Baraban active xatosi")
	return None


def cleanup():
	"""Kunlik: cookie (30 kun) muddati o'tgan qatorlarni o'chiradi. Ertaroq o'chirilsa, qaytgan mijozga baraban
	qayta chiqib, yangi chegirma olardi (tick modified'ni yangilamaydi — shuning uchun creation bo'yicha)."""
	frappe.db.delete("Baraban Chegirma", {"creation": ["<", add_days(now_datetime(), -31)]})


# ---------- Admin: do'kon formasida baraban tovarini tanlash ----------
def _shop_items(shop, txt="", code=None, start=0, limit=60, fields=None):
	frappe.has_permission("Shop", "read", shop, throw=True)
	filters = {"shop": shop, "disabled": 0, "variant_of": ["is", "not set"]}
	if code:
		filters["name"] = code
	txt = (txt or "").strip()
	or_filters = {"item_name": ["like", f"%{txt}%"], "name": ["like", f"%{txt}%"]} if txt else None
	return frappe.get_all(
		"Item",
		filters=filters,
		or_filters=or_filters,
		fields=fields or ["name", "item_name", "image", "has_variants", "is_published"],
		order_by="item_name asc",
		limit_start=cint(start),
		limit_page_length=cint(limit),
	)


@frappe.whitelist()
def tovarlar(shop, txt="", code=None):
	"""«Tovar tanlash» oynasi: shu do'kon tovarlari rasm, nom va narx bilan (variantlar emas — ota tovar)."""
	from marketplace.storefront import _get_prices

	rows = _shop_items(shop, txt, code)
	prices = _get_prices([r.name for r in rows]) if rows else {}
	if any(r.has_variants for r in rows):
		# Variantli tovarda narx variantlarda: eng arzon variant narxi ko'rsatiladi
		var = frappe.get_all(
			"Item",
			filters={"variant_of": ["in", [r.name for r in rows if r.has_variants]], "disabled": 0},
			fields=["name", "variant_of"],
		)
		vp = _get_prices([v.name for v in var]) if var else {}
		for v in var:
			p = flt(vp.get(v.name))
			if p and (not prices.get(v.variant_of) or p < flt(prices[v.variant_of])):
				prices[v.variant_of] = p
	for r in rows:
		r.price = flt(prices.get(r.name))
	return rows


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def tovar_query(doctype, txt, searchfield, start, page_len, filters):
	"""Tovar maydonining ochiladigan ro'yxati: faqat shu do'kon tovarlari, uzun tavsifsiz — kod va nom."""
	shop = (filters or {}).get("shop")
	if not shop:
		return []
	return [(r.name, r.item_name) for r in _shop_items(shop, txt, start=start, limit=page_len, fields=["name", "item_name"])]
