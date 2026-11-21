"""Chegirma barabani: do'kon sozlamalarini tekshirish va yordamchilar."""

import hashlib

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, flt, now_datetime, time_diff_in_seconds

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


def config(shop):
	"""Faol va to'g'ri sozlangan baraban config'i, aks holda None. Hech qachon xato bermaydi."""
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
	item = frappe.db.get_value("Item", tovar, ["shop", "item_name", "image"], as_dict=True)
	if not item or item.shop != shop:
		return None
	from marketplace.storefront import _get_prices

	eski = _get_prices([tovar]).get(tovar)
	return frappe._dict(
		tovar=tovar,
		narx=narx,
		variantlar=vs,
		yutuq=yutuq,
		tovar_nomi=item.item_name,
		eski_narx=flt(eski) if eski else None,
		rasm=item.image,
	)


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


def _state(shop, cfg, row, spun=False):
	return {
		"enabled": True,
		"spun": spun or bool(row),
		"variants": cfg.variantlar,
		"win": cfg.yutuq,
		"remaining": max(0, cint(row.qolgan_soniya)) if row else 0,
		"price": cfg.narx,
		"old_price": cfg.eski_narx,
		"product": {"code": cfg.tovar, "name": cfg.tovar_nomi, "thumb": cfg.rasm},
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def state(shop):
	from marketplace.storefront import get_shop

	shop = get_shop(shop).name
	cfg = config(shop)
	if not cfg:
		return {"enabled": False}
	return _state(shop, cfg, _row(shop))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=60)
def spin(shop):
	from marketplace.storefront import get_shop

	shop = get_shop(shop).name
	cfg = config(shop)
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
@rate_limit(limit=60, seconds=60)
def tick(shop):
	from marketplace.storefront import get_shop

	shop = get_shop(shop).name
	row = _row(shop)
	if not row:
		return {"remaining": 0}
	remaining = max(0, cint(row.qolgan_soniya))
	if remaining > 0:
		now = now_datetime()
		gap = time_diff_in_seconds(now, row.oxirgi_signal) if row.oxirgi_signal else 0
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
		cfg = config(shop)
		row = _row(shop) if cfg else None
		if cfg and row and cint(row.qolgan_soniya) > 0:
			return (cfg.tovar, cfg.narx)
	except Exception:
		frappe.log_error(title="Baraban active xatosi")
	return None
