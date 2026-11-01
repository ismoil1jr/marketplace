// Kuryer kassasi: qo'limdagi naqd pul (qaysi buyurtmalardan) va "Do'kon kassiriga topshirish" (kassa.py).
// Topshirilgach pul "Tasdiq kutilmoqda" bo'ladi; do'konchi Do'konim'da "Qabul qildim" bosgandagina kassaga o'tadi.

frappe.pages["kuryer-kassa"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Kuryer kassasi"), single_column: true });
	wrapper.kassa = new KuryerKassa(page);
};

frappe.pages["kuryer-kassa"].on_page_show = function (wrapper) {
	wrapper.kassa?.load();
};

class KuryerKassa {
	constructor(page) {
		this.page = page;
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-kk"></div>`).appendTo(page.main);
		this.inject_style();
		frappe.realtime.on("marketplace_new_order", () => this.load());
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-kk__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		this.data = await frappe.xcall("marketplace.kassa.courier_cash");
		this.render();
	}

	money(x) {
		return `${format_number(x || 0, null, 0)} so‘m`;
	}

	row(o, when) {
		const esc = frappe.utils.escape_html;
		return `
			<a class="mp-kk__row" href="/desk/sales-order/${encodeURIComponent(o.name)}">
				<span><b>${esc(o.customer_name || "—")}</b><small>${esc(o.name)}${when ? ` · ${esc(frappe.datetime.str_to_user(when))}` : ""}</small></span>
				<b>${this.money(o.grand_total)}</b>
			</a>`;
	}

	render() {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		this.$body.html(`
			<div class="mp-kk__hero">
				<div class="mp-kk__label">${__("Qo‘limdagi naqd")}</div>
				<div class="mp-kk__total">${this.money(d.in_hand_total)}</div>
				<div class="mp-kk__sub">${d.in_hand.length} ${__("ta buyurtmadan")} · ${esc(d.courier)} · ${esc(d.shop_name || "")}</div>
				<button class="btn btn-primary btn-lg mp-kk__btn" data-handover ${d.in_hand.length ? "" : "disabled"}>
					💵 ${__("Do‘kon kassiriga topshirish")}
				</button>
				${d.in_hand.length ? "" : `<div class="mp-kk__sub">${__("Qo‘lingizda topshiriladigan pul yo‘q")}</div>`}
			</div>

			${d.in_hand.length ? `<div class="mp-kk__sec">${__("Qaysi buyurtmalardan")}</div>
				<div class="mp-kk__list">${d.in_hand.map((o) => this.row(o, o.mp_delivered_at)).join("")}</div>` : ""}

			${d.sent.length ? `<div class="mp-kk__sec mp-kk__sec--wait">⏳ ${__("Do‘konchi tasdiqlashini kutmoqda")} · ${this.money(d.sent_total)}</div>
				<div class="mp-kk__list">${d.sent.map((o) => this.row(o, o.mp_cash_sent_at)).join("")}</div>
				<div class="mp-kk__note text-muted small">${__("Do‘konchi «Qabul qildim» bosgach, bu pul do‘kon kassasiga o‘tadi va sizdan tushadi.")}</div>` : ""}

			${d.handed.length ? `<div class="mp-kk__sec">✅ ${__("Oxirgi topshirilganlar")}</div>
				<div class="mp-kk__list">${d.handed.map((o) => this.row(o, o.mp_cash_handed_at)).join("")}</div>` : ""}
		`);
		this.$body.find("[data-handover]").on("click", () => this.handover());
	}

	handover() {
		const d = this.data;
		frappe.confirm(
			__("Do‘kon kassiriga {0} naqd pul topshiryapsizmi? ({1} ta buyurtma)", [this.money(d.in_hand_total), d.in_hand.length]),
			async () => {
				const r = await frappe.xcall("marketplace.kassa.courier_handover", { orders: d.in_hand.map((o) => o.name) });
				frappe.show_alert({ message: __("{0} topshirildi — do‘konchi tasdiqlashini kuting", [this.money(r.total)]), indicator: "green" });
				this.load();
			}
		);
	}

	inject_style() {
		if (document.getElementById("mp-kk-style")) return;
		$(`<style id="mp-kk-style">
			.mp-kk { max-width: 640px; margin: 0 auto; padding: 8px 0 40px; }
			.mp-kk__empty { padding: 60px 0; text-align: center; }
			.mp-kk__hero { display: grid; justify-items: center; gap: 6px; padding: 24px 16px; border-radius: var(--border-radius-lg);
				background: var(--bg-orange, #fff7ed); text-align: center; }
			.mp-kk__label { font-size: var(--text-sm); font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
			.mp-kk__total { font-size: 34px; font-weight: 700; color: var(--heading-color); line-height: 1.1; }
			.mp-kk__sub { font-size: var(--text-sm); color: var(--text-muted); }
			.mp-kk__btn { margin-top: 10px; min-height: 48px; padding: 0 24px; font-size: var(--text-md); }
			.mp-kk__sec { margin: 20px 0 8px; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: .04em; }
			.mp-kk__sec--wait { color: var(--orange-600, #ea580c); }
			.mp-kk__list { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); overflow: hidden; }
			.mp-kk__row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 14px;
				border-top: 1px solid var(--border-color); color: var(--text-color); }
			.mp-kk__row:first-child { border-top: 0; }
			.mp-kk__row:hover { background: var(--subtle-fg); text-decoration: none; color: var(--text-color); }
			.mp-kk__row span { display: grid; min-width: 0; }
			.mp-kk__row small { color: var(--text-muted); }
			.mp-kk__row > b { white-space: nowrap; }
			.mp-kk__note { margin-top: 6px; }
		</style>`).appendTo(document.head);
	}
}
