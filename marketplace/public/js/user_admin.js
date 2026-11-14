// User formasi (admin uchun): do'kon a'zoligi aniq ko'rinadi va bitta tugma bilan beriladi (admin.attach_user_to_shop).
// Rollar ro'yxati — ERPNext'ning standart ko'rinishi. Do'kon rollari a'zolikdan keladi (shop.user_validate).
frappe.ui.form.on("User", {
	refresh(frm) {
		if (!frappe.user.has_role(["System Manager", "Marketplace Manager"])) return;
		if (frm.is_new() || ["Administrator", "Guest"].includes(frm.doc.name)) return;
		frappe.xcall("marketplace.admin.user_shop", { user: frm.doc.name }).then((m) => {
			const esc = frappe.utils.escape_html;
			if (m.shop) {
				frm.set_intro(`<b>${esc(m.shop_name)}</b> ${__("do‘koni")} — <b>${esc(m.role)}</b>. ${esc(m.access || "")}`, "blue");
			} else if (frm.doc.roles?.some((r) => ["Shop Seller", "Shop Courier", "Shop Sales Manager", "Shop Packer", "Shop Supervisor"].includes(r.role))) {
				frm.set_intro(__("Hech qaysi do‘konga biriktirilmagan — do‘kon ma’lumotlarini ko‘rmaydi. «Do‘konga biriktirish» ni bosing."), "orange");
			}
			frm.add_custom_button(m.shop ? __("Do‘kon / rolni o‘zgartirish") : __("Do‘konga biriktirish"), () => mp_attach_dialog(frm, m));
		});
	},
});

function mp_attach_dialog(frm, m) {
	const esc = frappe.utils.escape_html;
	const d = new frappe.ui.Dialog({
		title: __("Do‘konga biriktirish"),
		fields: [
			{ fieldtype: "Link", fieldname: "shop", label: __("Do‘kon"), options: "Shop", reqd: 1, default: m.shop },
			{ fieldtype: "Select", fieldname: "role", label: __("Rol"), reqd: 1, options: Object.keys(m.roles).join("\n"), default: m.role || "Ega" },
			{
				fieldtype: "HTML",
				options: `<div class="small text-muted">${Object.entries(m.roles).map(([r, a]) => `<div><b>${esc(r)}</b> — ${esc(a)}</div>`).join("")}
					<div style="margin-top:6px">${__("Tizim roli, do‘kon ruxsatlari va menyular o‘zi qo‘yiladi; ERPNext modullari yopiladi.")}</div></div>`,
			},
		],
		primary_action_label: __("Saqlash"),
		primary_action: async (v) => {
			await frappe.xcall("marketplace.admin.attach_user_to_shop", { user: frm.doc.name, shop: v.shop, role: v.role });
			d.hide();
			frappe.show_alert({ message: __("Biriktirildi: {0} — {1}", [v.shop, v.role]), indicator: "green" });
			frm.reload_doc();
		},
	});
	d.show();
}
