"""Instagram/Facebook reklamasidagi Instant Form (lead-forma) → Murojaat, Make/Zapier va Google Sheets'siz.

Meta App bitta — butun platformaga (developers.facebook.com, Business turi): App ID va App Secret Marketplace
Settings'da. Har bir do'kon o'z Facebook sahifasini ulaydi (Shop → Instagram (Meta) → «Meta'ga ulash»): sahifa tokeni
shifrlanib saqlanadi, sahifa ilovaga «leadgen» bo'yicha obuna qilinadi, sahifaning formalari Shop → «Formalar → tovar»
jadvaliga tushadi — do'kon egasi har bir formaga tovarni tanlaydi.

Mijoz formani to'ldirsa:
1. Meta webhook'ni chaqiradi (POST, X-Hub-Signature-256 imzosi App Secret bilan tekshiriladi) — faqat lead ID keladi;
2. lead Graph API'dan sahifa tokeni bilan olinadi: ism, telefon, qaysi forma va reklama;
3. forma bog'langan tovar bo'yicha murojaat yoziladi (murojaat.save_lead) → Sotuv paneli → Murojaatlar.
Webhook kelmay qolsa ham (ilova Development rejimida, tarmoq uzilishi) har 10 daqiqada oxirgi 2 kunlik lidlar tortib
olinadi (poll_leads). Takror yozilmaydi — lead ID bo'yicha (Murojaat.tashqi_id).
"""

import hashlib
import hmac
import json
import time

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, format_datetime, get_url, now_datetime
from frappe.utils.password import get_decrypted_password, remove_encrypted_password, set_encrypted_password
from werkzeug.wrappers import Response

from marketplace.sotuv.murojaat import _pick, save_lead

GRAPH = "https://graph.facebook.com"
# Reklama nomi (ad_name) ba'zi tokenlarda ruxsat so'raydi — bo'lmasa reklamasiz maydonlar bilan qayta so'raladi
LEAD_FIELDS = ("id,created_time,field_data,form_id,platform,ad_name,campaign_name", "id,created_time,field_data,form_id,platform")
FORM_STATUS = {"ACTIVE": "Faol", "ARCHIVED": "Arxivda", "DRAFT": "Qoralama", "DELETED": "O'chirilgan"}
POLL_DAYS = 2


class MetaError(Exception):
	def __init__(self, message, code=None):
		super().__init__(message)
		self.code = code


def _conf():
	s = frappe.get_single("Marketplace Settings")
	return frappe._dict(
		app_id=(s.meta_app_id or "").strip(),
		secret=(s.get_password("meta_app_secret", raise_exception=False) or "").strip(),
		verify=s.meta_verify_token or "",
		ver=(s.meta_graph_version or "v23.0").strip(),
	)


def _graph(method, path, token=None, **params):
	"""Graph API so'rovi. Xato bo'lsa — MetaError (Meta'ning o'z matni; token va havola xatoga yozilmaydi)."""
	conf = _conf()
	if token:
		params["access_token"] = token
		# "Require app secret" yoqilgan ilovada har bir so'rov shu imzoni so'raydi; yoqilmaganda ham zarari yo'q
		if conf.secret and "|" not in token:
			params["appsecret_proof"] = hmac.new(conf.secret.encode(), token.encode(), hashlib.sha256).hexdigest()
	url = f"{GRAPH}/{conf.ver}/{path.lstrip('/')}"
	try:
		r = requests.request(method, url, params=params if method == "GET" else None,
		                     data=None if method == "GET" else params, timeout=25)
	except requests.RequestException as e:
		# from None: zanjirdagi urllib3 xatosi to'liq URL'ni (access_token, appsecret_proof) saqlaydi — traceback'ga tushmasin
		raise MetaError(_("Meta bilan aloqa yo'q ({0})").format(type(e).__name__)) from None
	try:
		body = r.json()
	except ValueError:
		body = {}
	err = body.get("error") if isinstance(body, dict) else None
	if r.status_code >= 400 or err:
		err = err or {}
		raise MetaError(err.get("error_user_msg") or err.get("message") or f"HTTP {r.status_code}", err.get("code"))
	return body


def ad_account(value):
	"""Reklama kabineti ID'si doim «act_» bilan (qo'lda «123» deb yozilgan bo'lsa ham)."""
	value = (value or "").strip()
	return value if not value or value.startswith("act_") else f"act_{value}"


def _page_token(shop):
	token = get_decrypted_password("Shop", shop, "meta_page_token", raise_exception=False)
	if not token:
		raise MetaError(_("Do'kon Meta'ga ulanmagan"))
	return token


def _status(shop, text):
	"""Shop → «Oxirgi holat»: Meta'dan nima keldi / qanday xato — do'kon formasida ko'rinadi."""
	line = f"{format_datetime(now_datetime(), 'dd.MM.yyyy HH:mm')} — {text}"
	frappe.db.set_value("Shop", shop, "meta_holat", line[:1000], update_modified=False)


IG_STATUS_TTL = 3600


def _ig_status(shop, text):
	"""Shop → «Instagram AI holati» (lead-formaning «Oxirgi holat»iga tegmaydi). Har daqiqalik tekshiruv bir xil matnni
	qayta-qayta yozmasin: so'nggi bir soatda yozilgan matn takrorlansa — o'tkazib yuboriladi. Qaytaradi: yozildimi
	(chaqiruvchi Error Log'ni ham faqat shunda yozadi)."""
	key = f"mp_ig_last_err:{shop}"
	now = time.time()
	seen = frappe.cache.get_value(key)
	seen = {t: ts for t, ts in (seen if isinstance(seen, dict) else {}).items() if now - ts < IG_STATUS_TTL}
	if text in seen:
		return False
	seen[text] = now
	frappe.cache.set_value(key, seen, expires_in_sec=IG_STATUS_TTL)
	line = f"{format_datetime(now_datetime(), 'dd.MM.yyyy HH:mm')} — {text}"
	frappe.db.set_value("Shop", shop, "ig_holat", line[:1000], update_modified=False)
	return True


def _check(shop, owner_ok=False):
	from marketplace.permissions import get_user_shop, is_admin

	if not shop or not frappe.db.exists("Shop", shop):
		frappe.throw(_("Do'kon topilmadi"))
	if is_admin() or (owner_ok and get_user_shop() == shop and "Shop Seller" in frappe.get_roles()):
		return
	frappe.throw(_("Buni faqat admin (formalarni — do'kon egasi ham) qila oladi"), frappe.PermissionError)


def callback_url():
	return f"{get_url()}/api/method/marketplace.sotuv.meta.webhook"


# ---------------- Webhook (Meta chaqiradi) ----------------


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=120, seconds=60)
def webhook(**kwargs):
	"""GET — Meta obunani tasdiqlaydi (hub.challenge qaytariladi), POST — yangi lid(lar) haqida xabar."""
	req = frappe.request
	conf = _conf()
	if req.method == "GET":
		args = req.args
		if args.get("hub.mode") == "subscribe" and conf.verify and hmac.compare_digest(args.get("hub.verify_token") or "", conf.verify):
			return Response(args.get("hub.challenge") or "", status=200, mimetype="text/plain")
		return Response("forbidden", status=403, mimetype="text/plain")

	raw = req.get_data() or b""
	sig = req.headers.get("X-Hub-Signature-256") or ""
	expected = conf.secret and hmac.new(conf.secret.encode(), raw, hashlib.sha256).hexdigest()
	if not (expected and sig.startswith("sha256=") and hmac.compare_digest(sig[7:], expected)):
		return Response("bad signature", status=403, mimetype="text/plain")
	try:
		body = json.loads(raw)
	except ValueError:
		return Response("bad json", status=400, mimetype="text/plain")

	if isinstance(body, dict) and body.get("object") == "page":
		for entry in body.get("entry") or []:
			for change in entry.get("changes") or []:
				value = change.get("value") or {}
				if change.get("field") != "leadgen" or not value.get("leadgen_id"):
					continue
				lead_id = str(value["leadgen_id"])
				frappe.enqueue(
					"marketplace.sotuv.meta.process_lead", queue="short", enqueue_after_commit=True,
					job_id=f"meta-lead-{lead_id}", deduplicate=True,
					page_id=str(value.get("page_id") or entry.get("id") or ""), leadgen_id=lead_id,
				)
	# Meta 200 kutadi; kechiksa yoki xato bo'lsa — qayta-qayta yuboradi
	return Response("ok", status=200, mimetype="text/plain")


def process_lead(page_id, leadgen_id):
	"""Fon ishi: bitta lidni Graph API'dan olib murojaat yozadi."""
	shop = frappe.db.get_value("Shop", {"meta_page_id": page_id}, "name") if page_id else None
	if not shop:
		frappe.log_error(title="Meta lid: do'kon topilmadi", message=f"Lid {leadgen_id}: Facebook sahifa {page_id} hech bir do'konga ulanmagan")
		return None
	existing = frappe.db.get_value("Murojaat", {"shop": shop, "tashqi_id": leadgen_id}, "name")
	if existing:
		return existing
	try:
		lead = _get_lead(shop, leadgen_id)
		return _store(shop, lead)
	except MetaError as e:
		_status(shop, _("lid {0} olinmadi: {1}").format(leadgen_id, e))
		frappe.log_error(title=f"Meta lid: {shop}", message=f"Lid {leadgen_id}: {e}")


def _get_lead(shop, leadgen_id):
	token = _page_token(shop)
	try:
		return _graph("GET", leadgen_id, token, fields=LEAD_FIELDS[0])
	except MetaError:
		return _graph("GET", leadgen_id, token, fields=LEAD_FIELDS[1])


def _flatten(lead):
	"""Meta field_data ([{"name": "full_name", "values": ["Ali Valiyev"]}, ...]) → tekis lug'at."""
	data = {}
	for row in lead.get("field_data") or []:
		key = str(row.get("name") or "").strip().lower().replace(" ", "_")
		values = [str(v).strip() for v in row.get("values") or [] if v not in (None, "")]
		if key and values:
			data[key] = ", ".join(values)
	return data


def _store(shop, lead):
	"""Lid → Murojaat. Tovar: forma bog'langan tovar, bo'lmasa formadagi yashirin «tovar» maydoni."""
	lead_id = str(lead.get("id") or "")
	form_id = str(lead.get("form_id") or "")
	data = _flatten(lead)
	form = frappe.db.get_value(
		"Meta Forma", {"parenttype": "Shop", "parent": shop, "form_id": form_id}, ["form_name", "tovar"], as_dict=True
	) or frappe._dict()
	data.update(
		lead_id=lead_id, kampaniya=lead.get("ad_name") or lead.get("campaign_name") or "",
		forma=form.form_name or form_id, manba=lead.get("platform") or "ig",
	)
	try:
		name, duplicate = save_lead(shop, data, form.tovar or _pick(data, "tovar") or None)
	except frappe.ValidationError:
		# Meta'ning "Lead Ads Testing Tool" soxta lidida telefon o'rnida "<test lead: dummy data ...>" bo'ladi
		frappe.clear_messages()
		test = any("test lead" in str(v).lower() for v in data.values())
		_status(shop, _("test lid keldi — ulanish ishlayapti (soxta ma'lumot, murojaat yozilmadi)") if test
		        else _("lid {0}: telefon raqami yo'q, murojaat yozilmadi").format(lead_id))
		_skip(lead_id)
		return None
	if not duplicate:
		_status(shop, _("lid qabul qilindi: {0}").format(name))
	return name


def _skip(lead_id):
	frappe.cache.set_value(f"meta_skip:{lead_id}", 1, expires_in_sec=(POLL_DAYS + 1) * 86400)


def _skipped(lead_id):
	return bool(frappe.cache.get_value(f"meta_skip:{lead_id}"))


# ---------------- Zaxira: lidlarni tortib olish ----------------


def poll_leads():
	"""Har 10 daqiqada (hooks.scheduler_events): ulangan barcha do'konlar — webhook kelmagan lidlar ham tushadi."""
	conf = _conf()
	if not (conf.app_id and conf.secret):
		return
	for shop in frappe.get_all("Shop", filters={"meta_page_id": ["is", "set"]}, pluck="name"):
		try:
			pull(shop)
			frappe.db.commit()
		except MetaError as e:
			frappe.db.rollback()
			# Token eskirgan / ruxsat olingan bo'lsa har 10 daqiqada Error Log to'lmasin — soatiga bir marta
			if frappe.cache.get_value(f"meta_err:{shop}") != str(e):
				frappe.cache.set_value(f"meta_err:{shop}", str(e), expires_in_sec=3600)
				frappe.log_error(title=f"Meta: {shop}", message=str(e))
			_status(shop, _("xato: {0}").format(e))
			frappe.db.commit()


def pull(shop, days=POLL_DAYS):
	"""Do'kon formalarining oxirgi `days` kunlik lidlari: yangilari murojaat bo'lib yoziladi. Qaytaradi: nechta yozildi."""
	token = _page_token(shop)
	forms = _sync_forms(shop)
	known = set(
		frappe.get_all("Murojaat", filters={"shop": shop, "tashqi_id": ["is", "set"], "creation": [">", add_days(now_datetime(), -days - 1)]},
		               pluck="tashqi_id")
	)
	since = int(time.time()) - days * 86400
	saved = 0
	for form in forms:
		if form.holat != FORM_STATUS["ACTIVE"]:
			continue
		for lead in _form_leads(form.form_id, token, since):
			lead_id = str(lead.get("id") or "")
			if not lead_id or lead_id in known or _skipped(lead_id):
				continue
			lead.setdefault("form_id", form.form_id)
			known.add(lead_id)
			if _store(shop, lead):
				saved += 1
	return saved


def _form_leads(form_id, token, since):
	params = {"limit": 100, "filtering": json.dumps([{"field": "time_created", "operator": "GREATER_THAN", "value": since}])}
	try:
		body = _graph("GET", f"{form_id}/leads", token, fields=LEAD_FIELDS[0], **params)
		fields = LEAD_FIELDS[0]
	except MetaError:
		body = _graph("GET", f"{form_id}/leads", token, fields=LEAD_FIELDS[1], **params)
		fields = LEAD_FIELDS[1]
	for _page in range(20):
		yield from body.get("data") or []
		paging = body.get("paging") or {}
		after = (paging.get("cursors") or {}).get("after")
		if not (paging.get("next") and after):
			return
		body = _graph("GET", f"{form_id}/leads", token, fields=fields, after=after, **params)


# ---------------- Formalar → tovar ----------------


def _sync_forms(shop):
	"""Sahifaning lead-formalari Shop → «Formalar → tovar» jadvaliga: yangisi qo'shiladi (nomida tovar kodi yoki nomi
	bo'lsa — tovar o'zi tanlanadi), bor qatorning tanlangan tovari o'zgarmaydi. Qaytaradi: jadval qatorlari."""
	page_id = frappe.db.get_value("Shop", shop, "meta_page_id")
	token = _page_token(shop)
	forms, after = [], None
	for _page in range(10):
		body = _graph("GET", f"{page_id}/leadgen_forms", token, fields="id,name,status", limit=100, **({"after": after} if after else {}))
		forms += body.get("data") or []
		paging = body.get("paging") or {}
		after = (paging.get("cursors") or {}).get("after")
		if not (paging.get("next") and after):
			break

	rows = {r.form_id: r for r in _rows(shop)}
	idx = max([r.idx for r in rows.values()] or [0])
	for f in forms:
		form_id, title = str(f.get("id")), (f.get("name") or "")[:140]
		holat = FORM_STATUS.get(f.get("status"), f.get("status") or "")
		row = rows.get(form_id)
		if row:
			if (row.form_name, row.holat) != (title, holat):
				frappe.db.set_value("Meta Forma", row.name, {"form_name": title, "holat": holat}, update_modified=False)
			continue
		idx += 1
		frappe.get_doc(
			{"doctype": "Meta Forma", "parenttype": "Shop", "parent": shop, "parentfield": "meta_forms", "idx": idx,
			 "form_id": form_id, "form_name": title, "holat": holat, "tovar": _guess_item(shop, title)}
		).db_insert()
	return _rows(shop)


def _rows(shop):
	return frappe.get_all("Meta Forma", filters={"parenttype": "Shop", "parent": shop},
	                      fields=["name", "idx", "form_id", "form_name", "holat", "tovar"], order_by="idx asc")


def _guess_item(shop, title):
	"""Forma nomida tovar kodi yoki nomi bo'lsa ("Ikki eshik — SKU-001") — o'sha tovar; eng uzun moslik olinadi."""
	text = (title or "").lower()
	if not text:
		return None
	best, size = None, 0
	for item in frappe.get_all("Item", filters={"shop": shop, "disabled": 0, "variant_of": ["is", "not set"]}, fields=["name", "item_name"]):
		for word in (item.name, item.item_name):
			word = (word or "").strip().lower()
			if len(word) >= 3 and word in text and len(word) > size:
				best, size = item.name, len(word)
	return best


# ---------------- Do'kon formasi (Desk) ----------------


@frappe.whitelist(methods=["POST"])
def connect(shop: str, user_token: str, page_id: str | None = None):
	"""Admin: Graph API Explorer'dagi foydalanuvchi tokeni bilan do'konga Facebook sahifani ulaydi.
	Token bilan bir nechta sahifa ko'rinsa — {"pages": [...]} qaytadi, admin tanlab qayta yuboradi (page_id bilan)."""
	_check(shop)
	conf = _conf()
	if not (conf.app_id and conf.secret):
		frappe.throw(_("Avval Marketplace Settings → Meta: App ID va App Secret'ni kiriting"))
	user_token = (user_token or "").strip()
	if len(user_token) < 20:
		frappe.throw(_("Tokenni to'liq nusxalang"))
	try:
		# Explorer tokeni 1–2 soat yashaydi; uzoq muddatlisidan olingan sahifa tokeni esa muddatsiz
		long_token = _graph(
			"GET", "oauth/access_token", grant_type="fb_exchange_token", client_id=conf.app_id,
			client_secret=conf.secret, fb_exchange_token=user_token,
		).get("access_token") or user_token
		pages = _graph("GET", "me/accounts", long_token, fields="id,name,access_token", limit=100).get("data") or []
	except MetaError as e:
		frappe.throw(_("Meta: {0}").format(e))
	if not pages:
		frappe.throw(_("Bu token bilan birorta Facebook sahifa ko'rinmadi. Tokenni sahifa admini yaratsin va «pages_show_list» ruxsatini belgilasin."))
	if not page_id and len(pages) > 1:
		return {"pages": [{"id": p["id"], "name": p.get("name")} for p in pages]}
	page = pages[0] if not page_id else next((p for p in pages if p["id"] == page_id), None)
	if not page:
		frappe.throw(_("Sahifa topilmadi"))
	return _attach(shop, page, long_token)


def _attach(shop, page, user_token=None):
	other = frappe.db.get_value("Shop", {"meta_page_id": page["id"], "name": ["!=", shop]}, "name")
	if other:
		frappe.throw(_("«{0}» sahifasi allaqachon {1} do'koniga ulangan").format(page.get("name"), other))
	try:
		_graph("POST", f"{page['id']}/subscribed_apps", page["access_token"], subscribed_fields="leadgen")
	except MetaError as e:
		frappe.throw(_("Sahifani obuna qilib bo'lmadi: {0}. Token «pages_manage_metadata» ruxsati bilan yaratilganmi?").format(e))
	set_encrypted_password("Shop", shop, page["access_token"], "meta_page_token")
	frappe.db.set_value("Shop", shop, {"meta_page_id": page["id"], "meta_page_name": (page.get("name") or page["id"])[:140],
	                                   "meta_page_token": "*" * 10}, update_modified=False)
	warning = _subscribe_app()
	try:
		forms = _sync_forms(shop)
	except MetaError as e:
		forms = []
		warning = (warning + " " if warning else "") + _("Formalar olinmadi: {0} (token «leads_retrieval», «pages_manage_ads» ruxsatlari bilanmi?)").format(e)
	ig_warning = _link_instagram(shop, page, user_token)
	if ig_warning:
		warning = (warning + " " if warning else "") + ig_warning
	_status(shop, _("ulandi: {0}").format(page.get("name")))
	ig_username, act = frappe.db.get_value("Shop", shop, ["ig_username", "meta_ad_account"]) or (None, None)
	return {"page": page.get("name"), "forms": len(forms), "warning": warning,
	        "ig_username": ig_username or "", "meta_ad_account": ad_account(act)}


def _link_instagram(shop, page, user_token):
	"""Sahifaga bog'langan Instagram professional akkaunt va reklama kabinetini Shop'ga yozadi. Hech qachon xato
	ko'tarmaydi — lead-forma ulanishi buzilmasin; muammo bo'lsa ogohlantirish matni qaytadi (tokensiz)."""
	warnings = []
	try:
		body = _graph("GET", page["id"], page["access_token"], fields="instagram_business_account{id,username}")
		ig = body.get("instagram_business_account") or {}
		if ig.get("id"):
			frappe.db.set_value("Shop", shop, {"ig_user_id": str(ig["id"]), "ig_username": ig.get("username") or ""}, update_modified=False)
		else:
			frappe.db.set_value("Shop", shop, {"ig_user_id": "", "ig_username": ""}, update_modified=False)
			warnings.append(_("Sahifaga Instagram professional akkaunt ulanmagan"))
	except MetaError as e:
		warnings.append(_("Instagram akkaunt olinmadi: {0}").format(e))

	if not user_token:
		warnings.append(_("Reklama kabineti qidirilmadi (token yo'q) — «Reklama kabineti» maydonini qo'lda to'ldiring"))
	else:
		try:
			accounts = _graph("GET", "me/adaccounts", user_token, fields="account_id,name,account_status", limit=100).get("data") or []
			active = [a for a in accounts if a.get("account_status") == 1 and a.get("account_id")]
			if len(active) == 1:
				frappe.db.set_value("Shop", shop, {"meta_ad_account": "act_" + str(active[0]["account_id"])}, update_modified=False)
			else:
				names = ", ".join(f"{a.get('name') or a['account_id']} (act_{a['account_id']})" for a in active)
				current = frappe.db.get_value("Shop", shop, "meta_ad_account")
				if not active:
					text = _("Faol reklama kabineti topilmadi")
				else:
					text = _("Bir nechta faol reklama kabineti bor: {0}").format(names)
				if not current:
					text += _(" — «Reklama kabineti» maydonini qo'lda to'ldiring")
				warnings.append(text)
		except MetaError as e:
			warnings.append(_("Reklama kabineti olinmadi: {0}").format(e))
	return " ".join(warnings) or None


def _subscribe_app():
	"""Ilovaning webhook obunasi (object=page, leadgen) — bir marta; Meta shu zahoti GET bilan manzilni tekshiradi."""
	conf = _conf()
	if not conf.verify:
		settings = frappe.get_single("Marketplace Settings")
		settings.save(ignore_permissions=True)
		conf = _conf()
	try:
		_graph(
			"POST", f"{conf.app_id}/subscriptions", f"{conf.app_id}|{conf.secret}", object="page",
			callback_url=callback_url(), fields="leadgen", verify_token=conf.verify, include_values="true",
		)
	except MetaError as e:
		return _("Webhook obunasi bo'lmadi ({0}) — lidlar baribir har 10 daqiqada tortib olinadi.").format(e)
	return None


@frappe.whitelist(methods=["POST"])
def disconnect(shop: str):
	_check(shop)
	try:
		page_id = frappe.db.get_value("Shop", shop, "meta_page_id")
		if page_id:
			_graph("DELETE", f"{page_id}/subscribed_apps", _page_token(shop))
	except MetaError:
		pass
	remove_encrypted_password("Shop", shop, "meta_page_token")
	frappe.db.set_value("Shop", shop, {"meta_page_id": None, "meta_page_name": None, "meta_page_token": None}, update_modified=False)
	_status(shop, _("uzildi"))
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def refresh_forms(shop: str):
	"""Do'kon egasi / admin: Meta'dagi yangi formalarni jadvalga olib keladi va oxirgi lidlarni tortib oladi."""
	_check(shop, owner_ok=True)
	try:
		saved = pull(shop)
	except MetaError as e:
		_status(shop, _("xato: {0}").format(e))
		frappe.throw(_("Meta: {0}").format(e))
	return {"forms": len(_rows(shop)), "saved": saved}
