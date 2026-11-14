"""Sotuvchining oddiy ERPNext Desk'dagi joyi.

* Desktop'da faqat o'z do'koni ikonkasi (nomi va logosi bilan) chiqadi, ERPNext ikonkasi yashiriladi.
* Ikonka "Do'konim" workspace'ini ochadi: oylik kirim/chiqim bloki, balans kartalari va tovar qo'shish,
  buyurtmalar tugmalari.
* Workspace va kartalar hamma sotuvchiga bitta. Har kim faqat o'z do'koni raqamlarini ko'radi,
  chunki kartalar va ro'yxatlar User Permission (Shop / Warehouse) bilan filtrlanadi.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from marketplace.marketplace.doctype.rang.rang import color_names, remember_shop_colors, shop_colors, shop_hexes
from marketplace.permissions import get_user_shop

WORKSPACE = "Dokonim"
COURIER_WORKSPACE = "Kuryer"
SELLER_ROLE = "Shop Seller"

# Workspace'dagi raqamli kartalar: (nom, doctype, funksiya, maydon, filtrlar, rang)
NUMBER_CARDS = [
	("Do'kon: To'langan summa", "Sales Order", "Sum", "grand_total",
		[["docstatus", "=", 1], ["payment_status", "=", "To'langan"]], "#16a34a"),
	("Do'kon: To'lov kutilmoqda", "Sales Order", "Count", None,
		[["docstatus", "=", 1], ["payment_status", "=", "Kutilmoqda"]], "#d97706"),
	("Do'kon: Bekor qilingan", "Sales Order", "Count", None,
		[["payment_status", "=", "Bekor"]], "#dc2626"),
	("Do'kon: Tovarlar", "Item", "Count", None,
		[["disabled", "=", 0], ["variant_of", "is", "not set"]], "#2563eb"),
	("Do'kon: Kuryerlardagi naqd", "Sales Order", "Sum", "grand_total",
		[["docstatus", "=", 1], ["mp_cash_status", "in", ["Kuryerda", "Topshirilmoqda"]]], "#ea580c"),
]

# Kuryer paneli kartalari: ro'yxat kuryerga faqat o'zinikini beradi (permissions.sales_order_query)
COURIER_CARDS = [
	# Son ro'yxatning o'zidan (kuryer.active_count): tasdiqlangan yoki onlayn to'langan, kuryer bilan, hali topshirilmagan
	("Kuryer: Yetkazilishi kerak", "Sales Order", "marketplace.kuryer.active_count", None, None, "#2563eb"),
	("Kuryer: Qo'limdagi naqd", "Sales Order", "Sum", "grand_total",
		[["docstatus", "=", 1], ["mp_cash_status", "=", "Kuryerda"]], "#ea580c"),
	("Kuryer: Doimiy mijozlar", "Doimiy Mijoz", "Count", None, [], "#16a34a"),
]


def _is_seller():
	"""Do'kon egasi/xodimi yoki kuryer (platforma admini emas)."""
	from marketplace.permissions import is_courier, is_packer

	if frappe.session.user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles())
	return (SELLER_ROLE in roles and not roles & {"System Manager", "Marketplace Manager"}) or is_courier() or is_packer()


def _shop_boot(shop, admin_view=False):
	from marketplace.permissions import is_courier, is_packer

	shop = frappe.get_cached_doc("Shop", shop)
	return {
		"name": shop.name,
		"shop_name": shop.shop_name,
		"url": f"/s/{shop.name}",
		# Tovar formasi do'kon shabloniga moslanadi (item_seller.js): vitrina / story / katalog
		"layout": shop.layout_style or "vitrina",
		"admin_view": int(admin_view),
		"courier": int(not admin_view and is_courier() and frappe.session.user != "Administrator"),
		"packer": int(not admin_view and is_packer() and frappe.session.user != "Administrator"),
	}


def _is_sales_manager():
	"""Do'konning sotuv menejeri (Shop Member: "Sotuv menejer") — faqat Sotuv paneli."""
	from marketplace.setup import SALES_ROLE

	if frappe.session.user in ("Administrator", "Guest"):
		return False
	roles = set(frappe.get_roles())
	return SALES_ROLE in roles and not roles & {SELLER_ROLE, "System Manager", "Marketplace Manager"}


def boot_session(bootinfo):
	"""Sotuvchi Desk'i (load_desktop_data'dan keyin ishlaydi): Desktop'da faqat o'z do'koni ikonkasi.
	Sotuv menejeriga ham o'z do'koni ikonkasi, u to'g'ri Sotuv paneliga olib boradi.

	Frappe bu natijani foydalanuvchi bo'yicha keshlaydi. Adminniki esa sessiyaga bog'liq ("Do'kon paneliga
	kirish" faqat o'sha brauzerda) — u extend_bootinfo'da har safar hisoblanadi."""
	sales = _is_sales_manager()
	if not (sales or _is_seller()):
		return
	shop = get_user_shop()
	if not shop:
		return
	bootinfo.marketplace_shop = _shop_boot(shop)

	if sales:
		route = "/desk/sotuv-paneli"
	elif bootinfo.marketplace_shop["packer"]:
		route = "/desk/upakovka"
	else:
		# Workspace hali yaratilmagan bo'lsa (migrate qilinmagan), ikonkani o'zgartirmaymiz
		workspace = COURIER_WORKSPACE if bootinfo.marketplace_shop["courier"] else WORKSPACE
		if not frappe.db.exists("Workspace", workspace):
			return
		route = f"/desk/{frappe.scrub(workspace).replace('_', '-')}"
	shop = frappe.get_cached_doc("Shop", shop)
	for app in bootinfo.get("app_data") or []:
		if app.get("app_name") == "marketplace":
			app.update(
				app_title=shop.shop_name,
				app_logo_url=shop.logo or app.get("app_logo_url"),
				app_route=route,
				on_apps_screen=True,
			)
		else:
			# ERPNext va boshqa ilovalar ikonkasi sotuvchiga kerak emas
			app["on_apps_screen"] = False


def extend_bootinfo(bootinfo):
	"""Platforma admini — har bir sessiyada (Frappe keshlamaydi):
	* Desktop'da faqat "Marketplace" ikonkasi (ERPNext, Framework sahifalari qidiruv orqali ochiladi).
	* "Do'kon paneliga kirish" bosilgan bo'lsa — shu sessiyada sotuvchi paneli o'sha do'kon bo'yicha (admin_view),
	  aks holda "Do'konim" menyusi umuman ko'rinmaydi. Boshqa brauzer/sessiyaga bu belgi o'tmaydi."""
	from marketplace.permissions import admin_view_shop

	if frappe.session.user == "Guest":
		return
	# Sayt manzili (host_name): IP orqali kirilganda ham Payme/Click manzillari va do'kon havolasi domen bilan chiqsin
	bootinfo.marketplace_site_url = frappe.utils.get_url()
	if _is_seller():
		return
	if not {"System Manager", "Marketplace Manager"} & set(frappe.get_roles()):
		return
	for app in bootinfo.get("app_data") or []:
		app["on_apps_screen"] = app.get("app_name") == "marketplace"
	shop = admin_view_shop()
	if shop and frappe.db.exists("Shop", shop):
		bootinfo.marketplace_shop = _shop_boot(shop, admin_view=True)
	else:
		bootinfo.pop("marketplace_shop", None)
		hide_seller_shell(bootinfo)


def hide_seller_shell(bootinfo):
	"""Admin (Administrator'da hamma rollar bor) "Do'konim"ni ko'rmasin: unga Marketplace yetarli."""
	(bootinfo.get("module_sidebars") or {}).pop("Dokon", None)
	workspaces = bootinfo.get("workspaces") or {}
	if workspaces.get("pages"):
		workspaces["pages"] = [p for p in workspaces["pages"] if p.get("name") not in (WORKSPACE, COURIER_WORKSPACE)]


def notify_new_order(doc, method=None):
	"""Sales Order submit bo'lganda do'kon a'zolariga xabar."""
	if doc.get("shop"):
		amount = frappe.utils.fmt_money(doc.grand_total, currency=doc.currency)
		notify_shop(doc, _("Yangi buyurtma {0}: {1} — {2}").format(doc.name, doc.customer_name, amount))


def notify_shop(doc, subject):
	"""Do'kon a'zolariga (kuryerdan tashqari): qo'ng'iroqcha (Notification Log) + ochiq Desk'da ovoz va ekrandagi xabar.
	Kuryer buyurtmani menejer tasdiqlaganda oladi (notify_couriers)."""
	_notify_users(doc, subject, {"role": ["!=", "Kuryer"]})


def notify_couriers(doc):
	"""Menejer mijoz bilan gaplashib "Oladi" deb tasdiqlagan yetkazish — do'kon kuryerlariga (sotuv/api.save_result)."""
	from marketplace.upakovka import notify_packers

	subject = _("Yetkazish {0}: {1} — {2}").format(doc.name, doc.customer_name, doc.get("delivery_address") or _("manzil yo'q"))
	_notify_users(doc, subject, {"role": "Kuryer"})
	# Upakovkachi ham shu paytdan boshlab buyurtmani yig'ib qo'yadi (kuryer kelguncha tayyor bo'lsin)
	notify_packers(doc)


def _notify_users(doc, subject, member_filters):
	users = set(frappe.get_all("Shop Member", filters={"parent": doc.shop, "parenttype": "Shop", **member_filters}, pluck="user"))
	for user in users:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Sales Order",
				"document_name": doc.name,
				"subject": subject,
			}
		).insert(ignore_permissions=True)
		frappe.publish_realtime(
			"marketplace_new_order", {"name": doc.name, "subject": subject}, user=user, after_commit=True
		)


SITE_BLOCK = "Mening saytim"

SITE_BLOCK_HTML = """
<div class="site">
	<div>
		<div class="label">Mening saytim</div>
		<a class="url" target="_blank" rel="noopener"></a>
		<div class="hint">Shu havolani Instagram profilingizga (bio) qo'ying</div>
	</div>
	<div class="actions">
		<button class="copy" type="button">Nusxalash</button>
		<a class="open" target="_blank" rel="noopener">Saytni ochish ↗</a>
	</div>
</div>
"""

SITE_BLOCK_CSS = """
.site { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
	padding: 16px 20px; border-radius: 12px; background: var(--subtle-fg, #f3f5f7); }
.label { font-size: 12px; color: var(--text-muted, #6b7280); }
.url { display: block; font-size: 18px; font-weight: 600; color: var(--text-color, #111); word-break: break-all; }
.hint { font-size: 12px; color: var(--text-muted, #6b7280); margin-top: 2px; }
.actions { display: flex; gap: 8px; }
.copy, .open { height: 34px; padding: 0 14px; border-radius: 8px; font-size: 13px; cursor: pointer; text-decoration: none;
	display: inline-flex; align-items: center; border: 1px solid var(--border-color, #d1d5db); background: var(--fg-color, #fff); color: var(--text-color, #111); }
.open { background: #171717; color: #fff; border-color: #171717; }
"""

SITE_BLOCK_JS = """
const shop = frappe.boot.marketplace_shop;
const url = shop ? location.origin + shop.url : "";
root_element.querySelector(".url").textContent = url || "Do'kon biriktirilmagan";
root_element.querySelector(".url").href = url;
root_element.querySelector(".open").href = url;
root_element.querySelector(".copy").addEventListener("click", () => {
	frappe.utils.copy_to_clipboard(url);
});
"""


MONTH_BLOCK = "Oylik kirim va chiqim"

MONTH_BLOCK_HTML = """
<div class="month">
	<div class="head">
		<button class="nav" type="button" data-step="-1" aria-label="Oldingi oy">‹</button>
		<div class="title"></div>
		<button class="nav" type="button" data-step="1" aria-label="Keyingi oy">›</button>
		<a class="more" href="/desk/hisobot">Batafsil hisobot →</a>
	</div>
	<div class="cards">
		<div class="card">
			<div class="label">Kirim</div>
			<div class="value in" data-k="income">—</div>
			<div class="hint" data-k="income_hint">sotuvdan tushgan pul</div>
		</div>
		<div class="card">
			<div class="label">Chiqim</div>
			<div class="value out" data-k="expense">—</div>
			<div class="hint" data-k="expense_hint">omborga tovar olishga ketgan pul</div>
			<div class="hint warn" data-k="unpriced" hidden></div>
		</div>
		<div class="card">
			<div class="label">Farq</div>
			<div class="value" data-k="profit">—</div>
			<div class="hint">kirim − chiqim</div>
		</div>
	</div>
</div>
"""

MONTH_BLOCK_CSS = """
.month { padding: 16px 20px; border-radius: 12px; border: 1px solid var(--border-color, #e5e7eb); background: var(--card-bg, #fff); }
.head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.title { min-width: 130px; text-align: center; font-size: 16px; font-weight: 600; color: var(--heading-color, #111); }
.nav { display: inline-grid; place-items: center; width: 30px; height: 30px; padding: 0 0 2px; border-radius: 8px;
	border: 1px solid var(--border-color, #d1d5db); background: var(--fg-color, #fff);
	color: var(--text-color, #111); font: inherit; font-size: 18px; line-height: 1; cursor: pointer; }
.nav:disabled { opacity: .35; cursor: default; }
.more { margin-left: auto; font-size: 13px; color: var(--text-muted, #6b7280); text-decoration: none; }
.cards { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.card { padding: 12px 14px; border-radius: 10px; background: var(--subtle-fg, #f3f5f7); min-width: 0; }
.label { font-size: 12px; font-weight: 600; color: var(--text-muted, #6b7280); text-transform: uppercase; letter-spacing: .03em; }
.value { margin-top: 4px; font-size: 22px; font-weight: 700; color: var(--heading-color, #111); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.value.in { color: var(--green-600, #16a34a); }
.value.out, .value.minus { color: var(--red-600, #dc2626); }
.hint { margin-top: 2px; font-size: 12px; color: var(--text-muted, #6b7280); }
.hint.warn { color: var(--orange-600, #d97706); }
@media (max-width: 640px) {
	.cards { grid-template-columns: 1fr; }
	.more { display: none; }
}
"""

MONTH_BLOCK_JS = """
const MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
const el = (s) => root_element.querySelector(s);
const key = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
const money = (v) => `${format_number(v || 0, null, 0)} so‘m`;
const now = new Date();
let cur = new Date(now.getFullYear(), now.getMonth(), 1);

async function load() {
	const month = key(cur);
	el(".title").textContent = `${MONTHS[cur.getMonth()]} ${cur.getFullYear()}`;
	el('[data-step="1"]').disabled = month === key(now);
	const d = await frappe.xcall("marketplace.reports.get_month_summary", { month });
	if (month !== key(cur)) return; // oy tez almashtirilsa, eski javob yozilmasin
	el('[data-k="income"]').textContent = money(d.income);
	el('[data-k="income_hint"]').textContent = `sotuvdan tushgan pul · ${d.orders} ta buyurtma`;
	el('[data-k="expense"]').textContent = money(d.expense);
	el('[data-k="expense_hint"]').textContent = `tovar olishga ketgan pul · ${d.receipts} ta kirim, ${format_number(d.received_qty, null, 0)} dona`;
	// Narx majburiy bo'lishidan oldingi kirimlar chiqimga qo'shilmaydi — buni ochiq aytamiz
	const unpriced = el('[data-k="unpriced"]');
	unpriced.hidden = !d.unpriced_qty;
	unpriced.textContent = `${format_number(d.unpriced_qty, null, 0)} donasi narxsiz kiritilgan (eski kirim) — chiqimga qo'shilmagan`;
	const profit = el('[data-k="profit"]');
	profit.textContent = money(d.profit);
	profit.classList.toggle("in", d.profit > 0);
	profit.classList.toggle("minus", d.profit < 0);
}

root_element.querySelectorAll(".nav").forEach((b) =>
	b.addEventListener("click", () => {
		cur = new Date(cur.getFullYear(), cur.getMonth() + Number(b.dataset.step), 1);
		load();
	})
);
load();
"""


CASH_BLOCK = "Naqd pul"

CASH_BLOCK_HTML = """
<div class="cash">
	<div class="cards">
		<div class="card"><div class="label">Do'kon kassasida</div><div class="value in" data-k="kassa">—</div><div class="hint" data-k="kassa_hint">naqd, qo'lingizda</div></div>
		<div class="card"><div class="label">Kuryerlarda</div><div class="value warn" data-k="in_couriers">—</div><div class="hint">mijozdan olingan, hali topshirilmagan</div></div>
		<div class="card"><div class="label">Tasdiq kutmoqda</div><div class="value" data-k="pending">—</div><div class="hint">kuryer topshirdi — «Qabul qildim» bosing</div></div>
		<div class="card"><div class="label">Onlayn (Payme/Click)</div><div class="value" data-k="online">—</div><div class="hint">kartaga tushgan</div></div>
	</div>
	<div class="couriers"></div>
</div>
"""

CASH_BLOCK_CSS = """
.cash { padding: 16px 20px; border-radius: 12px; border: 1px solid var(--border-color, #e5e7eb); background: var(--card-bg, #fff); }
.cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.card { padding: 12px 14px; border-radius: 10px; background: var(--subtle-fg, #f3f5f7); min-width: 0; }
.label { font-size: 12px; font-weight: 600; color: var(--text-muted, #6b7280); text-transform: uppercase; letter-spacing: .03em; }
.value { margin-top: 4px; font-size: 20px; font-weight: 700; color: var(--heading-color, #111); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.value.in { color: var(--green-600, #16a34a); }
.value.warn { color: var(--orange-600, #ea580c); }
.hint { margin-top: 2px; font-size: 12px; color: var(--text-muted, #6b7280); }
.couriers { margin-top: 12px; display: grid; gap: 8px; }
.courier { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; border: 1px solid var(--border-color, #e5e7eb); }
.courier.is-sent { border-color: var(--orange-400, #fb923c); background: var(--bg-orange, #fff7ed); }
.who { font-weight: 600; color: var(--heading-color, #111); }
.amounts { flex: 1; font-size: 13px; color: var(--text-muted, #6b7280); }
.amounts b { color: var(--text-color, #111); }
.accept { height: 32px; padding: 0 14px; border-radius: 8px; border: 0; background: var(--green-600, #16a34a); color: #fff; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.accept:disabled { opacity: .5; cursor: default; }
.list { font-size: 13px; color: var(--text-muted, #6b7280); text-decoration: none; }
.empty { font-size: 13px; color: var(--text-muted, #6b7280); }
@media (max-width: 760px) { .cards { grid-template-columns: 1fr 1fr; } }
"""

CASH_BLOCK_JS = """
const el = (s) => root_element.querySelector(s);
const esc = frappe.utils.escape_html;
const money = (v) => `${format_number(v || 0, null, 0)} so‘m`;

async function load() {
	const d = await frappe.xcall("marketplace.kassa.cash_summary");
	el('[data-k="kassa"]').textContent = money(d.kassa);
	el('[data-k="kassa_hint"]').textContent = `naqd, qo'lingizda · ${d.kassa_count} ta buyurtma`;
	el('[data-k="in_couriers"]').textContent = money(d.in_couriers);
	el('[data-k="pending"]').textContent = money(d.pending);
	el('[data-k="online"]').textContent = money(d.online);
	const box = el(".couriers");
	if (!d.couriers.length) {
		box.innerHTML = `<div class="empty">Kuryerlarda pul yo'q — hammasi kassada.</div>`;
		return;
	}
	box.innerHTML = d.couriers.map((c, i) => `
		<div class="courier ${c.sent ? "is-sent" : ""}">
			<span class="who">🚚 ${esc(c.name)}</span>
			<span class="amounts">
				${c.in_hand ? `qo'lida <b>${money(c.in_hand)}</b> (${c.in_hand_count} ta)` : ""}
				${c.in_hand && c.sent ? " · " : ""}
				${c.sent ? `topshirdi, tasdiq kutmoqda: <b>${money(c.sent)}</b> (${c.sent_orders.length} ta)` : ""}
			</span>
			${c.sent ? `<button class="accept" data-i="${i}">✅ Qabul qildim</button>` : ""}
		</div>`).join("");
	box.querySelectorAll(".accept").forEach((b) => b.addEventListener("click", () => {
		const c = d.couriers[Number(b.dataset.i)];
		frappe.confirm(`${esc(c.name)} sizga ${money(c.sent)} naqd pulni topshirdimi?`, async () => {
			b.disabled = true;
			const r = await frappe.xcall("marketplace.kassa.accept_cash", { orders: c.sent_orders.map((o) => o.name) });
			frappe.show_alert({ message: `${money(r.total)} do'kon kassasiga qabul qilindi`, indicator: "green" });
			// Pastdagi "Kuryerlardagi naqd" kartasi ham yangilansin — butun sahifani qayta chizamiz (seller_notify.js)
			(window.mp && mp.refresh_workspace && mp.refresh_workspace()) || load();
		});
	}));
}

frappe.realtime.on("marketplace_new_order", load);
load();
"""


def _save_html_block(name, html, style, script):
	doc = frappe.get_doc("Custom HTML Block", name) if frappe.db.exists("Custom HTML Block", name) else frappe.new_doc("Custom HTML Block")
	doc.update({"html": html, "style": style, "script": script, "private": 0})
	doc.set("roles", [{"role": r} for r in (SELLER_ROLE, "System Manager", "Marketplace Manager")])
	if doc.is_new():
		doc.name = name
		doc.flags.name_set = True
	doc.save(ignore_permissions=True)


def setup_site_block():
	"""Workspace tepasidagi bloklar: "Mening saytim" (o'z do'koni havolasi) va oylik kirim/chiqim
	(reports.get_month_summary). Har bir sotuvchi faqat o'z do'konini ko'radi."""
	_save_html_block(SITE_BLOCK, SITE_BLOCK_HTML, SITE_BLOCK_CSS, SITE_BLOCK_JS)
	_save_html_block(MONTH_BLOCK, MONTH_BLOCK_HTML, MONTH_BLOCK_CSS, MONTH_BLOCK_JS)
	_save_html_block(CASH_BLOCK, CASH_BLOCK_HTML, CASH_BLOCK_CSS, CASH_BLOCK_JS)


def _save_number_cards(cards):
	"""function nuqtali yo'l bo'lsa — Custom karta: whitelisted metod ({value, fieldtype, route} qaytaradi). doctype shunda
	ham kerak: Frappe Custom kartani faqat shu hujjatni o'qiy oladiganlarga ko'rsatadi (number_card.has_permission)."""
	for name, doctype, function, field, filters, color in cards:
		custom = "." in function
		card = frappe.get_doc("Number Card", name) if frappe.db.exists("Number Card", name) else frappe.new_doc("Number Card")
		card.update(
			{
				"label": name,
				"type": "Custom" if custom else "Document Type",
				"method": function if custom else None,
				"document_type": doctype,
				"function": None if custom else function,
				"aggregate_function_based_on": field or "",
				"filters_json": json.dumps(filters or []),
				"is_public": 1,
				"is_standard": 0,
				"module": "Marketplace",
				"color": color,
				"show_percentage_stats": 0,
				# 40 480 000 so‘m — "40.48 so‘m M" emas
				"show_full_number": 1,
				"currency": "UZS" if function == "Sum" else None,
			}
		)
		if card.is_new():
			card.name = name
			card.flags.name_set = True
		card.save(ignore_permissions=True)


def setup_seller_workspace():
	"""Number Card'lar va "Do'konim" workspace'ini yaratadi yoki yangilaydi (after_migrate)."""
	_save_number_cards(NUMBER_CARDS)
	shortcuts = [
		# (yorliq, turi, link_to, ko'rinish, filtr, rang, url)
		("Tovar qo'shish", "DocType", "Item", "New", None, "Green", None),
		("Tovarlarim", "DocType", "Item", "List", {"variant_of": ["is", "not set"]}, "Blue", None),
		("Ombor", "Page", "ombor", None, None, "Orange", None),
		("Kontragentlar", "DocType", "Kontragent", "List", None, "Cyan", None),
		("Hisobot", "Page", "hisobot", None, None, "Purple", None),
		("Sotuv nazorati", "Page", "sotuv-nazorati", None, None, "Orange", None),
		("Buyurtmalar", "DocType", "Sales Order", "List", None, "Blue", None),
		("Sotuvlar", "DocType", "Sales Order", "List", {"payment_status": "To'langan"}, "Green", None),
		("Kuryerlardagi naqd", "DocType", "Sales Order", "List", {"mp_cash_status": ["in", ["Kuryerda", "Topshirilmoqda"]]}, "Orange", None),
		("Doimiy mijozlar", "DocType", "Doimiy Mijoz", "List", None, "Green", None),
		("Do'kon sozlamalari", "DocType", "Shop", "List", None, "Grey", None),
	]

	ws = frappe.get_doc("Workspace", WORKSPACE) if frappe.db.exists("Workspace", WORKSPACE) else frappe.new_doc("Workspace")
	ws.update(
		{
			"label": WORKSPACE,
			"title": "Do'konim",
			# O'z moduli: yon menyuda sotuvchiga kerakli bo'limlar (dokon/sidebar/dokon)
			"module": "Dokon",
			"icon": "store",
			"public": 1,
			"standard": 0,
			"is_hidden": 0,
			"for_user": "",
		}
	)
	ws.set("roles", [{"role": r} for r in (SELLER_ROLE, "System Manager", "Marketplace Manager")])
	ws.set("number_cards", [{"number_card_name": c[0], "label": c[0].split(": ", 1)[1]} for c in NUMBER_CARDS])
	ws.set(
		"shortcuts",
		[
			{
				"label": label,
				"type": type_,
				"link_to": link_to,
				"doc_view": view or "",
				"stats_filter": json.dumps(flt_) if flt_ else None,
				"color": color,
				"url": url,
			}
			for label, type_, link_to, view, flt_, color, url in shortcuts
		],
	)

	def block(type_, data):
		return {"id": frappe.generate_hash(length=10), "type": type_, "data": data}

	setup_site_block()
	ws.set(
		"custom_blocks",
		[
			{"custom_block_name": SITE_BLOCK, "label": "Mening saytim"},
			{"custom_block_name": MONTH_BLOCK, "label": MONTH_BLOCK},
			{"custom_block_name": CASH_BLOCK, "label": CASH_BLOCK},
		],
	)
	content = [block("custom_block", {"custom_block_name": SITE_BLOCK, "col": 12})]
	content.append(block("header", {"text": f"<span class=\"h4\"><b>{MONTH_BLOCK}</b></span>", "col": 12}))
	content.append(block("custom_block", {"custom_block_name": MONTH_BLOCK, "col": 12}))
	# Naqd pul: kassada / kuryerlarda / kuryer topshirib, tasdiq kutayotgan (kassa.cash_summary)
	content.append(block("header", {"text": f"<span class=\"h4\"><b>{CASH_BLOCK}</b></span>", "col": 12}))
	content.append(block("custom_block", {"custom_block_name": CASH_BLOCK, "col": 12}))
	content.append(block("header", {"text": "<span class=\"h4\"><b>Balans</b></span>", "col": 12}))
	content += [block("number_card", {"number_card_name": c[0].split(": ", 1)[1], "col": 3}) for c in NUMBER_CARDS]
	content.append(block("spacer", {"col": 12}))
	content.append(block("header", {"text": "<span class=\"h4\"><b>Tezkor amallar</b></span>", "col": 12}))
	content += [block("shortcut", {"shortcut_name": s[0], "col": 3}) for s in shortcuts]
	ws.content = json.dumps(content)

	if ws.is_new():
		ws.name = WORKSPACE
		ws.flags.name_set = True
	ws.flags.ignore_permissions = True
	ws.save(ignore_permissions=True)
	setup_courier_workspace()


def setup_courier_workspace():
	"""Kuryer planshetidagi "Kuryer" sahifasi: yetkaziladigan buyurtmalar, qo'lidagi naqd va mijoz anketasi."""
	from marketplace.setup import COURIER_ROLE

	_save_number_cards(COURIER_CARDS)
	shortcuts = [
		# (yorliq, turi, link_to, ko'rinish, filtr, rang)
		# Kuryer uchun sahifa: mijoz, telefon, holat, to'lov, summa; bosilganda tovar rasmlari va xaritada yo'l (kuryer.py)
		("Yetkaziladigan buyurtmalar", "Page", "kuryer-buyurtmalar", None, None, "Blue"),
		("Mijoz qo'shish", "DocType", "Doimiy Mijoz", "New", None, "Green"),
		("Doimiy mijozlar", "DocType", "Doimiy Mijoz", "List", None, "Green"),
		("Qo'limdagi naqd", "Page", "kuryer-kassa", None, None, "Orange"),
		("Topshirilganlar", "DocType", "Sales Order", "List", {"per_delivered": [">=", 100]}, "Grey"),
	]
	exists = frappe.db.exists("Workspace", COURIER_WORKSPACE)
	ws = frappe.get_doc("Workspace", COURIER_WORKSPACE) if exists else frappe.new_doc("Workspace")
	ws.update(
		{
			"label": COURIER_WORKSPACE,
			"title": "Kuryer",
			"module": "Dokon",
			"icon": "truck",
			"public": 1,
			"standard": 0,
			"is_hidden": 0,
			"for_user": "",
		}
	)
	ws.set("roles", [{"role": r} for r in (COURIER_ROLE, "System Manager", "Marketplace Manager")])
	ws.set("number_cards", [{"number_card_name": c[0], "label": c[0].split(": ", 1)[1]} for c in COURIER_CARDS])
	ws.set(
		"shortcuts",
		[
			{
				"label": label,
				"type": type_,
				"link_to": link_to,
				"doc_view": view or "",
				"stats_filter": json.dumps(flt_) if flt_ else None,
				"color": color,
			}
			for label, type_, link_to, view, flt_, color in shortcuts
		],
	)

	def block(type_, data):
		return {"id": frappe.generate_hash(length=10), "type": type_, "data": data}

	content = [block("header", {"text": "<span class=\"h4\"><b>Bugun</b></span>", "col": 12})]
	content += [block("number_card", {"number_card_name": c[0].split(": ", 1)[1], "col": 4}) for c in COURIER_CARDS]
	content.append(block("spacer", {"col": 12}))
	content.append(block("header", {"text": "<span class=\"h4\"><b>Amallar</b></span>", "col": 12}))
	content += [block("shortcut", {"shortcut_name": s[0], "col": 4}) for s in shortcuts]
	ws.content = json.dumps(content)
	if ws.is_new():
		ws.name = COURIER_WORKSPACE
		ws.flags.name_set = True
	ws.save(ignore_permissions=True)


@frappe.whitelist()
def get_item_stock(item_code: str):
	"""Tovarning do'kon omboridagi hozirgi soni (sotuvchida Bin'ga to'g'ridan-to'g'ri ruxsat yo'q)."""
	if not frappe.has_permission("Item", "read", item_code):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	shop = frappe.db.get_value("Item", item_code, "shop")
	warehouse = shop and frappe.db.get_value("Shop", shop, "warehouse")
	if not warehouse:
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"))


def item_template_price(doc, method=None):
	"""Item validate: andozaga (has_variants) ERPNext narx qo'yishga ruxsat bermaydi.

	Sotuvchi "Sotish narxi"ni yozsa, u variant_price'ga o'tadi va variantlarga tarqatiladi."""
	if doc.has_variants and doc.standard_rate:
		doc.variant_price = doc.variant_price or doc.standard_rate
		doc.standard_rate = 0


def item_default_attributes(doc, method=None):
	"""Item before_validate: variant turlari jadvali bo'sh bo'lsa, Rang va O'lcham qo'yiladi
	(ERPNext uni validate'da majburiy qiladi; variant oynasi keyin tanlanganiga moslaydi)."""
	_check_colors(doc)
	_check_kirim(doc)
	if doc.has_variants and doc.get("ranglar") is not None and (doc.get("ranglar") or not doc.get("variant_colors")):
		# Ranglar jadvali (Table MultiSelect) -> ichki matn maydoni: Rang ID emas, nomi ("Oq (clothes)" -> "Oq")
		names = color_names([r.rang for r in doc.get("ranglar") or []])
		doc.variant_colors = ", ".join(names.get(r.rang, r.rang) for r in doc.get("ranglar") or [])
	if doc.has_variants and not (not doc.is_new() and frappe.db.exists("Item", {"variant_of": doc.name})):
		# Variantlari hali yo'q andoza: turlari "Ranglar"/"O'lchamlar" maydonlariga qarab
		color_attr, size_attr = _attr_names()
		wanted = [a for a, v in ((color_attr, doc.get("variant_colors")), (size_attr, doc.get("variant_sizes"))) if _split(v)]
		if wanted and [a.attribute for a in doc.get("attributes") or []] != wanted:
			doc.set("attributes", [{"attribute": a} for a in wanted])
	if doc.has_variants and not doc.get("attributes"):
		doc.variant_based_on = "Item Attribute"
		for attr in _attr_names():
			doc.append("attributes", {"attribute": attr})
	# Yangi variant nomi: "Paxta shim (Oq · 42)" — ERPNext'ning "Paxta shim-OQ-42" o'rniga
	if doc.is_new() and doc.variant_of and doc.get("attributes"):
		base = frappe.db.get_value("Item", doc.variant_of, "item_name")
		values = " · ".join(a.attribute_value for a in doc.attributes if a.attribute_value)
		if base and values:
			doc.item_name = f"{base} ({values})"[:140]


def item_after_insert(doc, method=None):
	"""Yangi variant: narxi andozadagi variant_price'dan."""
	if doc.variant_of:
		price = flt(frappe.db.get_value("Item", doc.variant_of, "variant_price"))
		if price:
			_set_price(doc.name, price)


def _check_colors(doc):
	"""Ranglar, kirim va galereyadagi rang — faqat tovar do'konining o'z ranglaridan. Boshqa do'konning shu nomli
	rangi tanlangan bo'lsa (masalan admin tanlagan), o'z do'konidagisiga almashtiriladi."""
	if not doc.get("shop"):
		return
	rows = [r for f in ("ranglar", "mp_kirim", "gallery") for r in doc.get(f) or [] if r.get("rang")]
	if not rows:
		return
	info = {
		c.name: c
		for c in frappe.get_all("Rang", filters={"name": ["in", list({r.rang for r in rows})]}, fields=["name", "rang_nomi", "shop"])
	}
	own = {c.rang_nomi.lower(): c.name for c in shop_colors(doc.shop)}
	for r in rows:
		c = info.get(r.rang)
		if c and c.shop == doc.shop:
			continue
		name = c.rang_nomi if c else r.rang
		if not own.get(name.lower()):
			frappe.throw(_("«{0}» rangi do'koningiz ro'yxatida yo'q. Chapdagi menyu → Ranglar'dan qo'shing").format(name))
		r.rang = own[name.lower()]


def _split(value):
	return list(dict.fromkeys(x.strip() for x in re.split(r"[,\n]", value or "") if x.strip()))

def _check_kirim(doc):
	"""Ombor tabidagi kirim: kontragent (shu do'konniki), har qatorda soni va 1 donasi narxi majburiy;
	kirimdagi yangi rang/o'lcham tovar ro'yxatlariga qo'shiladi."""
	rows = doc.get("mp_kirim") or []
	if rows and not doc.get("mp_kirim_kontragent"):
		frappe.throw(_("Kirim: tovar qaysi kontragentdan olinganini tanlang («Kimdan olindi»)"))
	if rows and frappe.db.get_value("Kontragent", doc.mp_kirim_kontragent, "shop") != doc.shop:
		frappe.throw(_("Kirim: kontragentni o'z do'koningiz ro'yxatidan tanlang"))
	for row in rows:
		if cint(row.soni) <= 0:
			frappe.throw(_("Kirim, {0}-qator: nechta kelganini yozing (0 dan katta)").format(row.idx))
		if flt(row.narx) <= 0:
			frappe.throw(_("Kirim, {0}-qator: 1 donasi necha puldan olinganini yozing").format(row.idx))
		row.olcham = (row.olcham or "").strip()
		if not doc.has_variants:
			row.rang = row.olcham = None
	if not (doc.has_variants and rows):
		return
	have = [r.rang for r in doc.get("ranglar") or []]
	for color in dict.fromkeys(r.rang for r in rows if r.rang and r.rang not in have):
		doc.append("ranglar", {"rang": color})
	sizes = _split(doc.variant_sizes)
	extra = [z for z in dict.fromkeys(r.olcham for r in rows if r.olcham) if z.lower() not in {s.lower() for s in sizes}]
	if extra:
		_check_names(extra)
		doc.variant_sizes = ", ".join(sizes + extra)
	remember_shop_sizes(doc.shop, [r.olcham for r in rows if r.olcham])


def shop_sizes(shop=None):
	"""Do'konning o'z o'lchamlari (O'lchamlar ro'yxati, tartibi bilan)."""
	shop = shop or get_user_shop()
	if not shop:
		return []
	return frappe.get_all(
		"Olcham", filters={"shop": shop}, pluck="olcham", order_by="tartib asc, creation asc", ignore_permissions=True
	)


def remember_shop_sizes(shop, sizes):
	"""Kirimda yozilgan yangi o'lcham do'kon ro'yxatiga qo'shiladi — keyingi safar tanlashga tayyor turadi."""
	if not shop:
		return
	have = {h.lower() for h in shop_sizes(shop)}
	for size in dict.fromkeys(sizes):
		if size.lower() not in have:
			have.add(size.lower())
			frappe.get_doc({"doctype": "Olcham", "olcham": size, "shop": shop}).insert(ignore_permissions=True)


def _receive_rows(doc):
	"""Kirim qatorlari -> bitta kirim hujjati (Material Receipt): kimdan, nechta, necha puldan.
	Keyin jadval tozalanadi: tarixi Ombor tabida."""
	from marketplace.inventory import receive, shop_warehouse

	note = _("Tovar formasidan kirim") + (f": {doc.mp_kirim_izoh.strip()[:300]}" if (doc.get("mp_kirim_izoh") or "").strip() else "")
	if doc.has_variants:
		names = color_names([r.rang for r in doc.mp_kirim])
		rows = [(names.get(r.rang, ""), r.olcham or "", cint(r.soni), flt(r.narx)) for r in doc.mp_kirim]
		_receive_matrix(doc.name, rows, doc.mp_kirim_kontragent, note)
	else:
		if not doc.is_stock_item:
			frappe.throw(_("Bu tovar omborda hisoblanmaydi"))
		rows = [(doc.name, cint(r.soni), flt(r.narx)) for r in doc.mp_kirim]
		receive(shop_warehouse(doc.shop), rows, doc.mp_kirim_kontragent, remarks=note)
	frappe.db.delete("Tovar Kirimi", {"parent": doc.name, "parenttype": "Item", "parentfield": "mp_kirim"})
	frappe.db.set_value("Item", doc.name, {"mp_kirim_izoh": None, "mp_kirim_kontragent": None}, update_modified=False)
	doc.set("mp_kirim", [])
	doc.mp_kirim_izoh = doc.mp_kirim_kontragent = None


@frappe.whitelist()
def get_item_ledger(item_code: str):
	"""Ombor tabi: shu tovar (va uning variantlari) kirimlari — kimdan, nechta, necha puldan.
	Sotuvlar bu yerga yozilmaydi: ular qoldiqni o'zi kamaytiradi (to'liq harakatlar — Hisobot'da)."""
	from marketplace.reports import journal

	if not frappe.has_permission("Item", "read", item_code):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	shop = frappe.db.get_value("Item", item_code, "shop")
	warehouse = shop and frappe.db.get_value("Shop", shop, "warehouse")
	if not warehouse:
		return []
	codes = [item_code, *frappe.get_all("Item", filters={"variant_of": item_code}, pluck="name")]
	return journal([warehouse], item_codes=codes, kinds={"kirim"})



def item_on_update(doc, method=None):
	"""Ombor tabidagi kirim qatorlari omborga yoziladi (rang/o'lcham varianti bo'lmasa — yaratiladi) va tozalanadi.
	Variantlar faqat kirimdan paydo bo'ladi: kelmagan rang/o'lcham saytda ham chiqmaydi.
	Andozada standart narx o'zgarsa, variantlar narxi yangilanadi — alohida narx qo'yilganlaridan (mp_own_price) tashqari."""
	if doc.get("mp_kirim") and not frappe.flags.mp_creating_variants:
		_receive_rows(doc)
	if doc.has_variants and doc.has_value_changed("variant_price") and flt(doc.variant_price):
		for code in frappe.get_all("Item", filters={"variant_of": doc.name, "mp_own_price": 0}, pluck="name"):
			_set_price(code, flt(doc.variant_price))
	# Oddiy tovar: ERPNext narx ro'yxatiga (Item Price) narxni faqat yaratilganda yozadi; sotuvchi narxni keyin
	# qo'ysa yoki o'zgartirsa, sayt eski/bo'sh narxni ko'rardi ("Mahsulot sotuvda emas"). Shu yerda sinxronlaymiz
	if not doc.has_variants and not doc.variant_of and flt(doc.standard_rate):
		from marketplace.storefront import _selling_price_list

		if doc.has_value_changed("standard_rate") or not frappe.db.exists(
			"Item Price", {"item_code": doc.name, "price_list": _selling_price_list(), "selling": 1}
		):
			_set_price(doc.name, flt(doc.standard_rate))
	_warn_unpriced(doc)


def item_onload(doc, method=None):
	"""Item onload: formada «Sotish narxi» 0 turib, narx ro'yxatida (Item Price) narx bo'lsa — ko'rsatamiz.
	Sotuvchi hozirgi narxni ko'radi va o'zgartira oladi (saqlashda item_on_update ro'yxatga yozadi)."""
	if doc.has_variants or doc.variant_of or flt(doc.standard_rate):
		return
	from marketplace.storefront import _get_prices

	rate = _get_prices([doc.name]).get(doc.name)
	if rate:
		doc.standard_rate = rate


def _warn_unpriced(doc):
	"""Saytga chiqarilgan, lekin narxi yo'q tovar katalogda ko'rinmaydi — sotuvchiga aytamiz (saqlash to'xtamaydi)."""
	if not (doc.is_published and doc.get("shop")) or doc.variant_of or doc.get("mp_tez_kunda"):
		return
	from marketplace.storefront import _get_prices

	if _get_prices([doc.name]).get(doc.name) is None:
		frappe.msgprint(
			_("Tovar saytda ko'rinmaydi: narxi yo'q. «Sotish narxi»ni yozing") + (
				_(" (variantli tovarda — Ombor tabidan kirim qiling, variantlar narx bilan yaratiladi)") if doc.has_variants else ""
			) + _(" yoki «Tez kunda» belgilang."),
			indicator="orange", title=_("Narx qo'yilmagan"),
		)


def item_price_on_update(doc, method=None):
	"""Item Price saqlanganda tovarning standard_rate'i ham shu narx bo'ladi — Tovarlar ro'yxatida narx ko'rinadi
	(ERPNext buni faqat yaratishda ko'chiradi). Item saqlanmaydi (db_set) — item_on_update bilan aylanma bo'lmaydi."""
	from marketplace.storefront import _selling_price_list

	if doc.price_list != _selling_price_list():
		return
	current = frappe.db.get_value("Item", doc.item_code, "standard_rate")
	if current is not None and flt(current) != flt(doc.price_list_rate):
		frappe.db.set_value("Item", doc.item_code, "standard_rate", flt(doc.price_list_rate), update_modified=False)


def _set_price(item_code, price):
	from marketplace.storefront import _selling_price_list

	price_list = _selling_price_list()
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if name:
		doc = frappe.get_doc("Item Price", name)
		doc.price_list_rate = price
		doc.save()
	else:
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": price}
		).insert()


def _variant_cells(template):
	"""{(rang, o'lcham): variant kodi}. Rang yoki o'lcham bo'lmasa — ""."""
	color_attr, size_attr = _attr_names()
	codes = frappe.get_all("Item", filters={"variant_of": template, "disabled": 0}, pluck="name")
	attrs = {}
	for a in frappe.get_all(
		"Item Variant Attribute", filters={"parent": ["in", codes or [""]]}, fields=["parent", "attribute", "attribute_value"]
	):
		attrs.setdefault(a.parent, {})[a.attribute] = a.attribute_value
	return {(attrs.get(c, {}).get(color_attr) or "", attrs.get(c, {}).get(size_attr) or ""): c for c in codes}


@frappe.whitelist()
def get_variant_matrix(template: str | None = None):
	"""Rang × o'lcham jadvali: har katakda omborda nechta bor (variant yo'q bo'lsa — code yo'q).
	Yangi tovar uchun (template yo'q) — faqat ranglar rangi (hexes)."""
	from marketplace.inventory import stock_of

	color_attr, size_attr = _attr_names()
	if not template or not frappe.db.exists("Item", template):
		return {"colors": [], "sizes": [], "cells": {}, "hexes": shop_hexes(get_user_shop())}
	if not frappe.has_permission("Item", "read", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	doc = frappe.get_doc("Item", template)
	hexes = shop_hexes(doc.shop)
	cells = _variant_cells(template)
	dims = [a.attribute for a in doc.attributes]
	names = color_names([r.rang for r in doc.get("ranglar") or []])
	colors = [""] if dims and color_attr not in dims else list(
		dict.fromkeys([names[r.rang] for r in doc.get("ranglar") or [] if r.rang] + [c for c, _s in cells if c])
	)
	sizes = [""] if dims and size_attr not in dims else list(dict.fromkeys(_split(doc.variant_sizes) + [z for _c, z in cells if z]))
	warehouse = frappe.db.get_value("Shop", doc.shop, "warehouse")
	stock = stock_of(list(cells.values()), warehouse) if warehouse else {}
	return {
		"hexes": hexes,
		"colors": [{"value": c, "hex": hexes.get(c)} for c in colors],
		"sizes": sizes,
		"cells": {
			f"{c}|{z}": {"code": code, "qty": stock.get(code, (0, 0))[0], "reserved": stock.get(code, (0, 0))[1]}
			for (c, z), code in cells.items()
		},
	}


@frappe.whitelist()
def get_variant_prices(template: str):
	""""Rang/o'lcham bo'yicha narx" oynasi: har bir variant — omborda nechta, oxirgi kirimdagi olish narxi,
	hozirgi sotish narxi va u alohida qo'yilganmi (mp_own_price). Tartib — get_variant_matrix'dagi kabi."""
	from marketplace.storefront import _get_prices

	matrix = get_variant_matrix(template)
	codes = [cell["code"] for cell in matrix["cells"].values()]
	prices = _get_prices(codes) if codes else {}
	own = set(frappe.get_all("Item", filters={"name": ["in", codes or [""]], "mp_own_price": 1}, pluck="name"))
	costs = _last_costs(codes)
	rows = []
	for color in matrix["colors"]:
		for size in matrix["sizes"]:
			cell = matrix["cells"].get(f"{color['value']}|{size}")
			if cell:
				code = cell["code"]
				rows.append(
					{
						"code": code, "color": color["value"], "hex": color["hex"], "size": size, "qty": cell["qty"],
						"cost": costs.get(code), "price": prices.get(code), "own": code in own,
					}
				)
	return {"standard": flt(frappe.db.get_value("Item", template, "variant_price")), "rows": rows}


@frappe.whitelist(methods=["POST"])
def set_variant_prices(template: str, prices: str | dict):
	"""Oynadan {variant: narx}. Bo'sh yoki standartga teng — variant standart narxga qaytadi (standart o'zgarsa,
	u ham o'zgaradi); boshqa son — alohida narx (mp_own_price): standart narx o'zgarsa ham o'z narxida qoladi."""
	if not frappe.has_permission("Item", "write", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	prices = json.loads(prices) if isinstance(prices, str) else prices or {}
	standard = flt(frappe.db.get_value("Item", template, "variant_price"))
	variants = dict(frappe.get_all("Item", filters={"variant_of": template}, fields=["name", "item_name"], as_list=True))
	for code, value in prices.items():
		if code not in variants:
			frappe.throw(_("Bu tovarning varianti emas: {0}").format(code))
		price = flt(value)
		if price < 0:
			frappe.throw(_("{0}: narx manfiy bo'lmaydi").format(variants[code]))
		own = bool(price) and price != standard
		if not own and not standard:
			frappe.throw(_("{0}: narxini yozing (tovarda standart narx yo'q)").format(variants[code]))
		_set_price(code, price if own else standard)
		frappe.db.set_value("Item", code, "mp_own_price", int(own), update_modified=False)
	return get_variant_prices(template)


def _last_costs(codes):
	"""{variant: oxirgi kirimdagi 1 donasining olish narxi}. Narxsiz eski kirimlar hisobga olinmaydi."""
	if not codes:
		return {}
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	rows = (
		frappe.qb.from_(sed)
		.join(se)
		.on(sed.parent == se.name)
		.select(sed.item_code, sed.basic_rate)
		.where(se.docstatus == 1)
		.where(se.purpose == "Material Receipt")
		.where(sed.item_code.isin(codes))
		.where(sed.basic_rate > 0)
		.orderby(se.posting_date, order=frappe.qb.desc)
		.orderby(se.posting_time, order=frappe.qb.desc)
		.orderby(se.creation, order=frappe.qb.desc)
		.orderby(sed.idx, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	costs = {}
	for r in rows:
		costs.setdefault(r.item_code, flt(r.basic_rate))
	return costs


def _receive_matrix(template, rows, supplier, remarks):
	"""Kerakli variantlarni yaratadi va kelgan sonlarni bitta kirim hujjati bilan omborga yozadi.
	rows = [(rang, o'lcham, soni, 1 donasi narxi)]: bir xil rang/o'lcham har xil narxda kelsa — alohida qator."""
	from erpnext.controllers.item_variant import create_variant

	from marketplace.inventory import receive, shop_warehouse

	if not rows:
		return
	doc = frappe.get_doc("Item", template)
	color_attr, size_attr = _attr_names()
	dims = [a.attribute for a in doc.attributes]
	cells = _variant_cells(template)
	_check_names([v for color, size, _qty, _rate in rows for v in (color, size) if v])
	items = []
	frappe.flags.mp_creating_variants = True
	try:
		for color, size, qty, rate in rows:
			if (color_attr in dims) != bool(color) or (size_attr in dims) != bool(size):
				frappe.throw(_("{0}: bu tovarda rang va o'lcham ikkalasi ham kerak").format(" · ".join(filter(None, (color, size)))))
			code = cells.get((color, size))
			if not code:
				args = {}
				if color:
					args[color_attr] = _ensure_values(color_attr, [color])[0]
				if size:
					args[size_attr] = _ensure_values(size_attr, [size])[0]
				code = cells.get((args.get(color_attr, ""), args.get(size_attr, "")))
				if not code:
					variant = create_variant(template, args)
					variant.insert()
					code = variant.name
				# Shu kirimda bu rang/o'lcham yana kelsa, variant qayta yaratilmasin
				cells[(color, size)] = code
			items.append((code, qty, rate))
	finally:
		frappe.flags.mp_creating_variants = False
	receive(shop_warehouse(doc.shop), items, supplier, remarks=remarks)
	frappe.clear_cache(doctype="Item")


def _check_names(values):
	for v in values:
		if len(v) > 30 or not re.fullmatch(r"[\w\s\-/.,()‘'ʻ+]+", v):
			frappe.throw(_("Noto'g'ri nom: {0}").format(v))


def _not_courier():
	from marketplace.permissions import is_courier

	if is_courier():
		frappe.throw(_("Bu amal do'kon egasi uchun"), frappe.PermissionError)


def _seller_order(name):
	if not frappe.has_permission("Sales Order", "write", name):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	so = frappe.get_doc("Sales Order", name)
	if so.docstatus != 1:
		frappe.throw(_("Buyurtma faol emas"))
	return so


@frappe.whitelist()
def mark_cash_received(order: str):
	"""Naqd to'lov: sotuvchi pulni olganini belgilaydi (kuryer esa courier_delivered bilan)."""
	_not_courier()
	so = _seller_order(order)
	if so.payment_method != "Naqd":
		frappe.throw(_("Bu buyurtma naqd emas"))
	if so.payment_status != "To'langan":
		so.db_set("payment_status", "To'langan")
		so.add_comment("Info", _("Naqd pul olindi"))
		from marketplace.kassa import stamp_paid

		stamp_paid(so.name)
	return so.payment_status


@frappe.whitelist()
def mark_delivered(order: str):
	"""Mijozga topshirildi: ERPNext Delivery Note yaratib submit qiladi — tovar ombordan ayriladi."""
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	so = _seller_order(order)
	if so.payment_status == "Bekor":
		frappe.throw(_("Bekor qilingan buyurtma"))
	if so.payment_method in ("Payme", "Click") and so.payment_status != "To'langan":
		frappe.throw(_("Onlayn to'lov hali kelmagan. To'lovdan keyin topshiring."))
	if not so.payment_method and so.payment_status != "To'langan":
		frappe.throw(_("Mijoz hali to'lov usulini tanlamagan. Tanlagandan keyin topshiring."))
	if flt(so.per_delivered) >= 100:
		return None
	from marketplace.orders import as_system

	# Ruxsat yuqorida tekshirildi. ERPNext ichida hisob (Account) o'qiladi, sotuvchida unga ruxsat yo'q
	with as_system():
		dn = make_delivery_note(so.name)
		dn.insert()
		dn.submit()
	so.add_comment("Info", _("Mijozga topshirildi: {0}").format(dn.name))
	# Tovarni olgan mijoz — do'konning doimiy mijozi. Xato bo'lsa ham topshirish to'xtamasin
	from marketplace.marketplace.doctype.doimiy_mijoz.doimiy_mijoz import register_from_delivery

	try:
		register_from_delivery(so)
	except Exception:
		frappe.log_error("Doimiy mijozga yozib bo'lmadi", so.name)
	return dn.name


@frappe.whitelist()
def courier_delivered(order: str):
	"""Kuryer tovarni mijozga berdi. Naqd buyurtmada — pulni ham oldi: pul "Kuryerda" bo'lib turadi,
	do'kon egasi uni olganda cash_handed_over bilan "Do'konga topshirildi" bo'ladi."""
	from frappe.utils import now_datetime

	from marketplace.permissions import is_courier

	so = _seller_order(order)
	if so.payment_status == "Bekor":
		frappe.throw(_("Bekor qilingan buyurtma"))
	if flt(so.per_delivered) >= 100:
		frappe.throw(_("Bu buyurtma allaqachon topshirilgan"))
	if so.mp_courier and so.mp_courier != frappe.session.user and is_courier():
		frappe.throw(_("Bu buyurtmani boshqa kuryer olgan"))

	cash = so.payment_method == "Naqd" and so.payment_status != "To'langan"
	so.db_set({"mp_courier": frappe.session.user, "mp_delivered_at": now_datetime()})
	if cash:
		so.db_set({"payment_status": "To'langan", "mp_cash_status": "Kuryerda"})
		from marketplace.kassa import stamp_paid

		stamp_paid(so.name)
	mark_delivered(order)
	who = frappe.utils.get_fullname(frappe.session.user)
	if cash:
		so.add_comment("Info", _("{0}: naqd {1} olindi, mijozga topshirildi").format(who, frappe.utils.fmt_money(so.grand_total, currency=so.currency)))
		notify_shop(so, _("{0} {1} buyurtmani topshirdi va {2} naqd oldi").format(who, so.name, frappe.utils.fmt_money(so.grand_total, currency=so.currency)))
	else:
		so.add_comment("Info", _("{0}: mijozga topshirildi").format(who))
	return "cash" if cash else "delivered"


@frappe.whitelist()
def cash_handed_over(orders):
	"""Do'kon egasi kuryerdan naqd pulni oldi (bitta yoki ro'yxatdan bir nechta buyurtma)."""
	from frappe.utils import now_datetime

	_not_courier()
	names = frappe.parse_json(orders) if isinstance(orders, str) and orders.startswith("[") else [orders]
	done = 0
	for name in names:
		so = _seller_order(name)
		# Kuryer "Topshirdim" bosgan (Topshirilmoqda) yoki hali bosmagan bo'lsa ham do'konchi qabul qila oladi (kassa.py)
		if so.mp_cash_status not in ("Kuryerda", "Topshirilmoqda"):
			continue
		so.db_set({"mp_cash_status": "Do'konga topshirildi", "mp_cash_handed_at": now_datetime()})
		so.add_comment(
			"Info",
			_("Kuryerdan ({0}) naqd {1} olindi").format(
				frappe.utils.get_fullname(so.mp_courier), frappe.utils.fmt_money(so.grand_total, currency=so.currency)
			),
		)
		done += 1
	return done


@frappe.whitelist()
def cancel_order(order: str, reason: str | None = None):
	"""Sotuvchi buyurtmani bekor qiladi (to'lanmagan bo'lsa). Zaxira bo'shaydi, mijozga "Bekor" ko'rinadi."""
	_not_courier()
	so = _seller_order(order)
	if so.payment_status == "To'langan" and so.payment_method in ("Payme", "Click"):
		frappe.throw(_("Onlayn to'langan buyurtma Payme/Click kabinetidan pul qaytarish orqali bekor qilinadi"))
	if flt(so.per_delivered):
		frappe.throw(_("Topshirilgan buyurtmani bekor qilib bo'lmaydi"))
	from marketplace.orders import as_system

	so.db_set("payment_status", "Bekor")
	so.add_comment("Info", _("Sotuvchi bekor qildi") + (f": {reason}" if reason else ""))
	with as_system():
		so.cancel()
	return "Bekor"


def _attr_names():
	from marketplace.setup import COLOR_ATTR, SIZE_ATTR

	return COLOR_ATTR, SIZE_ATTR


@frappe.whitelist()
def get_variant_options(template: str | None = None):
	"""Variant oynasi uchun: mavjud ranglar/o'lchamlar va shu tovarda allaqachon borlari."""
	if template and frappe.db.exists("Item", template) and not frappe.has_permission("Item", "read", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	color_attr, size_attr = _attr_names()
	values = lambda attr: frappe.get_all(  # noqa: E731
		"Item Attribute Value", filters={"parent": attr}, pluck="attribute_value", order_by="idx", ignore_permissions=True
	)
	used = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", frappe.get_all("Item", filters={"variant_of": template}, pluck="name")]},
		fields=["attribute", "attribute_value"],
		ignore_permissions=True,
	)
	return {
		# Do'konning o'z ranglari (yon menyu → Ranglar)
		"colors": [c.rang_nomi for c in shop_colors(get_user_shop())],
		# Do'konning o'z o'lchamlari (yon menyu → O'lchamlar); hali bo'sh bo'lsa — platformaning XS…3XL
		"sizes": shop_sizes() or values(size_attr),
		"used_colors": sorted({u.attribute_value for u in used if u.attribute == color_attr}),
		"used_sizes": sorted({u.attribute_value for u in used if u.attribute == size_attr}),
	}


@frappe.whitelist()
def create_variants(template: str, colors=None, sizes=None):
	"""Tanlangan rang × o'lcham uchun variantlar. Yangi rang/o'lcham nomlari avtomatik qo'shiladi."""
	if not frappe.has_permission("Item", "write", template):
		frappe.throw(_("Ruxsat yo'q"), frappe.PermissionError)
	clean = lambda xs: list(dict.fromkeys(x.strip() for x in frappe.parse_json(xs or "[]") if x and x.strip()))  # noqa: E731
	return _create_variants(template, clean(colors), clean(sizes))


def _create_variants(template, colors, sizes):
	from erpnext.controllers.item_variant import create_multiple_variants

	color_attr, size_attr = _attr_names()
	if not colors and not sizes:
		frappe.throw(_("Kamida bitta rang yoki o'lcham tanlang"))
	_check_names(colors + sizes)

	colors = _ensure_values(color_attr, colors)
	sizes = _ensure_values(size_attr, sizes)

	item = frappe.get_doc("Item", template)
	remember_shop_colors(item.shop, colors)
	if not item.has_variants:
		frappe.throw(_("Avval \"Rang / o'lcham variantlari bor\" belgisini qo'yib saqlang"))
	wanted = [a for a, vals in ((color_attr, colors), (size_attr, sizes)) if vals]
	current = [a.attribute for a in item.attributes]
	if current != wanted:
		if frappe.db.exists("Item", {"variant_of": template}):
			# Variantlar bor: tuzilmani o'zgartirib bo'lmaydi, yetishmayotgan turdagi qiymat so'raladi
			missing = [a for a in current if a not in wanted]
			if missing:
				frappe.throw(_("Bu tovarda {0} ham tanlanishi kerak").format(", ".join(missing)))
		else:
			item.set("attributes", [{"attribute": a} for a in wanted])
			item.save()

	args = {a: vals for a, vals in ((color_attr, colors), (size_attr, sizes)) if vals}
	count = create_multiple_variants(template, json.dumps(args))
	frappe.clear_cache(doctype="Item")
	return count


def _ensure_values(attr, values):
	"""Yangi nomlarni Item Attribute'ga qo'shadi. Qaytaradi: bazadagi yozilishidagi nomlar ("oq" -> "Oq")."""
	if not values:
		return []
	known = {
		v.lower(): v
		for v in frappe.get_all("Item Attribute Value", filters={"parent": attr}, pluck="attribute_value", ignore_permissions=True)
	}
	new = [v for v in values if v.lower() not in known]
	if new:
		doc = frappe.get_doc("Item Attribute", attr)
		abbrs = {r.abbr for r in doc.item_attribute_values}
		for v in new:
			abbr = re.sub(r"[^A-Za-z0-9]", "", v).upper()[:6] or frappe.generate_hash(length=4).upper()
			while abbr in abbrs:
				abbr = abbr[:5] + frappe.generate_hash(length=1).upper()
			abbrs.add(abbr)
			doc.append("item_attribute_values", {"attribute_value": v, "abbr": abbr})
			known[v.lower()] = v
		doc.flags.ignore_permissions = True
		doc.save()
	return list(dict.fromkeys(known[v.lower()] for v in values))
