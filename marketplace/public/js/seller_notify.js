// Yangi buyurtma tushganda sotuvchiga: ovoz + bosilsa buyurtmani ochadigan xabar.
// Qo'ng'iroqchadagi (bell) yozuvni server Notification Log orqali qo'yadi.
$(document).on("app_ready", () => {
	frappe.realtime.on("marketplace_new_order", (data) => {
		frappe.utils.play_sound("alert");
		const alert = frappe.show_alert(
			{ message: `🛒 ${frappe.utils.escape_html(data.subject)}`, indicator: "green" },
			20
		);
		alert?.on?.("click", () => frappe.set_route("Form", "Sales Order", data.name));
		const list = window.cur_list;
		if (list && list.doctype === "Sales Order") list.refresh();
	});
});

// Admin: do'kon paneliga kirish (shops-overview va Shop formasidan). Admin o'z akkauntida qoladi.
window.marketplace_enter_shop = (shop) =>
	frappe
		.xcall("marketplace.admin.enter_shop_panel", { shop }, null, { freeze: true })
		.then((url) => (window.location.href = url));

// Admin do'kon panelida bo'lsa: sahifa tepasida ingichka qator va qaytish tugmasi
$(document).on("app_ready", () => {
	if (!frappe.boot.marketplace_shop?.admin_view) return;
	const $bar = $(`
		<div class="mp-admin-view">
			<span>${frappe.utils.icon("eye", "sm")} <b></b> do'koni paneli — siz admin sifatida ko'ryapsiz</span>
			<button class="btn btn-xs btn-default">Admin paneliga qaytish</button>
		</div>
		<style>
			.mp-admin-view { display: flex; gap: 12px; align-items: center; justify-content: center; flex-wrap: wrap;
				padding: 6px 16px; background: var(--bg-orange, #fff4e5); color: var(--text-color); font-size: var(--text-sm); }
		</style>`);
	$bar.find("b").text(frappe.boot.marketplace_shop.shop_name);
	$bar.find("button").on("click", () =>
		frappe.xcall("marketplace.admin.leave_shop_panel").then((url) => (window.location.href = url))
	);
	$bar.insertBefore("#body");
});
