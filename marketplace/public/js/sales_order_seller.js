// Sotuvchi uchun buyurtma formasi: kerakli 3 ta amal tepada turadi.
frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		const is_seller =
			!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;
		if (!is_seller || frm.doc.docstatus !== 1) return;
		// ERPNext tugmalari (Update Items, Create → Invoice/Payment...) hisob-kitobga tegadi: sotuvchiga kerak emas.
		// ERPNext o'z tugmalarini shu refresh'dan keyin qo'shadi, shuning uchun bir lahza kutamiz.
		setTimeout(() => seller_buttons(frm), 0);
	},
});

function seller_buttons(frm) {
	frm.clear_custom_buttons();
	frm.page.clear_primary_action?.();

	const d = frm.doc;
	const paid = d.payment_status === "To'langan";
	const delivered = flt(d.per_delivered) >= 100;
	const online = ["Payme", "Click"].includes(d.payment_method);
	const call = (method, args, msg) =>
		frappe.xcall(`marketplace.seller_desk.${method}`, { order: d.name, ...args }).then(() => {
			frappe.show_alert({ message: msg, indicator: "green" });
			frm.reload_doc();
		});

	const status = d.payment_status === "Bekor" ? ["Bekor qilingan", "red"]
		: paid ? [d.payment_method === "Naqd" ? "Naqd — to'langan" : `To'langan (${d.payment_method || ""})`, "green"]
		: d.payment_method === "Naqd" ? ["Naqd — to'lov kutilmoqda", "orange"]
		: !d.payment_method ? ["To'lov usuli tanlanmagan", "orange"]
		: ["To'lov kutilmoqda", "orange"];
	frm.dashboard.set_headline(
		`<span class="indicator-pill ${status[1]}">${status[0]}</span>` +
			(delivered ? ` <span class="indicator-pill green">Topshirilgan</span>` : "")
	);

	if (d.payment_method === "Naqd" && !paid) {
		frm.add_custom_button("Naqd pul olindi", () =>
			frappe.confirm(`${format_currency(d.grand_total, d.currency)} naqd olindimi?`, () =>
				call("mark_cash_received", {}, "Naqd to'lov belgilandi")
			)
		).addClass("btn-primary");
	}
	if (!delivered && d.payment_status !== "Bekor" && (paid || d.payment_method === "Naqd")) {
		frm.add_custom_button("Mijozga topshirildi", () =>
			frappe.confirm("Tovar mijozga berildimi? Ombordan ayriladi.", () =>
				call("mark_delivered", {}, "Topshirildi, ombordan ayrildi")
			)
		);
	}
	if (!delivered && !(paid && online)) {
		frm.add_custom_button("Bekor qilish", () =>
			frappe.prompt(
				{ fieldname: "reason", fieldtype: "Small Text", label: "Sababi (ixtiyoriy)" },
				(v) => call("cancel_order", { reason: v.reason }, "Buyurtma bekor qilindi"),
				"Buyurtmani bekor qilish",
				"Bekor qilish"
			)
		);
	}
}
