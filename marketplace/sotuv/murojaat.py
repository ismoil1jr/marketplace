"""Instagram (lead-forma) murojaatlari: reklama formasini to'ldirgan mijoz saytga "Murojaat" bo'lib tushadi,
do'konning sotuv menejeri Sotuv panelidagi "Murojaatlar" bo'limida qo'ng'iroq qiladi va natija yozadi.

Qabul: POST /api/method/marketplace.sotuv.murojaat.qabul?kalit=<do'kon kaliti>&tovar=<tovar kodi>
* kalit — do'konning "Murojaat API kaliti" (Shop.murojaat_kaliti): murojaat qaysi do'konga tushishini shu belgilaydi;
* tovar — reklama qaysi kitob (tovar) bo'yicha: har bir tovarning o'z havolasi (tovar formasidagi «SMM havolasi»);
* tana — JSON yoki form: ism/first_name, familiya/last_name yoki full_name, telefon/phone, shahar/city, izoh/comment,
  kampaniya/campaign, lead_id. Meta lead-formasi ko'rinishi ({"field_data": [{"name", "values"}]}) ham tushuniladi.
SMM vositasi (Make, Zapier va h.k.) formani shu manzilga yuboradi. Bir xil lead qayta kelsa — yangisi yaratilmaydi.

Qo'ng'iroq yozuvi murojaatga RAQAM bo'yicha bog'lanadi (telefoniya.ingest_call), mijoz keyin saytda buyurtma bersa —
murojaat "Buyurtma berdi" bo'ladi.
"""

import json
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, get_url, getdate, now_datetime, today

from marketplace.sotuv.telefoniya import normalize_phone

RESULTS = ("Oladi", "Olmaydi", "Javob bermadi", "Keyinroq")
CHANNELS = ("Qo‘ng‘iroq", "SMS")
# Formadagi maydon nomlari har xil bo'ladi (Meta, Make, Zapier, o'zbekcha) — birinchi to'ldirilgani olinadi
KEYS = {
	"ism": ("ism", "first_name", "firstname", "name_first", "имя"),
	"familiya": ("familiya", "last_name", "lastname", "surname", "фамилия"),
	"to'liq": ("full_name", "fullname", "name", "ism_familiya", "fio", "фио"),
	"telefon": ("telefon", "phone", "phone_number", "phonenumber", "tel", "mobile", "номер_телефона", "телефон"),
	"izoh": ("izoh", "comment", "comments", "message", "note", "savol", "комментарий"),
	"shahar": ("shahar", "city", "viloyat", "region", "tuman", "город", "manzil"),
	"tovar": ("tovar", "kitob", "product", "book", "item"),
	"kampaniya": ("kampaniya", "campaign", "campaign_name", "utm_campaign", "ad_name", "adset_name"),
	"forma": ("forma", "form", "form_name", "form_id"),
	"manba": ("manba", "source", "platform"),
	"lead_id": ("lead_id", "leadgen_id", "id"),
}
SOURCES = {"instagram": "Instagram", "ig": "Instagram", "facebook": "Facebook", "fb": "Facebook", "telegram": "Telegram", "sayt": "Sayt", "site": "Sayt"}


# ---------------- Do'kon kaliti ----------------


def ensure_key(shop):
	"""Do'konga murojaat kaliti (yo'q bo'lsa — yaratiladi). Shop.after_insert va bir martalik patch chaqiradi."""
	key = frappe.db.get_value("Shop", shop, "murojaat_kaliti")
	if not key:
		key = secrets.token_urlsafe(18)
		frappe.db.set_value("Shop", shop, "murojaat_kaliti", key, update_modified=False)
	return key


def _shop_by_key(key):
	key = (key or "").strip()
	return key and len(key) >= 16 and frappe.db.get_value("Shop", {"murojaat_kaliti": key}, "name")


@frappe.whitelist()
def smm_link(item: str | None = None, shop: str | None = None):
	"""Do'kon egasi / admin uchun: SMM'ga beriladigan havola (tovar bo'yicha). Sotuv menejeri va kuryerga — yo'q."""
	from marketplace.permissions import get_user_shop, is_admin

	if item:
		shop = frappe.db.get_value("Item", item, "shop")
		item = frappe.db.get_value("Item", item, "variant_of") or item
	own = get_user_shop()
	allowed = is_admin() or (own == shop and "Shop Seller" in frappe.get_roles())
	if not shop or not allowed:
		frappe.throw(_("SMM havolasini faqat do'kon egasi yoki admin ko'radi"), frappe.PermissionError)
	url = f"{get_url()}/api/method/marketplace.sotuv.murojaat.qabul?kalit={ensure_key(shop)}"
	if item:
		url += f"&tovar={item}"
	return {"url": url, "shop": shop, "item": item, "item_name": item and frappe.db.get_value("Item", item, "item_name")}


# ---------------- Qabul (reklama formasi) ----------------


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def qabul(**kwargs):
	"""Lead-formadan bitta murojaat (POST). Qaytaradi: {"status": "ok", "name", "duplicate"}.
	Kalit noto'g'ri bo'lsa — 403, telefon yo'q bo'lsa — 417 (SMM vositasi xatoni ko'radi va qayta yubormaydi).
	GET — faqat tekshirish: havolani brauzerda ochsa, qaysi do'kon va qaysi tovarga ulangani ko'rinadi."""
	data = _payload()
	# JSON tanali so'rovda Frappe havoladagi ?kalit=...&tovar=... ni form_dict'ga qo'shmaydi — _payload ularni o'zi oladi
	shop = _shop_by_key(data.pop("kalit", None) or frappe.get_request_header("X-Murojaat-Kalit"))
	if not shop:
		raise frappe.PermissionError(_("Murojaat kaliti noto'g'ri"))
	if frappe.request and frappe.request.method == "GET":
		return _link_check(shop, _pick(data, "tovar"))
	phone = _pick(data, "telefon")
	normal = normalize_phone(phone)
	if not normal or len(normal) < 9:
		frappe.throw(_("Telefon raqami yo'q yoki noto'g'ri"))

	lead_id = _pick(data, "lead_id")[:140]
	tovar, tovar_nomi = _item(shop, _pick(data, "tovar"))
	# Qayta yuborilgan lead (SMM vositasi takrorlasa) yoki 10 daqiqa ichida aynan o'sha mijoz + tovar — dublikat
	dup = (lead_id and frappe.db.get_value("Murojaat", {"shop": shop, "tashqi_id": lead_id})) or frappe.db.get_value(
		"Murojaat",
		{"shop": shop, "normal_telefon": normal, "tovar": tovar or ["is", "not set"],
		 "creation": [">", add_to_date(now_datetime(), minutes=-10)]},
	)
	if dup:
		return {"status": "ok", "name": dup, "duplicate": True}

	ism, familiya = _pick(data, "ism"), _pick(data, "familiya")
	full = _pick(data, "to'liq")
	if full and not (ism or familiya):
		ism, _sep, familiya = full.partition(" ")
	source = SOURCES.get(_pick(data, "manba").lower(), "Instagram")
	doc = frappe.get_doc(
		{
			"doctype": "Murojaat",
			"shop": shop,
			"ism": ism[:140] or None,
			"familiya": familiya.strip()[:140] or None,
			"mijoz_ismi": (" ".join(x for x in (ism, familiya.strip()) if x) or full or phone)[:140],
			"telefon": phone[:40],
			"normal_telefon": normal,
			"izoh": _pick(data, "izoh")[:2000] or None,
			"shahar": _pick(data, "shahar")[:140] or None,
			"tovar": tovar,
			"tovar_nomi": tovar_nomi,
			"manba": source,
			"kampaniya": _pick(data, "kampaniya")[:140] or None,
			"forma": _pick(data, "forma")[:140] or None,
			"tashqi_id": lead_id or None,
			"holat": "Yangi",
			"xom": json.dumps(data, ensure_ascii=False, default=str)[:5000],
		}
	)
	doc.insert(ignore_permissions=True)
	_notify(doc)
	return {"status": "ok", "name": doc.name, "duplicate": False}


def _link_check(shop, value):
	tovar, tovar_nomi = _item(shop, value)
	if value and not tovar:
		xabar = _("Diqqat: «{0}» tovari bu do'konda topilmadi — murojaatlar tovarsiz yoziladi").format(value)
	else:
		xabar = _("Havola ishlayapti. Murojaatni POST bilan yuboring: full_name, phone, city, comment")
	return {
		"status": "ok", "dokon": frappe.db.get_value("Shop", shop, "shop_name"), "tovar": tovar, "tovar_nomi": tovar_nomi,
		"xabar": xabar,
	}


def _payload():
	"""Havoladagi parametrlar (kalit, tovar) + JSON tana yoki form maydonlari; Meta'ning field_data ro'yxati
	tekis lug'atga aylantiriladi."""
	data = {}
	request = getattr(frappe.local, "request", None)
	if request is not None:
		data.update(request.args.to_dict())
		try:
			body = request.get_json(silent=True)
		except Exception:
			body = None
		if isinstance(body, dict):
			data.update(body)
	data.update({k: v for k, v in frappe.form_dict.items() if k != "cmd"})
	for row in data.pop("field_data", None) or []:
		if isinstance(row, dict) and row.get("name"):
			values = row.get("values") or []
			data.setdefault(str(row["name"]), values[0] if values else "")
	return {str(k).strip().lower().replace(" ", "_"): v for k, v in data.items()}


# Meta formasidagi o'z savollari kalit bo'lib keladi: "telefon_raqamingiz", "qaysi_shahardansiz?", "savolingiz_bormi?"
STEMS = {
	"telefon": ("phone", "telefon", "raqam", "номер", "телефон"),
	"shahar": ("shahar", "city", "viloyat", "hudud", "город"),
	"izoh": ("izoh", "savol", "comment", "вопрос", "коммент"),
	"to'liq": ("ism", "имя", "фио"),
}
KNOWN = {key for keys in KEYS.values() for key in keys}


def _pick(data, field):
	for key in KEYS[field]:
		value = data.get(key)
		if value not in (None, ""):
			return str(value).strip()
	for key, value in data.items():
		if key not in KNOWN and value not in (None, "") and any(stem in key for stem in STEMS.get(field, ())):
			return str(value).strip()
	return ""


def _item(shop, value):
	"""Tovar kodi yoki nomi (shu do'kon ichida). Topilmasa — (None, kelgan matn)."""
	if not value:
		return None, None
	row = frappe.db.get_value("Item", {"name": value, "shop": shop}, ["name", "item_name", "variant_of"], as_dict=True) or frappe.db.get_value(
		"Item", {"item_name": value, "shop": shop, "variant_of": ["is", "not set"]}, ["name", "item_name", "variant_of"], as_dict=True
	)
	if not row:
		return None, value[:140]
	if row.variant_of:
		return row.variant_of, frappe.db.get_value("Item", row.variant_of, "item_name")
	return row.name, row.item_name


def _notify(doc):
	"""Yangi murojaat — faqat saytda (Telegram'ga emas): do'kon egasi va sotuv menejerlariga Desk qo'ng'iroqchasi
	va ochiq oynada ovozli xabar. Murojaatning o'zi Sotuv panelidagi "Murojaatlar" bo'limida."""
	subject = _("Yangi murojaat ({0}): {1}, {2}").format(doc.manba, doc.mijoz_ismi, doc.telefon) + (
		f" — {doc.tovar_nomi}" if doc.tovar_nomi else ""
	)
	users = set(
		frappe.get_all("Shop Member", filters={"parent": doc.shop, "parenttype": "Shop", "role": ["!=", "Kuryer"]}, pluck="user")
	)
	for user in users:
		frappe.get_doc(
			{"doctype": "Notification Log", "for_user": user, "type": "Alert", "document_type": "Murojaat",
			 "document_name": doc.name, "subject": subject}
		).insert(ignore_permissions=True)
		frappe.publish_realtime("marketplace_new_order", {"name": doc.name, "subject": subject}, user=user, after_commit=True)


# ---------------- Sotuv paneli: Murojaatlar ----------------


# "Hammasi" yonidagi natija bo'yicha filtrlar: menejer yozgan holat
STATUS_VIEWS = {"oladi": "Oladi", "keyinroq": "Keyinroq", "javob_bermadi": "Javob bermadi", "olmaydi": "Olmaydi",
                "buyurtma_berdi": "Buyurtma berdi"}


def _filters(view, shop):
	base = {"shop": shop}
	if view in STATUS_VIEWS:
		return {**base, "holat": STATUS_VIEWS[view]}
	if view == "yangi":
		return {**base, "holat": "Yangi"}
	if view == "bugun":
		return {**base, "keyingi_qongiroq": ["between", ["2000-01-01", today()]], "holat": ["not in", ["Olmaydi", "Buyurtma berdi"]]}
	if view == "jarayonda":
		return {**base, "holat": ["in", ["Oladi", "Javob bermadi", "Keyinroq"]]}
	return base


@frappe.whitelist()
def get_leads(view: str = "yangi", q: str | None = None):
	from marketplace.sotuv.api import _has_must, _shop

	shop = _shop(admin_optional=True)
	if not shop:
		return {"need_shop": True}
	_sync_orders(shop)
	or_filters = None
	if (q or "").strip():
		like = f"%{q.strip()}%"
		digits = normalize_phone(q) or ""
		or_filters = [["mijoz_ismi", "like", like], ["tovar_nomi", "like", like], ["kampaniya", "like", like], ["shahar", "like", like],
		              ["name", "like", like]]
		if len(digits) >= 4:
			or_filters.append(["normal_telefon", "like", f"%{digits[-9:]}%"])
	rows = frappe.get_all(
		"Murojaat", filters=_filters(view, shop), or_filters=or_filters,
		fields=["name", "mijoz_ismi", "telefon", "normal_telefon", "izoh", "shahar", "tovar", "tovar_nomi", "manba", "kampaniya", "holat",
		        "keyingi_qongiroq", "aloqa_vaqt", "creation", "buyurtma"],
		order_by="creation desc", limit_page_length=300,
	)
	calls = {}
	phones = list({r.normal_telefon for r in rows if r.normal_telefon})
	if phones:
		for c in frappe.get_all(
			"Telefon Qongiroq", filters={"shop": shop, "normal_telefon": ["in", phones]},
			fields=["normal_telefon", {"COUNT": "*", "as": "n"}], group_by="normal_telefon",
		):
			calls[c.normal_telefon] = c.n
	for r in rows:
		r.calls = calls.get(r.normal_telefon, 0)
	counts = {v: frappe.db.count("Murojaat", _filters(v, shop)) for v in ("yangi", "bugun", "jarayonda", "hammasi")}
	by_status = dict(frappe.get_all("Murojaat", filters={"shop": shop}, fields=["holat", {"COUNT": "*", "as": "n"}],
	                                group_by="holat", as_list=True))
	counts.update({v: by_status.get(holat, 0) for v, holat in STATUS_VIEWS.items()})
	return {"shop": shop, "shop_name": frappe.db.get_value("Shop", shop, "shop_name"), "rows": rows, "counts": counts,
	        "must": _has_must(shop)}


def _sync_orders(shop):
	"""Murojaatdan keyin saytda buyurtma bergan mijozlar — "Buyurtma berdi" (raqam bo'yicha, shu do'konda)."""
	open_leads = frappe.get_all(
		"Murojaat", filters={"shop": shop, "holat": ["not in", ["Buyurtma berdi"]], "normal_telefon": ["is", "set"]},
		fields=["name", "normal_telefon", "creation"], limit_page_length=1000,
	)
	if not open_leads:
		return
	phones = {"+" + r.normal_telefon for r in open_leads}
	orders = frappe.get_all(
		"Sales Order", filters={"shop": shop, "docstatus": 1, "mp_placed": 1, "customer_phone": ["in", list(phones)]},
		fields=["name", "customer_phone", "creation"], order_by="creation asc",
	)
	for lead in open_leads:
		so = next((o for o in orders if o.customer_phone == "+" + lead.normal_telefon and o.creation >= lead.creation), None)
		if so:
			frappe.db.set_value("Murojaat", lead.name, {"holat": "Buyurtma berdi", "buyurtma": so.name}, update_modified=False)


def _lead(name, shop):
	doc = frappe.get_doc("Murojaat", name)
	if doc.shop != shop:
		frappe.throw(_("Bu murojaat sizning do'koningizniki emas"), frappe.PermissionError)
	return doc


@frappe.whitelist()
def get_lead(name: str):
	"""Murojaat kartasi: mijoz, qaysi tovar (rasm, narx, saytdagi havola), qo'ng'iroqlar (audio), natijalar,
	shu raqamdan saytdagi buyurtmalar."""
	from marketplace.sotuv.api import _shop, mandatory_info
	from marketplace.storefront import _get_prices

	shop = _shop()
	doc = _lead(name, shop)
	item = None
	if doc.tovar:
		row = frappe.db.get_value("Item", doc.tovar, ["name", "item_name", "image"], as_dict=True) or {}
		item = {**row, "price": _get_prices([doc.tovar]).get(doc.tovar), "url": f"{get_url()}/s/{shop}/p/{doc.tovar}"}
	calls = frappe.get_all(
		"Telefon Qongiroq", filters={"shop": shop},
		or_filters=[["murojaat", "=", doc.name]] + ([["normal_telefon", "=", doc.normal_telefon]] if doc.normal_telefon else []),
		fields=["name", "boshlandi", "yonalish", "davomiyligi", "yozuv", "menejer", "holat", "ai_xulosa", "transkript"],
		order_by="boshlandi desc", limit_page_length=50,
	)
	logs = frappe.get_all(
		"Aloqa Yozuvi", filters={"shop": shop},
		or_filters=[["murojaat", "=", doc.name]] + ([["telefon", "=", doc.telefon]] if doc.telefon else []),
		fields=["name", "creation", "buyurtma", "murojaat", "kanal", "natija", "izoh", "keyingi_qongiroq", "menejer"],
		order_by="creation desc", limit_page_length=100,
	)
	orders = frappe.get_all(
		"Sales Order", filters={"shop": shop, "docstatus": ["in", [1, 2]], "customer_phone": "+" + (doc.normal_telefon or "")},
		fields=["name", "grand_total", "payment_status", "creation", "mp_placed", "docstatus"], order_by="creation desc", limit_page_length=20,
	)
	users = {u for u in [c.menejer for c in calls] + [lg.menejer for lg in logs] if u}
	names = {u: frappe.utils.get_fullname(u) for u in users}
	for c in calls:
		c.menejer_ismi = names.get(c.menejer) or c.menejer
	for lg in logs:
		lg.menejer_ismi = names.get(lg.menejer) or lg.menejer
	return {
		"name": doc.name, "mijoz_ismi": doc.mijoz_ismi, "telefon": doc.telefon, "izoh": doc.izoh, "shahar": doc.shahar, "manba": doc.manba,
		"kampaniya": doc.kampaniya, "forma": doc.forma, "holat": doc.holat, "created": str(doc.creation),
		"keyingi_qongiroq": str(doc.keyingi_qongiroq or ""), "tovar_nomi": doc.tovar_nomi, "item": item,
		"calls": calls, "logs": logs, "orders": orders,
		"mandatory": mandatory_info(shop, "+" + doc.normal_telefon if doc.normal_telefon else None),
	}


@frappe.whitelist(methods=["POST"])
def save_lead_result(name: str, kanal: str, natija: str, izoh: str | None = None, keyingi_qongiroq: str | None = None):
	"""Menejer natijasi murojaat bo'yicha: Aloqa Yozuvi + murojaat holati va qayta qo'ng'iroq sanasi."""
	from marketplace.sotuv.api import _shop

	shop = _shop()
	doc = _lead(name, shop)
	if kanal not in CHANNELS or natija not in RESULTS:
		frappe.throw(_("Kanal va natijani tanlang"))
	date = getdate(keyingi_qongiroq) if keyingi_qongiroq else None
	if date and date < getdate(today()):
		frappe.throw(_("Qayta qo'ng'iroq sanasi o'tib ketgan kun bo'lmasin"))
	log = frappe.get_doc(
		{
			"doctype": "Aloqa Yozuvi", "murojaat": doc.name, "mijoz_ismi": doc.mijoz_ismi, "telefon": doc.telefon,
			"shop": shop, "kanal": kanal, "natija": natija, "izoh": (izoh or "").strip() or None,
			"keyingi_qongiroq": date, "menejer": frappe.session.user,
		}
	)
	log.insert(ignore_permissions=True)
	doc.db_set(
		{"holat": "Buyurtma berdi" if doc.holat == "Buyurtma berdi" else natija, "keyingi_qongiroq": date,
		 "menejer": frappe.session.user, "aloqa_vaqt": now_datetime()},
		update_modified=False,
	)
	return {"name": log.name}
