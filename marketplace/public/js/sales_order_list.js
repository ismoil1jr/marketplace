// Sotuvchi uchun buyurtmalar ro'yxati: ERPNext statusi o'rniga to'lov holati rangli belgi bo'lib chiqadi.
(() => {
	// "To'langan" qiymatidagi apostrof ustunda ikki marta escape bo'lib "To&#39;langan" chiqardi (hamma uchun)
	const base = (frappe.listview_settings["Sales Order"] ||= {});
	base.formatters = {
		...(base.formatters || {}),
		payment_status: (value) => {
			const color = { "To'langan": "green", Kutilmoqda: "orange", Bekor: "red" }[value] || "gray";
			return value ? `<span class="indicator-pill ${color}">${frappe.utils.escape_html(value)}</span>` : "";
		},
	};

	const is_seller =
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;
	if (!is_seller) return;

	const settings = (frappe.listview_settings["Sales Order"] ||= {});
	settings.add_fields = [...(settings.add_fields || []), "payment_status", "payment_method"];
	// Avval to'lovi kutilayotganlar; boshqalarini "To'lov holati" filtrida tanlaydi
	settings.filters = [["payment_status", "=", "Kutilmoqda"]];
	settings.get_indicator = (doc) => {
		if (doc.docstatus === 2 || doc.payment_status === "Bekor") return ["Bekor qilingan", "red", "payment_status,=,Bekor"];
		if (doc.payment_status === "To'langan")
			return [doc.payment_method === "Naqd" ? "Naqd — to'langan" : "To'langan", "green", "payment_status,=,To'langan"];
		if (doc.payment_method === "Naqd") return ["Naqd — kutilmoqda", "orange", "payment_method,=,Naqd"];
		return ["To'lov kutilmoqda", "orange", "payment_status,=,Kutilmoqda"];
	};
})();
