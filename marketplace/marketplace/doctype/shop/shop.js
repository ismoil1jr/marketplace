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
	},
	refresh(frm) {
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
	const group = __("Instagram (Meta)");
	const connected = !!frm.doc.meta_page_id;
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
					<li>${__("Ruxsatlar")}: <code>pages_show_list</code>, <code>pages_read_engagement</code>, <code>pages_manage_metadata</code>, <code>pages_manage_ads</code>, <code>leads_retrieval</code>, <code>business_management</code></li>
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
							message: __("«{0}» sahifasi ulandi, formalar: {1}.", [m.page, m.forms]) + (m.warning ? `<br><br>${frappe.utils.escape_html(m.warning)}` : "")
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
