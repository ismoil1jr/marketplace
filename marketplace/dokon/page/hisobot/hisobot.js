// Hisobot: oyma-oy sotuvlar — tushum, buyurtmalar, eng ko'p sotilgan tovarlar, kategoriyalar, to'lov turlari.

const MP_MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];

frappe.pages["hisobot"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Hisobot"),
		single_column: true,
	});
	wrapper.report = new SalesReport(page);
};

frappe.pages["hisobot"].on_page_show = function (wrapper) {
	wrapper.report?.load();
};

class SalesReport {
	constructor(page) {
		this.page = page;
		const now = new Date();
		this.state = { year: now.getFullYear(), month: now.getMonth() + 1, shop: "", metric: "revenue", top: "by_qty" };
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.make_filters();
		this.$body = $(`<div class="mp-rep"></div>`).appendTo(page.main);
		this.inject_style();
	}

	make_filters() {
		this.year_field = this.page.add_field({
			fieldname: "year",
			label: __("Yil"),
			fieldtype: "Select",
			options: [String(this.state.year)],
			default: String(this.state.year),
			change: () => this.set_filter("year", this.year_field.get_value()),
		});
		this.month_field = this.page.add_field({
			fieldname: "month",
			label: __("Oy"),
			fieldtype: "Select",
			options: [{ value: "0", label: __("Butun yil") }, ...MP_MONTHS.map((m, i) => ({ value: String(i + 1), label: __(m) }))],
			default: String(this.state.month),
			change: () => this.set_filter("month", this.month_field.get_value()),
		});
	}

	// Admin uchun do'kon tanlovi (sotuvchiga ko'rinmaydi, server baribir o'z do'konini qaytaradi)
	make_shop_filter(shops) {
		if (this.shop_field || !shops.length) return;
		this.shop_field = this.page.add_field({
			fieldname: "shop",
			label: __("Do'kon"),
			fieldtype: "Select",
			options: [{ value: "", label: __("Barcha do'konlar") }, ...shops.map((s) => ({ value: s.name, label: s.shop_name || s.name }))],
			default: "",
			change: () => this.set_filter("shop", this.shop_field.get_value() || ""),
		});
	}

	set_filter(key, value) {
		if (String(this.state[key]) === String(value ?? "")) return;
		this.state[key] = value ?? "";
		this.load();
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-rep__loading text-muted">${__("Yuklanmoqda…")}</div>`);
		const { message } = await frappe.call("marketplace.reports.get_sales_report", {
			year: this.state.year,
			month: this.state.month,
			shop: this.state.shop || null,
		});
		this.data = message;
		this.sync_filters();
		this.render();
	}

	sync_filters() {
		const d = this.data;
		const years = [...new Set([...d.years, d.year])].sort((a, b) => b - a).map(String);
		this.year_field.df.options = years;
		this.year_field.refresh();
		this.year_field.set_input(String(d.year));
		this.month_field.set_input(String(d.month));
		if (d.is_admin) this.make_shop_filter(d.shops);
	}

	period_label() {
		const { year, month } = this.data;
		return month ? `${__(MP_MONTHS[month - 1])} ${year}` : `${year} ${__("yil")}`;
	}

	render() {
		const d = this.data;
		const s = d.summary;
		const esc = frappe.utils.escape_html;
		const prev_label = d.month ? __("o'tgan oyga nisbatan") : __("o'tgan yilga nisbatan");

		const change = (pct) => {
			if (pct === null || pct === undefined) return `<span class="mp-chg mp-chg--none">— ${prev_label}</span>`;
			const cls = pct > 0 ? "up" : pct < 0 ? "down" : "none";
			const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "•";
			return `<span class="mp-chg mp-chg--${cls}">${arrow} ${Math.abs(pct)}% <span>${prev_label}</span></span>`;
		};
		const card = (label, value, hint = "", cls = "") => `
			<div class="mp-stat ${cls}">
				<div class="mp-stat__label">${label}</div>
				<div class="mp-stat__value">${value}</div>
				${hint ? `<div class="mp-stat__hint">${hint}</div>` : ""}
			</div>`;

		this.$body.html(`
			<div class="mp-rep__period">
				<span class="mp-rep__title">${esc(this.period_label())}</span>
				${d.shop && d.is_admin ? `<span class="mp-tag">${esc(d.shop)}</span>` : ""}
			</div>
			<div class="mp-stats">
				${card(__("Tushum"), this.fmt(s.revenue), change(s.change.revenue), "mp-stat--main")}
				${card(__("Buyurtmalar"), s.orders, change(s.change.orders))}
				${card(__("To‘langan"), s.paid, change(s.change.paid))}
				${card(__("Kutilmoqda"), s.pending, s.pending ? `${this.fmt(s.pending_amount)}` : "")}
				${card(__("Bekor qilingan"), s.cancelled, s.delivered ? `${s.delivered} ${__("ta yetkazilgan")}` : "")}
			</div>

			<div class="mp-box">
				<div class="mp-box__head">
					<div class="mp-box__title">${__("{0} yil, oylar bo‘yicha", [d.year])}</div>
					<div class="mp-seg" data-group="metric">
						<button data-val="revenue" class="${this.state.metric === "revenue" ? "is-active" : ""}">${__("Tushum")}</button>
						<button data-val="orders" class="${this.state.metric === "orders" ? "is-active" : ""}">${__("Buyurtmalar")}</button>
					</div>
				</div>
				<div class="mp-chart"></div>
				<div class="mp-box__foot text-muted">${__("Ustunni bossangiz, o‘sha oy hisoboti ochiladi")}</div>
			</div>

			<div class="mp-box">
				<div class="mp-box__head">
					<div class="mp-box__title">${__("Eng ko‘p sotilganlar")} <span class="text-muted">· ${esc(this.period_label())}</span></div>
					<div class="mp-seg" data-group="top">
						<button data-val="by_qty" class="${this.state.top === "by_qty" ? "is-active" : ""}">${__("Soni bo‘yicha")}</button>
						<button data-val="by_amount" class="${this.state.top === "by_amount" ? "is-active" : ""}">${__("Summa bo‘yicha")}</button>
					</div>
				</div>
				<div class="mp-top"></div>
			</div>

			<div class="mp-two">
				<div class="mp-box">
					<div class="mp-box__head"><div class="mp-box__title">${__("Kategoriyalar bo‘yicha")}</div></div>
					<div class="mp-cats"></div>
				</div>
				<div class="mp-box">
					<div class="mp-box__head"><div class="mp-box__title">${__("To‘lov turlari")}</div></div>
					<div class="mp-pays"></div>
				</div>
			</div>
		`);

		this.render_chart();
		this.render_top();
		this.render_bars(this.$body.find(".mp-cats"), d.categories.map((c) => ({ label: c.item_group, amount: c.amount, sub: `${format_number(c.qty, null, 0)} ${__("dona")}` })));
		this.render_bars(
			this.$body.find(".mp-pays"),
			d.payment_methods.filter((p) => p.orders).map((p) => ({
				label: p.method,
				amount: p.amount,
				sub: `${p.orders} ${__("ta buyurtma")} · ${__("to‘langan")}: ${this.fmt(p.paid_amount)}`,
			}))
		);
		this.bind();
	}

	render_chart() {
		const d = this.data;
		const $el = this.$body.find(".mp-chart");
		const is_rev = this.state.metric === "revenue";
		const values = d.monthly.map((m) => (is_rev ? m.revenue : m.orders));
		if (!values.some(Boolean)) {
			$el.html(`<div class="mp-empty text-muted">${__("{0} yilda hali sotuv yo‘q", [d.year])}</div>`);
			return;
		}
		this.chart = new frappe.Chart($el.get(0), {
			type: "bar",
			height: 240,
			data: {
				labels: MP_MONTHS.map((m) => __(m).slice(0, 3)),
				datasets: [{ name: is_rev ? __("Tushum") : __("Buyurtmalar"), values }],
			},
			colors: [is_rev ? "green" : "blue"],
			barOptions: { spaceRatio: 0.4 },
			axisOptions: { xIsSeries: true, shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (v) => (is_rev ? this.fmt(v) : `${v} ${__("ta")}`) },
			isNavigable: false,
		});
		// Ustun bosilganda shu oyni tanlaymiz
		$el.off("click.mp").on("click.mp", "rect.bar", (e) => {
			const month = Number($(e.currentTarget).closest("[data-point-index]").attr("data-point-index")) + 1;
			if (month >= 1 && month <= 12) {
				this.month_field.set_value(String(month));
			}
		});
	}

	render_top() {
		const list = this.data.top_products[this.state.top] || [];
		const $el = this.$body.find(".mp-top");
		if (!list.length) {
			$el.html(`<div class="mp-empty text-muted">${__("Bu davrda sotilgan tovar yo‘q")}</div>`);
			return;
		}
		const esc = frappe.utils.escape_html;
		const max = Math.max(...list.map((p) => (this.state.top === "by_qty" ? p.qty : p.amount))) || 1;
		$el.html(`
			<div class="mp-table">
				<div class="mp-row mp-row--head text-muted">
					<span>#</span><span>${__("Tovar")}</span><span class="mp-num">${__("Sotildi")}</span><span class="mp-num">${__("Tushum")}</span>
				</div>
				${list
					.map((p, i) => {
						const share = ((this.state.top === "by_qty" ? p.qty : p.amount) / max) * 100;
						const initials = esc((p.item_name || "?").trim().slice(0, 2).toUpperCase());
						return `
						<a class="mp-row" href="/desk/item/${encodeURIComponent(p.item_code)}">
							<span class="mp-rank">${i + 1}</span>
							<span class="mp-prod">
								<span class="mp-thumb">${p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy">` : initials}</span>
								<span class="mp-prod__txt">
									<span class="mp-prod__name">${esc(p.item_name)}</span>
									<span class="mp-prod__sub text-muted">${esc(p.item_group || "")}${p.variants > 1 ? ` · ${p.variants} ${__("variant")}` : ""}</span>
									<span class="mp-meter"><i style="width:${share.toFixed(1)}%"></i></span>
								</span>
							</span>
							<span class="mp-num"><b>${format_number(p.qty, null, 0)}</b> <span class="text-muted">${__("dona")}</span></span>
							<span class="mp-num">${this.fmt(p.amount)}</span>
						</a>`;
					})
					.join("")}
			</div>`);
	}

	render_bars($el, rows) {
		if (!rows.length) {
			$el.html(`<div class="mp-empty text-muted">${__("Ma’lumot yo‘q")}</div>`);
			return;
		}
		const esc = frappe.utils.escape_html;
		const total = rows.reduce((a, r) => a + r.amount, 0) || 1;
		$el.html(
			rows
				.map((r) => {
					const pct = (r.amount / total) * 100;
					return `
					<div class="mp-bar">
						<div class="mp-bar__top">
							<span class="mp-bar__label">${esc(r.label)}</span>
							<span class="mp-bar__val">${this.fmt(r.amount)} <span class="text-muted">${Math.round(pct)}%</span></span>
						</div>
						<div class="mp-meter"><i style="width:${pct.toFixed(1)}%"></i></div>
						<div class="mp-bar__sub text-muted">${r.sub}</div>
					</div>`;
				})
				.join("")
		);
	}

	bind() {
		this.$body.find(".mp-seg button").on("click", (e) => {
			const group = $(e.currentTarget).closest(".mp-seg").data("group");
			this.state[group] = e.currentTarget.dataset.val;
			$(e.currentTarget).addClass("is-active").siblings().removeClass("is-active");
			group === "metric" ? this.render_chart() : this.render_top();
		});
	}

	// UZS uchun Frappe noto'g'ri belgi ko'rsatadi — o'zimiz formatlaymiz
	fmt(n) {
		return `${format_number(n || 0, null, 0)} so‘m`;
	}

	inject_style() {
		if (document.getElementById("mp-rep-style")) return;
		$(`<style id="mp-rep-style">
			.mp-rep { padding: 4px 0 40px; }
			.mp-rep__loading, .mp-empty { padding: 40px 0; text-align: center; }
			.mp-rep__period { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
			.mp-rep__title { font-size: var(--text-xl); font-weight: 600; color: var(--heading-color); }
			.mp-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 16px; }
			.mp-stat { padding: 14px 16px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); min-width: 0; }
			.mp-stat--main { grid-column: span 2; }
			@media (max-width: 480px) { .mp-stats { grid-template-columns: 1fr 1fr; } .mp-stat--main { grid-column: 1 / -1; } }
			.mp-stat__label { color: var(--text-muted); font-size: var(--text-sm); }
			.mp-stat__value { margin-top: 4px; font-size: 24px; font-weight: 600; color: var(--heading-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-stat__hint { margin-top: 2px; color: var(--text-muted); font-size: var(--text-xs); }
			.mp-chg { font-size: var(--text-xs); font-weight: 600; }
			.mp-chg span { font-weight: 400; color: var(--text-muted); }
			.mp-chg--up { color: var(--green-600, #16794c); }
			.mp-chg--down { color: var(--red-600, #c0392b); }
			.mp-chg--none { color: var(--text-muted); font-weight: 400; }
			.mp-box { margin-bottom: 16px; padding: 14px 16px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); min-width: 0; }
			.mp-box__head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin-bottom: 10px; }
			.mp-box__title { font-weight: 600; color: var(--heading-color); }
			.mp-box__foot { font-size: var(--text-xs); }
			.mp-chart rect.bar { cursor: pointer; }
			.mp-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
			.mp-two .mp-box { margin-bottom: 0; }
			@media (max-width: 768px) { .mp-two { grid-template-columns: 1fr; } }
			.mp-seg { display: inline-flex; padding: 3px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-seg button { border: 0; background: none; padding: 4px 10px; border-radius: var(--border-radius-sm); font-size: var(--text-sm); color: var(--text-muted); }
			.mp-seg button.is-active { background: var(--card-bg); color: var(--text-color); box-shadow: var(--shadow-sm); }
			.mp-tag { padding: 2px 8px; border-radius: 10px; background: var(--subtle-fg); color: var(--text-muted); font-size: var(--text-xs); }
			.mp-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) 90px 140px; gap: 10px; align-items: center; padding: 8px 4px; border-top: 1px solid var(--border-color); color: var(--text-color); }
			a.mp-row:hover { background: var(--subtle-fg); text-decoration: none; color: var(--text-color); }
			.mp-row--head { border-top: 0; font-size: var(--text-xs); padding-top: 0; }
			.mp-num { text-align: right; white-space: nowrap; }
			.mp-rank { color: var(--text-muted); font-weight: 600; text-align: center; }
			.mp-prod { display: flex; align-items: center; gap: 10px; min-width: 0; }
			.mp-thumb { display: grid; place-items: center; flex: none; width: 44px; height: 44px; overflow: hidden; border-radius: var(--border-radius-md); background: var(--subtle-fg); color: var(--text-muted); font-size: var(--text-xs); font-weight: 600; }
			.mp-thumb img { width: 100%; height: 100%; object-fit: cover; }
			.mp-prod__txt { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
			.mp-prod__name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-prod__sub { font-size: var(--text-xs); }
			.mp-meter { height: 4px; border-radius: 2px; background: var(--subtle-fg); overflow: hidden; }
			.mp-meter i { display: block; height: 100%; min-width: 6px; border-radius: 2px; background: var(--primary); }
			@media (max-width: 560px) {
				.mp-row { grid-template-columns: 22px minmax(0, 1fr) auto; }
				.mp-row > :nth-child(4) { grid-column: 2 / -1; text-align: left; font-size: var(--text-sm); color: var(--text-muted); }
				.mp-row--head > :nth-child(4) { display: none; }
			}
			.mp-bar { padding: 8px 0; border-top: 1px solid var(--border-color); }
			.mp-bar:first-child { border-top: 0; padding-top: 0; }
			.mp-bar__top { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 6px; }
			.mp-bar__label { font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
			.mp-bar__val { white-space: nowrap; }
			.mp-bar__sub { margin-top: 4px; font-size: var(--text-xs); }
		</style>`).appendTo(document.head);
	}
}
