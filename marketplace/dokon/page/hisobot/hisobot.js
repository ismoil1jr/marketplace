// Hisobot: tanlangan sanalar oralig'ida kassaga tushgan pul, buyurtmalar, eng ko'p sotilganlar, kategoriyalar,
// to'lov turlari, ombor (avval → keldi → sotildi → kamomad → qoldi) va harakatlar tarixi (mp.journal).

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

// Tez tanlovlar: [qiymat, nom, () => [dan, gacha]]
const MP_PRESETS = (() => {
	const d = (x) => frappe.datetime.obj_to_str(x);
	const today = () => new Date();
	const shift = (days) => {
		const x = today();
		x.setDate(x.getDate() + days);
		return x;
	};
	return [
		["today", "Bugun", () => [d(today()), d(today())]],
		["yesterday", "Kecha", () => [d(shift(-1)), d(shift(-1))]],
		["7", "Oxirgi 7 kun", () => [d(shift(-6)), d(today())]],
		["30", "Oxirgi 30 kun", () => [d(shift(-29)), d(today())]],
		["month", "Shu oy", () => { const t = today(); return [d(new Date(t.getFullYear(), t.getMonth(), 1)), d(t)]; }],
		["prev_month", "O'tgan oy", () => { const t = today(); return [d(new Date(t.getFullYear(), t.getMonth() - 1, 1)), d(new Date(t.getFullYear(), t.getMonth(), 0))]; }],
		["year", "Shu yil", () => { const t = today(); return [d(new Date(t.getFullYear(), 0, 1)), d(t)]; }],
	];
})();

class SalesReport {
	constructor(page) {
		this.page = page;
		const [from, to] = MP_PRESETS.find((p) => p[0] === "month")[2]();
		this.state = { from, to, preset: "month", shop: "", metric: "revenue", top: "by_qty" };
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.make_filters();
		this.$body = $(`<div class="mp-rep"></div>`).appendTo(page.main);
		this.inject_style();
	}

	make_filters() {
		this.preset_field = this.page.add_field({
			fieldname: "preset",
			label: __("Davr"),
			fieldtype: "Select",
			options: [...MP_PRESETS.map(([value, label]) => ({ value, label: __(label) })), { value: "custom", label: __("Boshqa sanalar") }],
			default: this.state.preset,
			change: () => {
				const preset = this.preset_field.get_value();
				const found = MP_PRESETS.find((p) => p[0] === preset);
				this.state.preset = preset;
				if (!found) return;
				const [from, to] = found[2]();
				this.set_range(from, to, preset);
			},
		});
		this.from_field = this.page.add_field({
			fieldname: "from_date",
			label: __("Dan"),
			fieldtype: "Date",
			default: this.state.from,
			change: () => this.on_date_change(),
		});
		this.to_field = this.page.add_field({
			fieldname: "to_date",
			label: __("Gacha"),
			fieldtype: "Date",
			default: this.state.to,
			change: () => this.on_date_change(),
		});
		for (const f of [this.preset_field, this.from_field, this.to_field]) f.$wrapper.addClass("mp-rep-filter");
	}

	on_date_change() {
		if (this._silent) return;
		const from = this.from_field.get_value();
		const to = this.to_field.get_value();
		if (!from || !to || (from === this.state.from && to === this.state.to)) return;
		this.state.preset = "custom";
		this.preset_field.set_input("custom");
		this.set_range(from, to, "custom");
	}

	set_range(from, to, preset) {
		this.state.from = from;
		this.state.to = to;
		this.state.preset = preset || this.state.preset;
		this._silent = true;
		this.from_field.set_input(from);
		this.to_field.set_input(to);
		this.preset_field.set_input(this.state.preset);
		this._silent = false;
		this.load();
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
			change: () => {
				const v = this.shop_field.get_value() || "";
				if (v === this.state.shop) return;
				this.state.shop = v;
				this.load();
			},
		});
		this.shop_field.$wrapper.addClass("mp-rep-filter mp-rep-filter--wide");
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-rep__loading text-muted">${__("Yuklanmoqda…")}</div>`);
		const { message } = await frappe.call("marketplace.reports.get_sales_report", {
			from_date: this.state.from,
			to_date: this.state.to,
			shop: this.state.shop || null,
		});
		this.data = message;
		// Do'kon panelidagi admin: hisobot faqat shu do'kon bo'yicha — tanlov kerak emas
		if (message.is_admin && !frappe.boot.marketplace_shop) this.make_shop_filter(message.shops);
		this.render();
	}

	date_label(s) {
		const [y, m, d] = s.split("-").map(Number);
		return `${d}-${__(MP_MONTHS[m - 1]).toLowerCase()} ${y}`;
	}

	period_label() {
		const { from_date, to_date } = this.data;
		return from_date === to_date ? this.date_label(from_date) : `${this.date_label(from_date)} — ${this.date_label(to_date)}`;
	}

	render() {
		const d = this.data;
		const s = d.summary;
		const st = d.stock?.totals; // admin (do'kon panelidan tashqarida) uchun ombor yo'q
		const esc = frappe.utils.escape_html;
		const prev_label = __("oldingi {0} kunga nisbatan", [d.days]);

		const change = (pct) => {
			if (pct === null || pct === undefined) return "";
			const cls = pct > 0 ? "up" : pct < 0 ? "down" : "none";
			const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "•";
			return `<span class="mp-chg mp-chg--${cls}">${arrow} ${Math.abs(pct)}% <span>${prev_label}</span></span>`;
		};
		const card = (label, value, hint = "", cls = "", title = "") => `
			<div class="mp-stat ${cls}" title="${esc(title)}">
				<div class="mp-stat__label">${label}</div>
				<div class="mp-stat__value">${value}</div>
				${hint ? `<div class="mp-stat__hint">${hint}</div>` : ""}
			</div>`;
		const n = (x) => format_number(x || 0, null, 0);
		const cnt = d.stock?.counts || {};

		this.$body.html(`
			<div class="mp-rep__period">
				<span class="mp-rep__title">${esc(this.period_label())}</span>
				${d.shop && d.is_admin ? `<span class="mp-tag">${esc(d.shop)}</span>` : ""}
			</div>

			<div class="mp-sec">${__("Pul")}</div>
			<div class="mp-stats">
				${card(__("Kassaga tushgan pul"), this.fmt(s.revenue), `${s.paid} ${__("ta buyurtma to‘landi")} ${change(s.change.revenue)}`, "mp-stat--main mp-stat--good", __("Payme, Click yoki naqd — to‘lovi qabul qilingan buyurtmalar"))}
				${card(__("To‘lanishi kutilmoqda"), this.fmt(s.pending_amount), `${s.pending} ${__("ta buyurtma hali to‘lanmagan")}`, s.pending ? "mp-stat--warn" : "")}
				${card(__("Jami buyurtmalar"), this.fmt(s.sales), `${s.orders} ${__("ta buyurtma")} ${change(s.change.sales)}`, "", __("To‘langan + to‘lanishi kutilayotgan"))}
				${card(__("Mijozga berilgan"), `${s.delivered} <small>/ ${s.orders}</small>`, s.orders - s.delivered ? `${s.orders - s.delivered} ${__("ta buyurtma hali berilmagan")}` : __("hammasi berilgan"))}
				${card(__("Bekor qilingan"), s.cancelled, s.cancelled ? this.fmt(s.cancelled_amount) : __("buyurtma"))}
			</div>
			<div class="mp-explain text-muted">${__("Kassaga tushgan pul")} ${this.fmt(s.revenue)} + ${__("to‘lanishi kutilmoqda")} ${this.fmt(s.pending_amount)} = ${__("jami buyurtmalar")} ${this.fmt(s.sales)}</div>

			${d.by_shop ? this.by_shop_html(d.by_shop) : ""}

			${d.stock ? `<div class="mp-sec">${__("Ombor (dona)")}</div>
			<div class="mp-stats">
				${card(__("Omborda hozir"), n(st.closing), __("{0} holatiga", [this.date_label(d.to_date)]), "mp-stat--main")}
				${card(__("Keldi (kirim)"), `+${n(st.received)}`, __("{0} ta kirim", [cnt.kirim]), "mp-stat--good")}
				${card(__("Sotildi"), n(st.sold), __("mijozga berildi · {0} ta buyurtma", [cnt.sotuv]))}
				${st.adjusted ? card(__("Kamomad"), n(st.adjusted), __("sotilmasdan kamaygan — tekshiring!"), "mp-stat--bad", __("Inventarizatsiyada administrator kamaytirgan: yo‘qolgan, buzilgan yoki noto‘g‘ri yozilgan tovar")) : ""}
			</div>
			<div class="mp-explain text-muted">${__("Davr boshida")} ${n(st.opening)} + ${__("keldi")} ${n(st.received)} − ${__("sotildi")} ${n(st.sold)}${st.adjusted ? ` − ${__("kamomad")} ${n(st.adjusted)}` : ""} = ${__("omborda")} <b>${n(st.closing)}</b> ${__("dona")}</div>` : ""}

			<div class="mp-box">
				<div class="mp-box__head">
					<div class="mp-box__title">${d.series.unit === "day" ? __("Kunlar bo‘yicha") : __("Oylar bo‘yicha")}</div>
					<div class="mp-seg" data-group="metric">
						<button data-val="revenue" class="${this.state.metric === "revenue" ? "is-active" : ""}">${__("Tushgan pul")}</button>
						<button data-val="sales" class="${this.state.metric === "sales" ? "is-active" : ""}">${__("Buyurtmalar summasi")}</button>
						<button data-val="orders" class="${this.state.metric === "orders" ? "is-active" : ""}">${__("Buyurtmalar soni")}</button>
					</div>
				</div>
				<div class="mp-chart"></div>
				<div class="mp-box__foot text-muted">${d.series.unit === "day" ? __("Ustunni bossangiz, o‘sha kun hisoboti ochiladi") : __("Ustunni bossangiz, o‘sha oy hisoboti ochiladi")}</div>
			</div>

			<div class="mp-box">
				<div class="mp-box__head">
					<div class="mp-box__title">${__("Eng ko‘p sotilganlar")}</div>
					<div class="mp-seg" data-group="top">
						<button data-val="by_qty" class="${this.state.top === "by_qty" ? "is-active" : ""}">${__("Soni bo‘yicha")}</button>
						<button data-val="by_amount" class="${this.state.top === "by_amount" ? "is-active" : ""}">${__("Summa bo‘yicha")}</button>
					</div>
				</div>
				<div class="mp-top"></div>
				<div class="mp-box__foot text-muted">${__("«Sotildi» — faqat puli to‘langan buyurtmalar (hammasi qo‘shilsa «Kassaga tushgan pul»ga teng). «To‘lov kutilmoqda» — buyurtma qilingan, lekin puli hali tushmagan: naqd buyurtmada do‘kon «Naqd pul olindi» bosganda «Sotildi»ga o‘tadi.")}</div>
			</div>

			${d.stock ? `<div class="mp-box">
				<div class="mp-box__head">
					<div class="mp-box__title">${__("Ombor: har bir tovar")}</div>
					<input class="form-control input-xs mp-mv__search" type="search" placeholder="${__("Tovar qidirish…")}">
				</div>
				<div class="mp-mv"></div>
				<div class="mp-box__foot text-muted">${__("Avval bor edi + Keldi − Sotildi − Kamomad = Qoldi. Tovar faqat sotuv bilan kamayadi; «Kamomad» — sotilmasdan yo‘qolgan tovar.")}</div>
			</div>

			<div class="mp-box">
				<div class="mp-box__head"><div class="mp-box__title">${__("Harakatlar tarixi")}</div></div>
				<div class="mp-rc"></div>
			</div>` : ""}

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
		if (d.stock) {
			this.render_movement();
			this.render_journal();
		}
		this.render_bars(this.$body.find(".mp-cats"), d.categories.map((c) => ({ label: c.item_group, amount: c.amount, sub: `${n(c.qty)} ${__("dona")}` })));
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
		const { series } = this.data;
		const $el = this.$body.find(".mp-chart");
		const metric = this.state.metric;
		const is_money = metric !== "orders";
		const values = series.points.map((p) => p[metric]);
		if (!values.some(Boolean)) {
			$el.html(`<div class="mp-empty text-muted">${__("Bu davrda sotuv yo‘q")}</div>`);
			return;
		}
		const labels = series.points.map((p) => {
			const [y, m, d] = p.from.split("-").map(Number);
			return series.unit === "day" ? `${d}.${String(m).padStart(2, "0")}` : `${__(MP_MONTHS[m - 1]).slice(0, 3)} ${String(y).slice(2)}`;
		});
		const names = { sales: __("Buyurtmalar summasi"), revenue: __("Tushgan pul"), orders: __("Buyurtmalar soni") };
		this.chart = new frappe.Chart($el.get(0), {
			type: "bar",
			height: 220,
			data: { labels, datasets: [{ name: names[metric], values }] },
			colors: [metric === "revenue" ? "green" : metric === "sales" ? "purple" : "blue"],
			barOptions: { spaceRatio: 0.4 },
			axisOptions: { xIsSeries: true, shortenYAxisNumbers: 1 },
			tooltipOptions: { formatTooltipY: (v) => (is_money ? this.fmt(v) : `${v} ${__("ta")}`) },
			isNavigable: false,
		});
		// Ustun bosilganda o'sha kun/oyni tanlaymiz
		$el.off("click.mp").on("click.mp", "rect.bar", (e) => {
			const i = Number($(e.currentTarget).closest("[data-point-index]").attr("data-point-index"));
			const p = series.points[i];
			if (p) this.set_range(p.from, p.to, "custom");
		});
	}

	render_top() {
		const list = this.data.top_products[this.state.top] || [];
		const $el = this.$body.find(".mp-top");
		if (!list.length) {
			$el.html(`<div class="mp-empty text-muted">${__("Bu davrda buyurtma yo‘q")}</div>`);
			return;
		}
		const max = Math.max(...list.map((p) => (this.state.top === "by_qty" ? p.qty : p.amount))) || 1;
		$el.html(`
			<div class="mp-table">
				<div class="mp-row mp-row--head text-muted">
					<span>#</span><span>${__("Tovar")}</span><span class="mp-num">${__("Sotildi")}</span><span class="mp-num">${__("Tushgan pul")}</span><span class="mp-num">${__("To‘lov kutilmoqda")}</span>
				</div>
				${list
					.map((p, i) => {
						const share = ((this.state.top === "by_qty" ? p.qty : p.amount) / max) * 100;
						return `
						<a class="mp-row" href="/desk/item/${encodeURIComponent(p.item_code)}">
							<span class="mp-rank">${i + 1}</span>
							${this.prod_cell(p, `<span class="mp-meter"><i style="width:${share.toFixed(1)}%"></i></span>`)}
							<span class="mp-num">${p.qty ? `<b>${format_number(p.qty, null, 0)}</b> <span class="text-muted">${__("dona")}</span>` : "—"}</span>
							<span class="mp-num mp-pos">${p.amount ? this.fmt(p.amount) : "—"}</span>
							<span class="mp-num text-muted">${p.wait_qty ? `${format_number(p.wait_qty, null, 0)} ${__("dona")} · ${this.fmt(p.wait_amount)}` : "—"}</span>
						</a>`;
					})
					.join("")}
			</div>`);
	}

	prod_cell(p, extra = "") {
		const esc = frappe.utils.escape_html;
		const initials = esc((p.item_name || "?").trim().slice(0, 2).toUpperCase());
		return `
			<span class="mp-prod">
				<span class="mp-thumb">${p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy">` : initials}</span>
				<span class="mp-prod__txt">
					<span class="mp-prod__name">${esc(p.item_name)}</span>
					<span class="mp-prod__sub text-muted">${esc(p.item_group || "")}${p.variants > 1 ? ` · ${p.variants} ${__("variant")}` : ""}</span>
					${extra}
				</span>
			</span>`;
	}

	render_movement(q = "") {
		const $el = this.$body.find(".mp-mv");
		q = q.trim().toLowerCase();
		const list = this.data.stock.products.filter((p) => !q || `${p.item_name} ${p.item_group || ""}`.toLowerCase().includes(q));
		if (!list.length) {
			$el.html(`<div class="mp-empty text-muted">${__("Ombor harakati yo‘q")}</div>`);
			return;
		}
		const n = (x) => format_number(x || 0, null, 0);
		$el.html(`
			<div class="mp-mv__table">
				<div class="mp-mv__row mp-row--head text-muted">
					<span>${__("Tovar")}</span><span class="mp-num">${__("Avval bor edi")}</span><span class="mp-num">${__("Keldi")}</span>
					<span class="mp-num">${__("Sotildi")}</span><span class="mp-num">${__("Kamomad")}</span><span class="mp-num">${__("Qoldi")}</span>
				</div>
				${list.map((p) => `
					<a class="mp-mv__row ${p.adjusted > 0 ? "is-bad" : ""}" href="/desk/item/${encodeURIComponent(p.item_code)}">
						${this.prod_cell(p)}
						<span class="mp-num" data-label="${__("Avval")}">${n(p.opening)}</span>
						<span class="mp-num mp-pos" data-label="${__("Keldi")}">${p.received ? `+${n(p.received)}` : "—"}</span>
						<span class="mp-num" data-label="${__("Sotildi")}">${p.sold ? n(p.sold) : "—"}</span>
						<span class="mp-num mp-neg" data-label="${__("Kamomad")}">${p.adjusted ? n(p.adjusted) : "—"}</span>
						<span class="mp-num" data-label="${__("Qoldi")}"><b>${n(p.closing)}</b></span>
					</a>`).join("")}
			</div>`);
	}

	render_journal() {
		this.$body.find(".mp-rc").html(mp.journal(this.data.stock.journal, { show_item: true, empty: __("Bu davrda kirim ham, sotuv ham bo‘lmagan") }));
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
		this.$body.find(".mp-mv__search").on("input", frappe.utils.debounce((e) => this.render_movement(e.target.value), 200));
		// "Do'konlar bo'yicha": qatorni bossa — hisobot o'sha do'kon bo'yicha
		this.$body.find("[data-shop-row]").on("click", (e) => {
			this.shop_field?.set_value(e.currentTarget.dataset.shopRow);
		});
	}

	// Admin, "Barcha do'konlar": har bir do'konda nechta buyurtma, qancha tushdi (Payme / Click / Naqd)
	by_shop_html(rows) {
		const esc = frappe.utils.escape_html;
		const sum = (x) => (x ? this.fmt(x) : "—");
		return `
			<div class="mp-box">
				<div class="mp-box__head"><div class="mp-box__title">${__("Do‘konlar bo‘yicha")}</div></div>
				<div class="mp-bs">
					<div class="mp-bs__row mp-row--head text-muted">
						<span>${__("Do‘kon")}</span><span class="mp-num">${__("Buyurtmalar")}</span><span class="mp-num">${__("Kassaga tushgan")}</span>
						<span class="mp-num">Payme</span><span class="mp-num">Click</span><span class="mp-num">${__("Naqd")}</span>
						<span class="mp-num">${__("Kutilmoqda")}</span><span class="mp-num">${__("Bekor")}</span>
					</div>
					${rows.map((r) => `
						<div class="mp-bs__row ${r.orders ? "" : "is-empty"}" data-shop-row="${esc(r.shop)}" title="${__("Shu do‘kon hisobotini ochish")}">
							<span class="mp-bs__name">${esc(r.shop_name || r.shop)}</span>
							<span class="mp-num" data-label="${__("Buyurtmalar")}"><b>${r.orders}</b>${r.paid ? ` <small class="text-muted">(${r.paid} ${__("to‘landi")})</small>` : ""}</span>
							<span class="mp-num mp-pos" data-label="${__("Kassaga tushgan")}"><b>${sum(r.revenue)}</b></span>
							<span class="mp-num" data-label="Payme">${sum(r.payme)}</span>
							<span class="mp-num" data-label="Click">${sum(r.click)}</span>
							<span class="mp-num" data-label="${__("Naqd")}">${sum(r.naqd)}</span>
							<span class="mp-num" data-label="${__("Kutilmoqda")}">${sum(r.pending_amount)}</span>
							<span class="mp-num" data-label="${__("Bekor")}">${r.cancelled || "—"}</span>
						</div>`).join("")}
				</div>
				<div class="mp-box__foot text-muted">${__("«Kassaga tushgan» — puli to‘langan buyurtmalar. Qatorni bossangiz, shu do‘kon hisoboti ochiladi.")}</div>
			</div>`;
	}

	// UZS uchun Frappe noto'g'ri belgi ko'rsatadi — o'zimiz formatlaymiz
	fmt(n) {
		return `${format_number(n || 0, null, 0)} so‘m`;
	}

	inject_style() {
		if (document.getElementById("mp-rep-style")) return;
		$(`<style id="mp-rep-style">
			.mp-rep { padding: 4px var(--padding-md, 15px) 40px; }
			.page-form .mp-rep-filter { flex: 0 0 150px; max-width: 150px; }
			.page-form .mp-rep-filter--wide { flex-basis: 200px; max-width: 200px; }
			.mp-sec { margin: 4px 0 8px; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); }
			.mp-stat--good .mp-stat__value { color: var(--green-600, #16a34a); }
			.mp-stat--warn { background: var(--bg-orange); }
			.mp-stat--bad { background: var(--bg-red); border-color: var(--red-300, #fca5a5); }
			.mp-stat--bad .mp-stat__value { color: var(--red-600, #dc2626); }
			.mp-pos { color: var(--green-600, #16a34a); }
			.mp-neg { color: var(--red-600, #dc2626); }
			.mp-mv__search { max-width: 220px; }
			.mp-mv__table { max-height: 520px; overflow: auto; }
			.mp-mv__row { display: grid; grid-template-columns: minmax(0, 1fr) repeat(5, 84px); gap: 10px; align-items: center; padding: 8px 4px;
				border-top: 1px solid var(--border-color); color: var(--text-color); }
			.mp-mv__row.mp-row--head { position: sticky; top: 0; background: var(--card-bg); z-index: 1; border-top: 0; }
			a.mp-mv__row:hover { background: var(--subtle-fg); text-decoration: none; color: var(--text-color); }
			.mp-mv__row.is-bad { background: var(--bg-red); }
			.mp-bs { overflow-x: auto; }
			.mp-bs__row { display: grid; grid-template-columns: minmax(140px, 1fr) 96px repeat(6, 112px); gap: 10px; align-items: center;
				padding: 8px 4px; border-top: 1px solid var(--border-color); min-width: 860px; cursor: pointer; }
			.mp-bs__row.mp-row--head { border-top: 0; cursor: default; font-size: var(--text-sm); }
			.mp-bs__row:not(.mp-row--head):hover { background: var(--subtle-fg); }
			.mp-bs__row.is-empty { color: var(--text-muted); }
			.mp-bs__name { font-weight: 600; color: var(--heading-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
			.mp-explain { margin: -8px 0 16px; font-size: var(--text-sm); }
			.mp-stat__value small { font-size: var(--text-md); color: var(--text-muted); font-weight: 400; }
			@media (max-width: 640px) {
				.page-form .mp-rep-filter, .page-form .mp-rep-filter--wide { flex: 1 1 45%; max-width: none; }
				.mp-mv__row { grid-template-columns: repeat(5, 1fr); }
				.mp-mv__row > .mp-prod { grid-column: 1 / -1; }
				.mp-mv__row.mp-row--head > :first-child { grid-column: 1 / -1; }
				.mp-mv__row .mp-num { font-size: var(--text-xs); }
			}
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
			.mp-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) 80px 130px 180px; gap: 10px; align-items: center; padding: 8px 4px; border-top: 1px solid var(--border-color); color: var(--text-color); }
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
				.mp-row > :nth-child(4), .mp-row > :nth-child(5) { grid-column: 2 / -1; text-align: left; font-size: var(--text-sm); color: var(--text-muted); }
				.mp-row > :nth-child(5)::before { content: "To‘langan: "; }
				.mp-row--head > :nth-child(4), .mp-row--head > :nth-child(5) { display: none; }
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
