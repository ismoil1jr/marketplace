"""Sotuv nazorati (Do'kon → Sotuv nazorati): do'kon egasi uchun lidlar va sotuv menejerlari ishining umumiy manzarasi.

Davr (dan — gacha) bo'yicha, shu davrda kelgan lidlar asosida:
* voronka: tushdi → bog'lanildi → rozi bo'ldi → buyurtma berdi → puli tushdi; holatlar; birinchi aloqagacha vaqt;
* kunlar bo'yicha grafik, kimlar sotib oldi, tovar va manba (reklama) bo'yicha;
* menejerlar: qo'ng'iroqlar, gaplashgan vaqt, natijalar, sotuvlar (shu davrdagi qo'ng'iroq va xulosalar);
* AI xulosalari (oxirgi qo'ng'iroqlar).
Hozirgi holat (davrga bog'liq emas): hali qo'ng'iroq qilinmagan lidlar, qayta qo'ng'iroq muddati kelganlar,
menejer hali gaplashmagan saytdagi buyurtmalar.

Ko'radi: do'kon egasi va do'kon menejeri (Shop Member: Ega / Menejer) hamda platforma admini (do'kon tanlab yoki
hammasi). Sotuv menejeri bu sahifani ko'rmaydi. Notanish (24 soat kutayotgan) qo'ng'iroqlar hisobga olinmaydi.
"""

import statistics
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, get_first_day, get_fullname, getdate, now_datetime, today

from marketplace.permissions import get_user_shop
from marketplace.reports import _is_admin, _pct, _shop_options
from marketplace.sotuv.telefoniya import normalize_phone

# Nazoratchi — faqat shu sahifa uchun berilgan rol (masalan CEO): ko'radi, hech narsani o'zgartirmaydi
OWNER_ROLES = ("Ega", "Menejer", "Nazoratchi")
STATES = ("Yangi", "Javob bermadi", "Keyinroq", "Oladi", "Olmaydi", "Buyurtma berdi")
CLOSED = ("Olmaydi", "Buyurtma berdi")
PAID, CANCELLED = "To'langan", "Bekor"
PHONE_SOURCE = "Qo‘ng‘iroq"  # menejer o'zi qo'shgan murojaat (mijoz to'g'ridan-to'g'ri qo'ng'iroq qilgan)
DAILY_MAX_DAYS = 62
LIST_LIMIT = 50


@frappe.whitelist()
def get_dashboard(from_date: str | None = None, to_date: str | None = None, shop: str | None = None):
	shop = _scope(shop)
	end = getdate(to_date or today())
	start = getdate(from_date) if from_date else get_first_day(end)
	if start > end:
		start, end = end, start
	if (end - start).days > 366 * 3:
		frappe.throw(_("Davr 3 yildan oshmasin"))
	days = (end - start).days + 1
	prev_end = start - timedelta(days=1)
	prev_start = prev_end - timedelta(days=days - 1)

	leads = _leads(shop, start, end)
	orders = _orders([lead.buyurtma for lead in leads if lead.buyurtma])
	calls = _lead_calls(shop, leads)
	summary = _summary(leads, orders, calls)
	prev_leads = _leads(shop, prev_start, prev_end)
	prev = _summary(prev_leads, *_with_orders(prev_leads)[1:], _lead_calls(shop, prev_leads))
	summary["change"] = {k: _pct(summary[k], prev[k]) for k in ("leads", "ordered", "revenue")}
	summary["conversion_change"] = round(summary["conversion"] - prev["conversion"], 1) if prev["leads"] else None
	summary.update(_response_time(leads, calls))

	return {
		"shop": shop,
		"shop_name": frappe.db.get_value("Shop", shop, "shop_name") if shop else None,
		"from_date": str(start),
		"to_date": str(end),
		"days": days,
		"is_admin": _is_admin(),
		"shops": _shop_options() if _is_admin() else [],
		"summary": summary,
		"states": _states(leads),
		"series": _series(leads, start, end),
		"bought": _bought(leads, orders),
		"waiting": _waiting(shop),
		"managers": _managers(shop, start, end),
		"items": _by_item(leads, orders),
		"sources": _by_source(leads),
		"calls": _recent_calls(shop, start, end),
	}


# ---------------- Kim ko'radi ----------------


def _scope(shop):
	"""Admin — tanlagan do'kon (yoki do'kon panelidagi do'kon, yoki hammasi). Do'kon a'zosi — faqat o'z do'koni va
	faqat Ega / Menejer / Nazoratchi bo'lsa: Xodim, sotuv menejeri, kuryer bu sahifani ochmaydi."""
	if _is_admin():
		if shop and not frappe.db.exists("Shop", shop):
			frappe.throw(_("Do'kon topilmadi"))
		return shop or get_user_shop() or None
	own = get_user_shop()
	role = own and frappe.db.get_value("Shop Member", {"parent": own, "parenttype": "Shop", "user": frappe.session.user}, "role")
	if role not in OWNER_ROLES:
		frappe.throw(_("Sotuv nazorati faqat do'kon egasi, menejeri va nazoratchisi uchun"), frappe.PermissionError)
	return own


def _shop_filter(shop):
	return {"shop": shop} if shop else {}


def _between(start, end):
	return ["between", [f"{start} 00:00:00", f"{end} 23:59:59.999999"]]


# ---------------- Lidlar va ulardan buyurtmalar ----------------


def _leads(shop, start, end):
	return frappe.get_all(
		"Murojaat",
		filters={**_shop_filter(shop), "creation": _between(start, end)},
		fields=["name", "creation", "holat", "mijoz_ismi", "telefon", "normal_telefon", "tovar", "tovar_nomi", "manba",
		        "kampaniya", "menejer", "buyurtma", "shop"],
		order_by="creation asc",
		limit_page_length=0,
	)


def _orders(names):
	if not names:
		return {}
	return {
		o.name: o
		for o in frappe.get_all(
			"Sales Order", filters={"name": ["in", list(set(names))]},
			fields=["name", "grand_total", "payment_status", "payment_method", "docstatus", "creation", "per_delivered"],
			limit_page_length=0,
		)
	}


def _with_orders(leads):
	return leads, _orders([lead.buyurtma for lead in leads if lead.buyurtma])


def _alive(o):
	return bool(o and o.docstatus == 1 and o.payment_status != CANCELLED)


def _paid(o):
	return _alive(o) and o.payment_status == PAID


def _contacted(lead, calls):
	"""Menejer mijoz bilan bog'langanmi: natija yozgan, qo'ng'iroq bo'lgan yoki lidni qo'ng'iroqdan keyin o'zi qo'shgan."""
	return lead.holat != "Yangi" or lead.name in calls or lead.manba == PHONE_SOURCE


def _summary(leads, orders, calls):
	total = len(leads)
	ordered = [lead for lead in leads if lead.holat == "Buyurtma berdi"]
	alive = [orders.get(lead.buyurtma) for lead in ordered if _alive(orders.get(lead.buyurtma))]
	paid = [o for o in alive if _paid(o)]
	return {
		"leads": total,
		"contacted": sum(1 for lead in leads if _contacted(lead, calls)),
		"agreed": sum(1 for lead in leads if lead.holat in ("Oladi", "Buyurtma berdi")),
		"ordered": len(ordered),
		"paid": len(paid),
		"conversion": round(len(ordered) * 100 / total, 1) if total else 0,
		"revenue": flt(sum(o.grand_total for o in alive)),
		"paid_amount": flt(sum(o.grand_total for o in paid)),
		"waiting_amount": flt(sum(o.grand_total for o in alive if not _paid(o))),
	}


def _states(leads):
	counts = {s: 0 for s in STATES}
	for lead in leads:
		counts[lead.holat if lead.holat in counts else "Yangi"] += 1
	return [{"state": s, "count": counts[s]} for s in STATES]


def _lead_calls(shop, leads):
	"""{lid nomi: birinchi qo'ng'iroq vaqti} — lidga biriktirilgan yoki shu raqam bilan lid kelgandan keyin bo'lgan
	qo'ng'iroqlar (notanish qo'ng'iroqlar hisobga olinmaydi)."""
	if not leads:
		return {}
	names = [lead.name for lead in leads]
	phones = list({lead.normal_telefon for lead in leads if lead.normal_telefon})
	rows = frappe.get_all(
		"Telefon Qongiroq",
		filters={**_shop_filter(shop), "notanish": 0, "boshlandi": [">=", min(lead.creation for lead in leads) - timedelta(days=1)]},
		or_filters=[["murojaat", "in", names]] + ([["normal_telefon", "in", phones]] if phones else []),
		fields=["murojaat", "normal_telefon", "boshlandi"], limit_page_length=0,
	)
	by_lead, by_phone = {}, {}
	for c in rows:
		t = get_datetime(c.boshlandi)
		if c.murojaat:
			by_lead.setdefault(c.murojaat, []).append(t)
		if c.normal_telefon:
			by_phone.setdefault(c.normal_telefon, []).append(t)
	out = {}
	for lead in leads:
		created = get_datetime(lead.creation)
		times = by_lead.get(lead.name, []) + [t for t in by_phone.get(lead.normal_telefon, []) if t >= created]
		if times:
			out[lead.name] = min(times)
	return out


def _response_time(leads, calls):
	"""Lid kelgandan menejer birinchi bog'langangacha (qo'ng'iroq yoki natija yozilishi): mediana, daqiqada.
	Menejer o'zi qo'shgan lid (mijoz o'zi qo'ng'iroq qilgan) hisobga olinmaydi — u yerda aloqa lid'dan oldin bo'lgan."""
	pool = [lead for lead in leads if lead.manba != PHONE_SOURCE]
	empty = {"response_median": None, "response_hour_pct": None, "response_count": 0}
	if not pool:
		return empty
	first = {}
	for r in frappe.get_all("Menejer Xulosasi", filters={"murojaat": ["in", [lead.name for lead in pool]]},
	                        fields=["murojaat", "creation"], limit_page_length=0):
		t = get_datetime(r.creation)
		first[r.murojaat] = min(first.get(r.murojaat, t), t)
	minutes = []
	for lead in pool:
		created = get_datetime(lead.creation)
		times = [t for t in (first.get(lead.name), calls.get(lead.name)) if t and t >= created]
		if times:
			minutes.append((min(times) - created).total_seconds() / 60)
	if not minutes:
		return empty
	return {
		"response_median": round(statistics.median(minutes)),
		"response_hour_pct": round(sum(1 for m in minutes if m <= 60) * 100 / len(minutes)),
		"response_count": len(minutes),
	}


def _series(leads, start, end):
	"""Kunlar (62 kungacha) yoki oylar bo'yicha: nechta lid tushdi va ulardan nechtasi sotib oldi."""
	daily = (end - start).days + 1 <= DAILY_MAX_DAYS
	points, index = [], {}
	cursor = start
	while cursor <= end:
		if daily:
			key, nxt = str(cursor), cursor + timedelta(days=1)
			frm, to = cursor, cursor
		else:
			frm = cursor
			nxt = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
			to = min(nxt - timedelta(days=1), end)
			key = cursor.strftime("%Y-%m")
		index[key] = len(points)
		points.append({"from": str(frm), "to": str(to), "leads": 0, "ordered": 0})
		cursor = nxt
	for lead in leads:
		d = getdate(lead.creation)
		p = points[index[str(d) if daily else d.strftime("%Y-%m")]]
		p["leads"] += 1
		if lead.holat == "Buyurtma berdi":
			p["ordered"] += 1
	return {"unit": "day" if daily else "month", "points": points}


def _bought(leads, orders):
	"""Shu davrda kelgan lidlardan kimlar buyurtma berdi — oxirgisi birinchi."""
	rows = []
	names = {}
	for lead in leads:
		if lead.holat != "Buyurtma berdi":
			continue
		o = orders.get(lead.buyurtma)
		if lead.menejer and lead.menejer not in names:
			names[lead.menejer] = get_fullname(lead.menejer)
		rows.append({
			"lead": lead.name, "mijoz": lead.mijoz_ismi, "telefon": lead.telefon, "tovar": lead.tovar_nomi,
			"manba": lead.manba, "buyurtma": lead.buyurtma, "summa": flt(o.grand_total) if o else 0,
			"tolov": _pay_state(o), "usul": o.payment_method if o else None,
			"sana": str(o.creation if o else lead.creation), "menejer": names.get(lead.menejer),
		})
	rows.sort(key=lambda r: r["sana"], reverse=True)
	return {"count": len(rows), "rows": rows[:LIST_LIMIT]}


def _pay_state(o):
	if not o:
		return "Buyurtma yo'q"
	if not _alive(o):
		return "Bekor"
	return "To'langan" if o.payment_status == PAID else "To'lov kutilmoqda"


def _by_item(leads, orders):
	"""Qaysi tovar (reklama Tovar ID'si) bo'yicha nechta lid va nechtasi sotib oldi."""
	groups = {}
	for lead in leads:
		g = groups.setdefault(lead.tovar or "", {"tovar": lead.tovar, "name": lead.tovar_nomi or None, "leads": 0, "ordered": 0, "revenue": 0.0})
		g["leads"] += 1
		if lead.holat == "Buyurtma berdi":
			g["ordered"] += 1
			if _alive(orders.get(lead.buyurtma)):
				g["revenue"] += flt(orders[lead.buyurtma].grand_total)
	codes = [k for k in groups if k]
	meta = {r.name: r for r in frappe.get_all("Item", filters={"name": ["in", codes or [""]]},
	                                          fields=["name", "item_name", "image", "mp_tovar_id"])}
	out = []
	for code, g in groups.items():
		m = meta.get(code)
		out.append({**g, "name": (m.item_name if m else None) or g["name"], "image": m.image if m else None,
		            "tid": m.mp_tovar_id if m else None,
		            "conversion": round(g["ordered"] * 100 / g["leads"], 1) if g["leads"] else 0})
	return sorted(out, key=lambda r: (-r["leads"], -r["ordered"]))[:20]


def _by_source(leads):
	"""Manba (Instagram, Facebook, sayt, qo'ng'iroq) va reklama kampaniyasi bo'yicha."""
	def group(key):
		g = {}
		for lead in leads:
			name = (lead.get(key) or "").strip()
			if key == "kampaniya" and not name:
				continue
			row = g.setdefault(name or "Boshqa", {"name": name or "Boshqa", "leads": 0, "ordered": 0})
			row["leads"] += 1
			row["ordered"] += lead.holat == "Buyurtma berdi"
		return sorted(g.values(), key=lambda r: -r["leads"])

	return {"manba": group("manba"), "kampaniya": group("kampaniya")[:10]}


# ---------------- Hozir kutayotganlar ----------------


def _waiting(shop):
	from marketplace.sotuv.api import _filters as order_filters

	base = _shop_filter(shop)
	fields = ["name", "creation", "mijoz_ismi", "telefon", "tovar_nomi", "manba", "holat", "keyingi_qongiroq", "menejer"]
	fresh = frappe.get_all("Murojaat", filters={**base, "holat": "Yangi"}, fields=[*fields, "normal_telefon"], order_by="creation asc",
	                       limit_page_length=0)
	called = _lead_calls(shop, fresh)
	new = [r for r in fresh if r.name not in called and r.manba != PHONE_SOURCE]
	no_result = [r for r in fresh if r.name in called or r.manba == PHONE_SOURCE]
	for r in no_result:
		r.qongiroq = str(called[r.name]) if r.name in called else None
	callback_filters = {**base, "keyingi_qongiroq": ["<=", today()], "holat": ["not in", CLOSED]}
	callbacks = frappe.get_all("Murojaat", filters=callback_filters, fields=fields, order_by="keyingi_qongiroq asc, creation asc",
	                           limit_page_length=LIST_LIMIT)
	users = {r.menejer for r in callbacks if r.menejer}
	names = {u: get_fullname(u) for u in users}
	for r in callbacks:
		r.menejer_ismi = names.get(r.menejer)
	site = order_filters("yangi", shop)
	if not shop:
		site.pop("shop", None)
	oldest = new[0].creation if new else None
	return {
		"new_count": len(new),
		"new_oldest_minutes": round((now_datetime() - get_datetime(oldest)).total_seconds() / 60) if oldest else None,
		"new": new[:LIST_LIMIT],
		"no_result_count": len(no_result),
		"no_result": sorted(no_result, key=lambda r: r.creation, reverse=True)[:LIST_LIMIT],
		"callback_count": frappe.db.count("Murojaat", callback_filters),
		"callback_overdue": frappe.db.count("Murojaat", {**callback_filters, "keyingi_qongiroq": ["<", today()]}),
		"callbacks": callbacks,
		"site_orders": frappe.db.count("Sales Order", site),
		"now": str(now_datetime()),
		"today": today(),
	}


# ---------------- Menejerlar ----------------


def _managers(shop, start, end):
	"""Har bir menejer shu davrda: qo'ng'iroqlar, gaplashgan vaqt, yozgan natijalari, tasdiqlagan buyurtmalari."""
	base = _shop_filter(shop)
	people = {}

	def row(user):
		return people.setdefault(user, {"user": user, "name": get_fullname(user), "calls": 0, "answered": 0, "talk": 0,
		                                "results": 0, "oladi": 0, "olmaydi": 0, "javob_bermadi": 0, "keyinroq": 0,
		                                "sales": 0, "sales_amount": 0.0, "paid_amount": 0.0, "contacts": set()})

	members = frappe.get_all("Shop Member", filters={"role": "Sotuv menejer", "parenttype": "Shop", **({"parent": shop} if shop else {})}, pluck="user")
	for user in members:
		row(user)
	for c in frappe.get_all("Telefon Qongiroq", filters={**base, "notanish": 0, "boshlandi": _between(start, end)},
	                        fields=["menejer", "davomiyligi", "natija", "normal_telefon"], limit_page_length=0):
		if not c.menejer:
			continue
		r = row(c.menejer)
		r["calls"] += 1
		if c.normal_telefon:
			r["contacts"].add(c.normal_telefon)
		if cint(c.davomiyligi) > 0 and c.natija != "Javob yo'q":
			r["answered"] += 1
			r["talk"] += cint(c.davomiyligi)
	sold = {}
	keys = {"Oladi": "oladi", "Olmaydi": "olmaydi", "Javob bermadi": "javob_bermadi", "Keyinroq": "keyinroq"}
	for lg in frappe.get_all("Menejer Xulosasi", filters={**base, "creation": _between(start, end)},
	                         fields=["menejer", "natija", "murojaat", "buyurtma", "telefon"], limit_page_length=0):
		if not lg.menejer:
			continue
		r = row(lg.menejer)
		r["results"] += 1
		if lg.natija in keys:
			r[keys[lg.natija]] += 1
		r["contacts"].add(normalize_phone(lg.telefon) or lg.murojaat or lg.buyurtma)
		if lg.natija == "Oladi" and lg.buyurtma:
			sold.setdefault(lg.menejer, set()).add(lg.buyurtma)
	orders = _orders([name for names in sold.values() for name in names])
	for user, names in sold.items():
		alive = [orders[n] for n in names if _alive(orders.get(n))]
		people[user]["sales"] = len(alive)
		people[user]["sales_amount"] = flt(sum(o.grand_total for o in alive))
		people[user]["paid_amount"] = flt(sum(o.grand_total for o in alive if _paid(o)))
	out = []
	for r in people.values():
		contacts = len(r.pop("contacts") - {None})
		r["contacts"] = contacts
		r["conversion"] = round(r["sales"] * 100 / contacts, 1) if contacts else 0
		out.append(r)
	return sorted(out, key=lambda r: (-r["sales_amount"], -r["calls"], r["name"] or ""))


# ---------------- Oxirgi qo'ng'iroqlar va AI xulosalari ----------------


def _recent_calls(shop, start, end):
	"""Shu davrdagi oxirgi qo'ng'iroqlar — yozuvi (tinglash) va AI holati bilan: xulosa, jarayonda, navbatda, xato (sababi),
	juda qisqa. Xulosasi yo'q qo'ng'iroq ham ko'rinadi: rahbar «qo'ng'iroq bo'lmagan» deb o'ylamasin."""
	from marketplace.sotuv.stt import blockers, settings

	base = {**_shop_filter(shop), "notanish": 0, "boshlandi": _between(start, end)}
	rows = frappe.get_all(
		"Telefon Qongiroq", filters=base,
		fields=["name", "boshlandi", "davomiyligi", "yonalish", "menejer", "mijoz_ismi", "telefon", "yozuv", "holat",
		        "ai_xulosa", "xato_matni", "stt_urinish", "murojaat", "buyurtma"],
		order_by="boshlandi desc", limit_page_length=12,
	)
	off = blockers()
	cfg = settings()
	min_sec = max(cint(cfg.stt_min_sekund), 1)
	names = {u: get_fullname(u) for u in {r.menejer for r in rows if r.menejer}}
	for r in rows:
		r.menejer_ismi = names.get(r.menejer)
		r.ai = (
			"tayyor" if r.ai_xulosa else
			"yozuvsiz" if not r.yozuv else
			"jarayonda" if r.holat == "Transkripsiya" else
			"qisqa" if cint(r.davomiyligi) < min_sec else
			"xato" if r.holat == "Xato" else
			"ochiq" if off else
			"navbatda"
		)
	return {
		"rows": rows,
		"total": frappe.db.count("Telefon Qongiroq", base),
		"recorded": frappe.db.count("Telefon Qongiroq", {**base, "yozuv_bor": 1}),
		"transcribed": frappe.db.count("Telefon Qongiroq", {**base, "ai_xulosa": ["is", "set"]}),
		"failed": frappe.db.count("Telefon Qongiroq", {**base, "holat": "Xato", "ai_xulosa": ["is", "not set"]}),
		"blockers": off,
	}
