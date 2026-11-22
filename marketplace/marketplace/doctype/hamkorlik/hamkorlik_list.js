frappe.listview_settings["Hamkorlik"] = {
	add_fields: ["holat", "pdf_fayl"],
	get_indicator(doc) {
		const color = { Yangi: "orange", Imzolangan: "green", "Bekor qilingan": "red" }[doc.holat] || "gray";
		return [__(doc.holat), color, `holat,=,${doc.holat}`];
	},
	formatters: {
		pdf_fayl(value) {
			return value ? `<a href="${encodeURI(value)}" target="_blank" onclick="event.stopPropagation()">PDF ⬇</a>` : "";
		},
	},
};
