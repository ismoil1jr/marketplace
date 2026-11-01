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
	const courier_name = d.mp_courier ? frappe.user.full_name(d.mp_courier) : "";
	const cash_pill = d.mp_cash_status === "Kuryerda"
		? ` <span class="indicator-pill orange">Naqd kuryerda: ${frappe.utils.escape_html(courier_name)}</span>`
		: d.mp_cash_status === "Topshirilmoqda"
			? ` <span class="indicator-pill orange">${frappe.utils.escape_html(courier_name)} pulni topshirdi — tasdiqlang</span>`
		: d.mp_cash_status === "Do'konga topshirildi"
			? ` <span class="indicator-pill green">Naqd do'konga topshirildi</span>`
			: "";
	frm.dashboard.set_headline(
		`<span class="indicator-pill ${status[1]}">${status[0]}</span>` +
			(delivered ? ` <span class="indicator-pill green">Topshirilgan</span>` : "") +
			cash_pill
	);

	// Mijoz anketasi (tug'ilgan kuni, farzandlari): kuryer ham, do'kon egasi ham to'ldira oladi
	frm.add_custom_button("Mijozni ro'yxatga olish", () => open_loyal_customer(frm));

	if (frappe.boot.marketplace_shop.courier) {
		courier_buttons(frm, call, delivered);
		return;
	}
	if (["Kuryerda", "Topshirilmoqda"].includes(d.mp_cash_status)) {
		frm.add_custom_button("Kuryerdan pul olindi", () =>
			frappe.confirm(
				`${frappe.utils.escape_html(courier_name)} sizga ${format_currency(d.grand_total, d.currency)} naqd pulni topshirdimi?`,
				() => frappe.xcall("marketplace.kassa.accept_cash", { orders: [d.name] }).then(() => {
					frappe.show_alert({ message: "Pul do'konga qabul qilindi", indicator: "green" });
					frm.reload_doc();
				})
			)
		).addClass("btn-primary");
	}

	// Kuryer bilan yetkaziladigan naqd buyurtmani do'konchi yopadi: tovar berildi, pul do'kon kassasida (kassa.deliver_cash).
	// Pul kuryerda qolgan bo'lsa — kuryer o'z sahifasidagi "Naqd olindi, mijozga topshirildi" tugmasini bosadi
	const courier_cash = d.delivery_method === "Kuryer" && d.payment_method === "Naqd" && !paid && !delivered && d.payment_status !== "Bekor";
	if (courier_cash) {
		frm.add_custom_button("Mijozga topshirildi va naqd olindi", () =>
			frappe.confirm(
				`Tovar mijozga berildimi va ${format_currency(d.grand_total, d.currency)} naqd olindimi?<br>
				<small class="text-muted">Tovar ombordan ayriladi, pul do'kon kassasiga yoziladi.</small>`,
				() => frappe.xcall("marketplace.kassa.deliver_cash", { order: d.name, by: "shop" }).then(() => {
					frappe.show_alert({ message: "Topshirildi, naqd kassada", indicator: "green" });
					frm.reload_doc();
				})
			)
		).addClass("btn-primary");
	}
	if (d.payment_method === "Naqd" && !paid && !courier_cash) {
		frm.add_custom_button("Naqd pul olindi", () =>
			frappe.confirm(`${format_currency(d.grand_total, d.currency)} naqd olindimi?`, () =>
				call("mark_cash_received", {}, "Naqd to'lov belgilandi")
			)
		).addClass("btn-primary");
	}
	if (!delivered && !courier_cash && d.payment_status !== "Bekor" && (paid || d.payment_method === "Naqd")) {
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

// Kuryer: bitta asosiy tugma. Naqdda — pulni oldi va tovarni berdi (pul "kuryerda" bo'lib turadi)
function courier_buttons(frm, call, delivered) {
	const d = frm.doc;
	if (delivered || d.payment_status === "Bekor") return;
	const cash = d.payment_method === "Naqd" && d.payment_status !== "To'langan";
	const paid = d.payment_status === "To'langan";
	if (!cash && !paid) {
		frm.dashboard.set_headline_alert("Mijoz hali to'lamagan — to'lovdan keyin topshiring", "orange");
		return;
	}
	const label = cash ? "Naqd olindi, mijozga topshirildi" : "Mijozga topshirildi";
	const question = cash
		? `Mijozdan ${format_currency(d.grand_total, d.currency)} naqd oldingizmi va tovarni berdingizmi?`
		: "Tovarni mijozga berdingizmi?";
	frm.add_custom_button(label, () =>
		frappe.confirm(question, () =>
			frappe.xcall("marketplace.seller_desk.courier_delivered", { order: d.name }).then((r) => {
				frappe.show_alert({
					message: r === "cash" ? "Topshirildi. Pul «Qo'limdagi naqd»da — keyin do'kon kassiriga topshiring" : "Topshirildi",
					indicator: "green",
				});
				frm.reload_doc().then(() => open_loyal_customer(frm, true));
			})
		)
	).addClass("btn-primary");
}

// Shu raqam ro'yxatda bo'lsa — anketasini ochadi, bo'lmasa buyurtmadagi ism/telefon bilan yangisini
function open_loyal_customer(frm, after_delivery = false) {
	frappe
		.xcall("marketplace.marketplace.doctype.doimiy_mijoz.doimiy_mijoz.from_order", { order: frm.doc.name })
		.then((r) => {
			if (r.existing) {
				if (!after_delivery) frappe.set_route("Form", "Doimiy Mijoz", r.existing);
				return;
			}
			const go = () => frappe.new_doc("Doimiy Mijoz", r);
			if (!after_delivery) return go();
			frappe.confirm(
				"Mijozni doimiy mijozlar ro'yxatiga qo'shamizmi? (tug'ilgan kuni va farzandlari — chegirma va sovg'alar uchun)",
				go
			);
		});
}
