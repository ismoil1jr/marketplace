// Do'konim va Kuryer paneli: raqamli kartalar (Kuryerlardagi naqd, Qo'limdagi naqd...) faqat sahifa chizilganda
// hisoblanadi, Frappe esa ochilgan workspace'ga qaytganda uni qayta chizmaydi ("already shown") — eskirgan raqam
// turardi. Shu ikki sahifaga qaytilganda — qayta chizamiz. mp.refresh_workspace() — pul harakatidan keyin (kassa).
window.mp = window.mp || {};

// Xarita maydonlari (Doimiy mijoz → «Xaritadagi joyi» va boshqalar): Frappe standart holda Mumbayni ochadi.
// Nuqta qo'yilmagan bo'lsa — Toshkent markazi; qo'yilgan bo'lsa Frappe o'zi o'sha nuqtaga suradi.
if (frappe.utils?.map_defaults) {
	frappe.utils.map_defaults.center = [41.3111, 69.2797];
	frappe.utils.map_defaults.zoom = 12;
}

// Workspace'da ruxsati yo'q yorliq/karta (masalan nazoratchiga «Mijoz qo'shish») bo'sh katak bo'lib qolardi —
// tahrirlash rejimidan tashqarida yashiramiz. Spacer'ning o'z klassi bor (.widget), unga tegilmaydi
$("<style>")
	.text(".layout-main-section:not(.edit-mode) .ce-block:has(> .ce-block__content > div:empty:not(.widget)) { display: none !important; }")
	.appendTo(document.head);

const MP_LIVE_WORKSPACES = new Set(["Dokonim", "Kuryer"]);
mp.refresh_workspace = () => {
	const ws = frappe.workspace;
	if (!ws?._page) return false;
	ws._page = null;
	ws.show();
	return true;
};
$(document).on("app_ready", () => {
	const proto = frappe.views?.Workspace?.prototype;
	if (!proto || proto._mp_live) return;
	proto._mp_live = true;
	const show = proto.show;
	proto.show = function (...args) {
		if (this.workspaces && MP_LIVE_WORKSPACES.has(this._page?.name) && this.get_page_to_show?.()?.name === this._page.name) {
			this._page = null;
		}
		return show.apply(this, args);
	};
});

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

// Admin do'kon panelida bo'lsa: sahifa tepasida ingichka qator va qaytish tugmasi.
// Admin sahifalariga (Desktop yoki /desk/marketplace/...) o'tsa — do'kon panelidan o'zi chiqadi
$(document).on("app_ready", () => {
	if (!frappe.boot.marketplace_shop?.admin_view) return;
	const in_admin_area = () => {
		const path = location.pathname.replace(/\/+$/, "");
		return path === "/desk" || path === "/desk/marketplace" || path.startsWith("/desk/marketplace/");
	};
	const leave = () => frappe.xcall("marketplace.admin.leave_shop_panel").then(() => window.location.reload());
	if (in_admin_area()) return leave();
	frappe.router.on("change", () => in_admin_area() && leave());
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
