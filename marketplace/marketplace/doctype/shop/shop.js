// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shop", {
	setup(frm) {
		// Reklama slaydi faqat shu do'konning saytdagi tovariga olib boradi
		frm.set_query("item", "banners", () => ({
			filters: { shop: frm.doc.name, is_published: 1, disabled: 0, variant_of: ["is", "not set"] },
		}));
	},
	refresh(frm) {
		if (frm.is_new()) return;

		const url = `/s/${encodeURIComponent(frm.doc.name)}`;
		frm.add_custom_button(__("Saytni ochish"), () => window.open(url, "_blank"));
		frm.add_custom_button(__("Havolani nusxalash"), () => frappe.utils.copy_to_clipboard(location.origin + url));

		for (const [layout, label] of [["vitrina", "A — Vitrina"], ["story", "B — Instagram uslubi"], ["katalog", "C — Katalog (ulgurji)"]]) {
			frm.add_custom_button(__(label), () => window.open(`${url}?layout=${layout}`, "_blank"), __("Shablonni ko'rish"));
		}
		frm.add_custom_button(__("Tovarlar"), () => frappe.set_route("List", "Item", { shop: frm.doc.name }), __("Ko'rish"));
		frm.add_custom_button(__("Buyurtmalar"), () => frappe.set_route("List", "Sales Order", { shop: frm.doc.name }), __("Ko'rish"));

		// Admin: Payme/Click kabinetiga yoziladigan webhook manzillari (hamma do'konlar uchun bir xil)
		if (frappe.user.has_role("System Manager") || frappe.user.has_role("Marketplace Manager")) {
			frm.add_custom_button(__("Do'kon paneliga kirish"), () => marketplace_enter_shop(frm.doc.name));
			const api = `${location.origin}/api/method/marketplace`;
			frm.set_df_property(
				"sb_payme",
				"description",
				`Payme Business → kassa → Endpoint URL: <code>${api}.payme.callback</code><br>Hisob maydoni (account): <code>order_id</code>. Kalitni shu yerga qo'ying — u shifrlanib saqlanadi.`
			);
			frm.set_df_property(
				"sb_click",
				"description",
				`Click merchant → xizmat → Prepare URL: <code>${api}.click.prepare</code>, Complete URL: <code>${api}.click.complete</code>`
			);
		}

		frm.set_intro(
			frm.doc.status === "Active"
				? __("Sayt mijozlarga ochiq: {0}", [`<a href="${url}" target="_blank">${location.host}${url}</a>`])
				: __("Sayt mijozlarga yopiq. Ochish uchun Status'ni Active qiling."),
			frm.doc.status === "Active" ? "green" : "orange"
		);
	},
});
