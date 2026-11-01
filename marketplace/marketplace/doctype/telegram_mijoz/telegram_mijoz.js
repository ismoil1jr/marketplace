// Telegram orqali kirgan mijoz: profil rasmi katta ko'rinishda va uning shu do'kondagi buyurtmalari
frappe.ui.form.on("Telegram Mijoz", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.customer) {
			frm.add_custom_button(__("Buyurtmalari"), () =>
				frappe.set_route("List", "Sales Order", { customer: frm.doc.customer, shop: frm.doc.shop })
			);
		}
		if (frm.doc.doimiy_mijoz) {
			frm.add_custom_button(__("Doimiy mijoz anketasi"), () => frappe.set_route("Form", "Doimiy Mijoz", frm.doc.doimiy_mijoz));
		}
		const esc = frappe.utils.escape_html;
		const photo = frm.doc.photo
			? `<img src="${esc(frm.doc.photo)}" alt="" style="width:72px;height:72px;border-radius:50%;object-fit:cover">`
			: `<span class="avatar avatar-xl"><span class="avatar-frame standard-image">${esc(frappe.get_abbr(frm.doc.full_name || "?"))}</span></span>`;
		frm.set_intro(
			`<div style="display:flex;align-items:center;gap:14px">${photo}<div>
				<div style="font-size:var(--text-lg);font-weight:600">${esc(frm.doc.full_name || "")}</div>
				<div class="text-muted">${esc(frm.doc.username || "")}${frm.doc.username && frm.doc.phone ? " · " : ""}${esc(frm.doc.phone || "")}</div>
			</div></div>`,
			"blue"
		);
	},
});
