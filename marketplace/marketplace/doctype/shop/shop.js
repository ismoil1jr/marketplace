// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shop", {
	setup(frm) {
		// Reklama slaydi faqat shu do'konning saytdagi tovariga olib boradi
		frm.set_query("item", "banners", () => ({
			filters: { shop: frm.doc.name, is_published: 1, disabled: 0, variant_of: ["is", "not set"] },
		}));
		// Instagram formasi faqat shu do'kon tovariga bog'lanadi (variant emas — rang/o'lchamni menejer so'raydi)
		frm.set_query("tovar", "meta_forms", () => ({
			filters: { shop: frm.doc.name, disabled: 0, variant_of: ["is", "not set"] },
		}));
		// Chegirma barabani: faqat shu do'kon tovarlari, uzun tavsifsiz (kod + nom)
		frm.set_query("baraban_tovar", () => ({ query: "marketplace.baraban.tovar_query", filters: { shop: frm.doc.name } }));
	},
	baraban_tovar(frm) {
		baraban_preview(frm);
	},
	baraban_narx(frm) {
		baraban_preview(frm);
	},
	refresh(frm) {
		baraban_preview(frm);
		if (frm.is_new()) return;

		const url = `/s/${encodeURIComponent(frm.doc.name)}`;
		// Asosiy domen (host_name, seller_desk.extend_bootinfo): IP orqali kirilganda ham to'g'ri manzil
		const base = frappe.boot.marketplace_site_url || location.origin;
		frm.add_custom_button(__("Saytni ochish"), () => window.open(url, "_blank"));
		frm.add_custom_button(__("Havolani nusxalash"), () => frappe.utils.copy_to_clipboard(base + url));

		for (const [layout, label] of [["vitrina", "A — Vitrina"], ["story", "B — Instagram uslubi"], ["katalog", "C — Katalog (ulgurji)"]]) {
			frm.add_custom_button(__(label), () => window.open(`${url}?layout=${layout}`, "_blank"), __("Shablonni ko'rish"));
		}
		frm.add_custom_button(__("Tovarlar"), () => frappe.set_route("List", "Item", { shop: frm.doc.name }), __("Ko'rish"));
		frm.add_custom_button(__("Buyurtmalar"), () => frappe.set_route("List", "Sales Order", { shop: frm.doc.name }), __("Ko'rish"));

		// Admin: Payme/Click kabinetiga yoziladigan webhook manzillari — har bir do'konning o'zi (?dokon=, payments.url_shop)
		if (frappe.user.has_role("System Manager") || frappe.user.has_role("Marketplace Manager")) {
			frm.add_custom_button(__("Do'kon paneliga kirish"), () => marketplace_enter_shop(frm.doc.name));
			const api = `${base}/api/method/marketplace`;
			const own = `?dokon=${encodeURIComponent(frm.doc.name)}`;
			frm.set_df_property(
				"sb_payme",
				"description",
				`Shu do'kon kassasi uchun Payme Business → kassa → Endpoint URL: <code>${api}.payme.callback${own}</code><br>Hisob maydoni (account): <code>order_id</code>. Kalitni shu yerga qo'ying — u shifrlanib saqlanadi.`
			);
			frm.set_df_property(
				"sb_click",
				"description",
				`Shu do'kon xizmati uchun Click merchant → Prepare URL: <code>${api}.click.prepare${own}</code>, Complete URL: <code>${api}.click.complete${own}</code>`
			);
		}

		marketplace_meta_buttons(frm);

		frm.set_intro(
			frm.doc.status === "Active"
				? __("Sayt mijozlarga ochiq: {0}", [`<a href="${base}${url}" target="_blank">${base.replace(/^https?:\/\//, "")}${url}</a>`])
				: __("Sayt mijozlarga yopiq. Ochish uchun Status'ni Active qiling."),
			frm.doc.status === "Active" ? "green" : "orange"
		);
	},
});

// ---------------- Instagram lead-formalari (sotuv/meta.py) ----------------

function marketplace_meta_buttons(frm) {
	const admin = frappe.user.has_role("System Manager") || frappe.user.has_role("Marketplace Manager");
	const group = __("Instagram forma");
	const connected = !!frm.doc.meta_page_id;
	if (admin || frappe.user.has_role("Shop Seller")) {
		frm.add_custom_button(__("Google Sheets orqali"), () => marketplace_sheets(frm), group);
	}
	if (admin) {
		frm.add_custom_button(connected ? __("Boshqa sahifani ulash") : __("Meta'ga ulash"), () => marketplace_meta_connect(frm), group);
	}
	if (connected) {
		frm.add_custom_button(__("Formalarni yangilash"), () =>
			frappe.call({
				method: "marketplace.sotuv.meta.refresh_forms",
				args: { shop: frm.doc.name },
				freeze: true,
				freeze_message: __("Meta'dan formalar olinmoqda…"),
			}).then((r) => {
				frappe.show_alert({ message: __("Formalar: {0}, yangi murojaat: {1}", [r.message.forms, r.message.saved]), indicator: "green" });
				frm.reload_doc();
			}), group);
		if (admin) {
			frm.add_custom_button(__("Uzish"), () =>
				frappe.confirm(__("«{0}» sahifasi uzilsinmi? Shu sahifa formalaridan murojaat kelmay qoladi.", [frm.doc.meta_page_name]), () =>
					frappe.call({ method: "marketplace.sotuv.meta.disconnect", args: { shop: frm.doc.name }, freeze: true }).then(() => frm.reload_doc())
				), group);
		}
	}
}

// Meta Instant Form → Google Sheets (Meta'ning o'z integratsiyasi) → jadvaldagi Apps Script → murojaat.qabul.
// Meta developer akkaunti kerak emas; kodda do'kon kaliti bor, ekranda yashirilgan (murojaat.sheets_setup)
async function marketplace_sheets(frm) {
	const r = await frappe.xcall("marketplace.sotuv.murojaat.sheets_setup", { shop: frm.doc.name });
	const esc = frappe.utils.escape_html;
	const shown = r.script.replace(/(const KALIT = ")[^"]+/, "$1••••••••••••");
	const items = r.items.length
		? r.items.map((i) => `<tr><td style="width:90px"><b>${i.id}</b></td><td>${esc(i.name)}`
			+ (i.published ? "" : ` <span class="text-muted">— ${__("saytda yashirin")}</span>`)
			+ (i.soon ? ` <span class="text-muted">— ${__("tez kunda")}</span>` : "") + "</td></tr>").join("")
		: `<tr><td class="text-muted">${__("Do'konda hali tovar yo'q")}</td></tr>`;
	const d = new frappe.ui.Dialog({
		title: __("Instagram forma → Google Sheets → Murojaatlar"),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "body" }],
	});
	d.fields_dict.body.$wrapper.html(`
		${r.local ? `<div class="alert alert-warning small">${__("Bu nusxa lokal: Google unga yeta olmaydi. Kodni magazinlar.uz'dan oling.")}</div>` : ""}
		<ol style="padding-left:18px;line-height:1.75;margin-bottom:14px">
			<li><b>Meta Business Suite</b> → ${__("Barcha vositalar")} → <b>Instant Forms</b> (Мгновенные формы) → <b>CRM setup</b> → <b>Google Sheets</b> → ${__("Google akkaunt bilan kiring.")}</li>
			<li><b>New integration</b>: ${__("bitta jadvalni tanlang, har bir formani o'z varag'iga ulang.")}
				<b>${__("Varaq nomini Tovar ID bilan boshlang")}</b>: «1 Audio kitob». ${__("Forma nomi «1 …» bilan boshlansa ham bo'ladi.")}</li>
			<li>${__("Jadvalda")}: <b>${__("Kengaytmalar → Apps Script")}</b> → ${__("pastdagi kodni qo'ying")} → ${__("Saqlash")} → <b>sozlash</b> → <b>Run</b> → ${__("ruxsat bering.")}
				<div class="text-muted small">${__("Google «tasdiqlanmagan ilova» desa: Advanced (Дополнительно) → Go to … → Allow. Bu sizning o'z skriptingiz.")}</div></li>
			<li>${__("Meta'da «Send test lead» bosing: «magazinlar.uz» varag'ida «o'tkazildi: Telefon raqami…» chiqadi — sinov lid shunday bo'ladi. Haqiqiy murojaat 1 daqiqada Sotuv paneli → Murojaatlar'ga tushadi.")}</li>
		</ol>
		<div style="font-weight:600;margin-bottom:6px">${__("Tovar ID'lar")}</div>
		<table class="table table-bordered table-sm small" style="margin-bottom:6px">${items}</table>
		<p class="text-muted small">${__("ID tovar formasida («Tovar ID (reklama)») o'zgartiriladi. Jadvalda «tovar_id» ustuni bo'lsa — o'sha olinadi.")}</p>
		<div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px">
			<span style="font-weight:600">${__("Apps Script kodi")}</span>
			<button class="btn btn-primary btn-sm" data-copy>${__("Kodni nusxalash")}</button>
		</div>
		<pre style="font-size:11px;max-height:220px;overflow:auto;margin-top:6px">${esc(shown)}</pre>
		<div class="alert alert-warning small" style="margin-top:10px">${__("Kod ichida do'kon kaliti bor: jadvalni faqat ishonchli odamlar bilan bo'lishing. Kalit yangilansa (tovar → «SMM havolasi» → Kalitni yangilash), kodni qayta qo'ying.")}</div>`);
	d.fields_dict.body.$wrapper.find("[data-copy]").on("click", () => frappe.utils.copy_to_clipboard(r.script));
	d.show();
}

function marketplace_meta_connect(frm) {
	const explorer = "https://developers.facebook.com/tools/explorer/";
	const d = new frappe.ui.Dialog({
		title: __("Facebook sahifani ulash"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<ol style="padding-left:18px;line-height:1.7;margin-bottom:12px">
					<li>${__("Oching")}: <a href="${explorer}" target="_blank" rel="noopener">Graph API Explorer</a></li>
					<li>${__("Meta App — bizning ilova; User or Page — «Get User Access Token»")}</li>
					<li>${__("Ruxsatlar")}: <code>pages_show_list</code>, <code>pages_read_engagement</code>, <code>pages_manage_metadata</code>, <code>pages_manage_ads</code>, <code>leads_retrieval</code>, <code>business_management</code>, <code>instagram_basic</code>, <code>instagram_manage_comments</code>, <code>instagram_manage_messages</code>, <code>pages_messaging</code>, <code>ads_read</code></li>
					<li>${__("Facebook oynasida do'konning Instagram akkaunti va reklama kabinetini ham belgilang")}</li>
					<li>${__("«Generate Access Token» → sahifani tanlang → tokenni nusxalab pastga qo'ying")}</li>
				</ol>
				<div class="text-muted small">${__("Token saqlanmaydi: undan faqat sahifa tokeni olinadi va shifrlanib saqlanadi.")}</div>`,
			},
			{ fieldname: "user_token", fieldtype: "Small Text", label: __("Access token"), reqd: 1 },
		],
		primary_action_label: __("Ulash"),
		primary_action(values) {
			const run = (page_id) =>
				frappe
					.call({
						method: "marketplace.sotuv.meta.connect",
						args: { shop: frm.doc.name, user_token: values.user_token, page_id },
						freeze: true,
						freeze_message: __("Meta bilan bog'lanmoqda…"),
					})
					.then((r) => {
						const m = r.message || {};
						if (m.pages) return pick(m.pages);
						d.hide();
						frappe.msgprint({
							title: __("Ulandi"),
							indicator: m.warning ? "orange" : "green",
							message: __("«{0}» sahifasi ulandi, formalar: {1}.", [m.page, m.forms]) + (m.ig_username ? `<br>${__("Instagram")}: @${frappe.utils.escape_html(m.ig_username)}` : "")
								+ (m.meta_ad_account ? `<br>${__("Reklama kabineti")}: ${frappe.utils.escape_html(m.meta_ad_account)}` : "")
								+ (m.warning ? `<br><br>${frappe.utils.escape_html(m.warning)}` : "")
								+ "<br><br>" + __("Endi jadvalda har bir formaga tovarni tanlab saqlang."),
						});
						frm.reload_doc();
					});
			const pick = (pages) => {
				const p = new frappe.ui.Dialog({
					title: __("Qaysi sahifa?"),
					fields: [{ fieldname: "page", fieldtype: "Select", label: __("Facebook sahifa"), reqd: 1,
						options: pages.map((x) => ({ value: x.id, label: x.name })) }],
					primary_action_label: __("Ulash"),
					primary_action(v) {
						p.hide();
						run(v.page);
					},
				});
				p.show();
			};
			run();
		},
	});
	d.show();
}

// ---------- Chegirma barabani: tanlangan tovar kartochkasi va rasmli "Tovar tanlash" oynasi ----------
function baraban_style() {
	if (document.getElementById("mp-bb-style")) return;
	const css = `
	.mp-bb-pick { margin-top: 8px; }
	.mp-bb-card { display: flex; align-items: center; gap: 12px; padding: 10px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-bg); }
	.mp-bb-card img, .mp-bb-ph { width: 64px; height: 64px; flex: none; border-radius: 10px; object-fit: cover; background: var(--subtle-fg); }
	.mp-bb-card__name { font-weight: 600; }
	.mp-bb-card__meta { color: var(--text-muted); font-size: 12px; }
	.mp-bb-card__price { margin-top: 2px; }
	.mp-bb-card__price b { color: var(--green-600, #16a34a); }
	.mp-bb-card__price s { color: var(--text-muted); margin-left: 6px; }
	.mp-bb-card .btn { margin-left: auto; white-space: nowrap; }
	.mp-bb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; max-height: 60vh; overflow: auto; padding: 2px; }
	.mp-bb-item { display: flex; flex-direction: column; text-align: left; padding: 0; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-bg); overflow: hidden; cursor: pointer; transition: box-shadow .15s, border-color .15s; }
	.mp-bb-item:hover, .mp-bb-item:focus-visible { border-color: var(--primary); box-shadow: 0 4px 14px rgba(0,0,0,.08); }
	.mp-bb-item.is-active { border-color: var(--primary); box-shadow: 0 0 0 2px var(--primary); }
	.mp-bb-item img, .mp-bb-item .mp-bb-ph { width: 100%; height: auto; aspect-ratio: 1; border-radius: 0; object-fit: cover; }
	.mp-bb-item__body { padding: 8px 10px 10px; }
	.mp-bb-item__name { font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
	.mp-bb-item__price { margin-top: 4px; font-weight: 600; }
	.mp-bb-item__tags { margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap; }
	.mp-bb-tag { font-size: 11px; padding: 1px 6px; border-radius: 999px; background: var(--subtle-fg); color: var(--text-muted); }
	.mp-bb-empty { padding: 24px; text-align: center; color: var(--text-muted); }`;
	const el = document.createElement("style");
	el.id = "mp-bb-style";
	el.textContent = css;
	document.head.append(el);
}

const bb_money = (n) => (n ? `${format_number(n, null, 0)} so'm` : __("narx yo'q"));
const bb_img = (r) => (r.image ? `<img src="${encodeURI(r.image)}" alt="" loading="lazy">` : '<span class="mp-bb-ph"></span>');

function baraban_preview(frm) {
	const field = frm.fields_dict.baraban_tovar;
	if (!field || !field.$wrapper) return;
	baraban_style();
	let box = field.$wrapper.find(".mp-bb-pick");
	if (!box.length) box = $('<div class="mp-bb-pick"></div>').appendTo(field.$wrapper);
	if (frm.is_new()) return box.empty();
	const code = frm.doc.baraban_tovar;
	const button = () =>
		$(`<button type="button" class="btn btn-default btn-sm">${code ? __("Boshqa tovar") : __("Tovar tanlash")}</button>`).on("click", () => baraban_pick(frm));
	if (!code) return box.empty().append(button());
	frappe.call({ method: "marketplace.baraban.tovarlar", args: { shop: frm.doc.name, code } }).then((r) => {
		if (frm.doc.baraban_tovar !== code) return; // tanlov o'zgarib ulgurdi
		const it = (r.message || [])[0];
		if (!it) return box.empty().append(button());
		const e = frappe.utils.escape_html;
		const wheel = flt(frm.doc.baraban_narx);
		const card = $(`<div class="mp-bb-card">
			${bb_img(it)}
			<div>
				<div class="mp-bb-card__name">${e(it.item_name)}</div>
				<div class="mp-bb-card__meta">${e(it.name)}${it.has_variants ? " · " + __("rangli/o'lchamli — chegirma hamma variantga") : ""}${it.is_published ? "" : " · " + __("saytda ko'rinmaydi")}</div>
				<div class="mp-bb-card__price">${wheel ? `<b>${bb_money(wheel)}</b><s>${bb_money(it.price)}</s>` : bb_money(it.price)}</div>
			</div>
		</div>`);
		card.append(button());
		box.empty().append(card);
	});
}

function baraban_pick(frm) {
	baraban_style();
	const d = new frappe.ui.Dialog({
		title: __("Baraban uchun tovar tanlang"),
		size: "large",
		fields: [
			{ fieldtype: "Data", fieldname: "q", placeholder: __("Qidirish: nomi yoki kodi") },
			{ fieldtype: "HTML", fieldname: "grid" },
		],
	});
	const grid = $('<div class="mp-bb-grid"></div>').appendTo(d.fields_dict.grid.$wrapper);
	const e = frappe.utils.escape_html;
	let seq = 0;
	const load = async () => {
		const mine = ++seq;
		const r = await frappe.call({ method: "marketplace.baraban.tovarlar", args: { shop: frm.doc.name, txt: d.get_value("q") || "" } });
		if (mine !== seq) return; // eski qidiruv javobi
		const items = r.message || [];
		grid.empty();
		if (!items.length) return grid.append(`<div class="mp-bb-empty">${__("Tovar topilmadi")}</div>`);
		for (const it of items) {
			const tags = [it.has_variants ? __("rangli/o'lchamli") : "", it.is_published ? "" : __("saytda yo'q")].filter(Boolean);
			$(`<button type="button" class="mp-bb-item${it.name === frm.doc.baraban_tovar ? " is-active" : ""}">
				${bb_img(it)}
				<div class="mp-bb-item__body">
					<div class="mp-bb-item__name">${e(it.item_name)}</div>
					<div class="mp-bb-item__price">${bb_money(it.price)}</div>
					${tags.length ? `<div class="mp-bb-item__tags">${tags.map((t) => `<span class="mp-bb-tag">${e(t)}</span>`).join("")}</div>` : ""}
				</div>
			</button>`)
				.on("click", () => {
					frm.set_value("baraban_tovar", it.name);
					d.hide();
				})
				.appendTo(grid);
		}
	};
	d.fields_dict.q.$input.on("input", frappe.utils.debounce(load, 250));
	d.show();
	load();
}
