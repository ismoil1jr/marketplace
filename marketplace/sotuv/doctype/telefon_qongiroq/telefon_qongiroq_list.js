// Qo'ng'iroqlar ro'yxati: holat rangli belgi bo'lib (AI tahlil qilinganmi, xatomi)
frappe.listview_settings["Telefon Qongiroq"] = {
	add_fields: ["holat", "natija"],
	get_indicator(doc) {
		const color = { Yangi: "gray", "Yozuv bor": "blue", Transkripsiya: "orange", "Tahlil qilindi": "green", Xato: "red" }[doc.holat] || "gray";
		return [__(doc.holat || "Yangi"), color, `holat,=,${doc.holat || "Yangi"}`];
	},
};
