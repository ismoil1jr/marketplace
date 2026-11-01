// Ro'yxatda telefon: +998 90 123 45 67
frappe.listview_settings["Doimiy Mijoz"] = {
	formatters: {
		phone(value) {
			const d = (value || "").replace(/\D/g, "");
			if (d.length !== 12) return frappe.utils.escape_html(value || "");
			return `+${d.slice(0, 3)} ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10, 12)}`;
		},
	},
};
