// Telegram orqali kirgan mijozlar: profil rasmi + @username bitta ustunda, telefon o'qiladigan ko'rinishda
frappe.listview_settings["Telegram Mijoz"] = {
	add_fields: ["photo", "full_name"],
	formatters: {
		username(value, df, doc) {
			const esc = frappe.utils.escape_html;
			const avatar = doc.photo
				? `<img src="${esc(doc.photo)}" alt="" style="width:28px;height:28px;border-radius:50%;object-fit:cover;flex:none">`
				: `<span class="avatar avatar-small" style="flex:none"><span class="avatar-frame standard-image">${esc(frappe.get_abbr(doc.full_name || "?"))}</span></span>`;
			return `<span style="display:inline-flex;align-items:center;gap:8px">${avatar}<span>${esc(value || "—")}</span></span>`;
		},
		// +998998011026 -> +998 99 801 10 26
		phone(value) {
			const d = (value || "").replace(/\D/g, "");
			if (d.length !== 12) return frappe.utils.escape_html(value || "");
			return `+${d.slice(0, 3)} ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10, 12)}`;
		},
	},
};
