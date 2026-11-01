// Sotuvchi uchun buyurtmalar ro'yxati: ERPNext statusi o'rniga to'lov holati rangli belgi bo'lib chiqadi.
(() => {
	// "To'langan" qiymatidagi apostrof ustunda ikki marta escape bo'lib "To&#39;langan" chiqardi (hamma uchun)
	const base = (frappe.listview_settings["Sales Order"] ||= {});
	base.formatters = {
		...(base.formatters || {}),
		// +998998011026 -> +998 99 801 10 26
		customer_phone: (value) => {
			const d = (value || "").replace(/\D/g, "");
			if (d.length !== 12) return frappe.utils.escape_html(value || "");
			return `+${d.slice(0, 3)} ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10, 12)}`;
		},
		payment_status: (value) => {
			const color = { "To'langan": "green", Kutilmoqda: "orange", Bekor: "red" }[value] || "gray";
			return value ? `<span class="indicator-pill ${color}">${frappe.utils.escape_html(value)}</span>` : "";
		},
	};

	const is_seller =
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;
	if (!is_seller) return;

	const settings = (frappe.listview_settings["Sales Order"] ||= {});
	settings.add_fields = [...(settings.add_fields || []), "payment_status", "payment_method", "per_delivered", "mp_cash_status"];

	if (frappe.boot.marketplace_shop.courier) {
		// Kuryer: avval hali topshirilmaganlar (to'langan Click/Payme ham, naqd ham)
		settings.filters = [["per_delivered", "<", 100]];
		settings.get_indicator = (doc) => {
			if (doc.docstatus === 2 || doc.payment_status === "Bekor") return ["Bekor qilingan", "red", "payment_status,=,Bekor"];
			if (doc.mp_cash_status === "Kuryerda") return ["Naqd menda", "orange", "mp_cash_status,=,Kuryerda"];
			if (flt(doc.per_delivered) >= 100) return ["Topshirilgan", "green", "per_delivered,>=,100"];
			if (doc.payment_status === "To'langan") return [`To'langan (${doc.payment_method || ""}) — olib boring`, "blue", "per_delivered,<,100"];
			if (doc.payment_method === "Naqd") return ["Naqd — pulni oling", "orange", "payment_method,=,Naqd"];
			return ["To'lov kutilmoqda", "gray", "payment_status,=,Kutilmoqda"];
		};
		return;
	}

	// Kuryerdan bir nechta buyurtma pulini birdaniga qabul qilish
	settings.onload = (list) => {
		list.page.add_actions_menu_item("Kuryerdan pul olindi", () => {
			const names = list.get_checked_items(true);
			frappe.confirm(`${names.length} ta buyurtma naqd puli kuryerdan olindimi?`, () =>
				frappe.xcall("marketplace.seller_desk.cash_handed_over", { orders: JSON.stringify(names) }).then((n) => {
					frappe.show_alert({ message: `${n} ta buyurtma puli qabul qilindi`, indicator: "green" });
					list.refresh();
				})
			);
		});
	};
	// Avval to'lovi kutilayotganlar; boshqalarini "To'lov holati" filtrida tanlaydi
	settings.filters = [["payment_status", "=", "Kutilmoqda"]];
	settings.get_indicator = (doc) => {
		if (doc.mp_cash_status === "Kuryerda") return ["Naqd kuryerda", "orange", "mp_cash_status,=,Kuryerda"];
		if (doc.docstatus === 2 || doc.payment_status === "Bekor") return ["Bekor qilingan", "red", "payment_status,=,Bekor"];
		if (doc.payment_status === "To'langan")
			return [doc.payment_method === "Naqd" ? "Naqd — to'langan" : "To'langan", "green", "payment_status,=,To'langan"];
		if (doc.payment_method === "Naqd") return ["Naqd — kutilmoqda", "orange", "payment_method,=,Naqd"];
		return ["To'lov kutilmoqda", "orange", "payment_status,=,Kutilmoqda"];
	};
})();
