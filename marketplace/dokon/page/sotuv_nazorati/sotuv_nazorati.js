// Sotuv nazorati: do'kon egasi uchun lidlar va sotuv menejerlari ishining umumiy manzarasi (sotuv/nazorat.py).
// Tepada — hozir kutayotganlar (davrga bog'liq emas), keyin tanlangan davrda kelgan lidlar: voronka, holatlar,
// grafik, kimlar sotib oldi, menejerlar, tovar va manba bo'yicha, AI xulosalari.
// Butun skript IIFE ichida: Desk sahifa skriptlari bitta global maydonda ishlaydi, nomlar boshqa sahifalar bilan to'qnashmasin.
(() => {
	const WEEKDAYS = ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"];
	const WEEKDAYS_SHORT = ["Ya", "Du", "Se", "Ch", "Pa", "Ju", "Sh"];
	const MONTHS = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentabr", "Oktabr", "Noyabr", "Dekabr"];
	const STATE_COLOR = {
		Yangi: "purple", "Javob bermadi": "orange", Keyinroq: "blue", Oladi: "green", Olmaydi: "red", "Buyurtma berdi": "teal",
	};
	const PAY_COLOR = { "To'langan": "green", "To'lov kutilmoqda": "orange", Bekor: "red", "Buyurtma yo'q": "gray" };

	const PRESETS = (() => {
		const d = (x) => frappe.datetime.obj_to_str(x);
		const now = () => new Date();
		const shift = (n) => { const x = now(); x.setDate(x.getDate() + n); return x; };
		return [
			["today", "Bugun", () => [d(now()), d(now())]],
			["yesterday", "Kecha", () => [d(shift(-1)), d(shift(-1))]],
			["7", "Oxirgi 7 kun", () => [d(shift(-6)), d(now())]],
			["30", "Oxirgi 30 kun", () => [d(shift(-29)), d(now())]],
			["month", "Shu oy", () => { const t = now(); return [d(new Date(t.getFullYear(), t.getMonth(), 1)), d(t)]; }],
			["prev_month", "O'tgan oy", () => { const t = now(); return [d(new Date(t.getFullYear(), t.getMonth() - 1, 1)), d(new Date(t.getFullYear(), t.getMonth(), 0))]; }],
			["year", "Shu yil", () => { const t = now(); return [d(new Date(t.getFullYear(), 0, 1)), d(t)]; }],
		];
	})();

	const esc = (s) => frappe.utils.escape_html(s == null ? "" : String(s));
	// Shop Member «Nazoratchi» (seller_desk._shop_boot) — sahifani faqat ko'radi
	const mp_sn_supervisor = () => !!frappe.boot.marketplace_shop?.supervisor;
	const num = (x) => format_number(x || 0, null, 0);
	const money = (x) => `${num(x)} so‘m`;
	const pct = (a, b) => (b ? Math.round((a * 100) / b) : 0);
	const ago = (minutes) => {
		if (minutes == null) return "";
		if (minutes < 60) return __("{0} daq", [Math.max(1, Math.round(minutes))]);
		if (minutes < 60 * 24) return __("{0} soat", [Math.round(minutes / 60)]);
		return __("{0} kun", [Math.round(minutes / 1440)]);
	};
	const talk = (sec) => {
		sec = cint(sec);
		if (!sec) return "—";
		const h = Math.floor(sec / 3600), m = Math.round((sec % 3600) / 60);
		if (h) return __("{0} soat {1} daq", [h, m]);
		return m ? __("{0} daq", [m]) : __("{0} s", [sec]);
	};
	const date_label = (s) => {
		const [y, m, d] = s.split("-").map(Number);
		return `${d}-${__(MONTHS[m - 1]).toLowerCase()} ${y}`;
	};
	const when = (s) => (s ? moment(s).format("DD.MM.YYYY HH:mm") : "");
	const pill = (text, color) => `<span class="mp-sn-pill mp-sn-pill--${color || "gray"}">${esc(__(text))}</span>`;

	frappe.pages["sotuv-nazorati"].on_page_load = function (wrapper) {
		const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Sotuv nazorati"), single_column: true });
		wrapper.nazorat = new SotuvNazorati(page);
	};
	frappe.pages["sotuv-nazorati"].on_page_show = function (wrapper) {
		wrapper.nazorat?.load();
	};

	class SotuvNazorati {
		constructor(page) {
			this.page = page;
			const [from, to] = PRESETS.find((p) => p[0] === "month")[2]();
			this.state = { from, to, preset: "month", shop: "", wait: "new" };
			this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
			this.make_filters();
			this.$body = $(`<div class="mp-sn"></div>`).appendTo(page.main);
			inject_style();
		}

		make_filters() {
			this.preset_field = this.page.add_field({
				fieldname: "preset", label: __("Davr"), fieldtype: "Select", default: this.state.preset,
				options: [...PRESETS.map(([value, label]) => ({ value, label: __(label) })), { value: "custom", label: __("Boshqa sanalar") }],
				change: () => {
					const found = PRESETS.find((p) => p[0] === this.preset_field.get_value());
					if (found) this.set_range(...found[2](), found[0]);
				},
			});
			this.from_field = this.page.add_field({ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: this.state.from, change: () => this.on_date() });
			this.to_field = this.page.add_field({ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: this.state.to, change: () => this.on_date() });
			for (const f of [this.preset_field, this.from_field, this.to_field]) f.$wrapper.addClass("mp-sn-filter");
		}

		on_date() {
			if (this._silent) return;
			const from = this.from_field.get_value(), to = this.to_field.get_value();
			if (!from || !to || (from === this.state.from && to === this.state.to)) return;
			this.set_range(from, to, "custom");
		}

		set_range(from, to, preset) {
			Object.assign(this.state, { from, to, preset });
			this._silent = true;
			this.from_field.set_input(from);
			this.to_field.set_input(to);
			this.preset_field.set_input(preset);
			this._silent = false;
			this.load();
		}

		make_shop_filter(shops) {
			if (this.shop_field || !shops.length) return;
			this.shop_field = this.page.add_field({
				fieldname: "shop", label: __("Do'kon"), fieldtype: "Select", default: "",
				options: [{ value: "", label: __("Barcha do'konlar") }, ...shops.map((s) => ({ value: s.name, label: s.shop_name || s.name }))],
				change: () => {
					const v = this.shop_field.get_value() || "";
					if (v !== this.state.shop) { this.state.shop = v; this.load(); }
				},
			});
			this.shop_field.$wrapper.addClass("mp-sn-filter mp-sn-filter--wide");
		}

		async load() {
			if (!this.data) this.$body.html(`<div class="mp-sn-empty">${__("Yuklanmoqda…")}</div>`);
			try {
				this.data = await frappe.xcall("marketplace.sotuv.nazorat.get_dashboard", {
					from_date: this.state.from, to_date: this.state.to, shop: this.state.shop || null,
				});
			} catch (e) {
				this.$body.html(`<div class="mp-sn-empty">${__("Bu sahifa do‘kon egasi uchun.")}</div>`);
				return;
			}
			if (this.data.is_admin && !frappe.boot.marketplace_shop) this.make_shop_filter(this.data.shops);
			this.render();
		}

		render() {
			const d = this.data, s = d.summary;
			this.$body.html(`
				<div class="mp-sn-head">
					<span class="mp-sn-head__title">${esc(d.from_date === d.to_date ? date_label(d.from_date) : `${date_label(d.from_date)} — ${date_label(d.to_date)}`)}</span>
					<span class="mp-sn-tag">${esc(d.shop_name || (d.shop ? d.shop : __("Barcha do‘konlar")))}</span>
				</div>
				${this.now_html(d.waiting)}
				<div class="mp-sn-kpis">
					${this.kpi(__("Lid tushdi"), num(s.leads), this.change(s.change.leads), "", __("Shu davrda kelgan murojaatlar: reklama, Google Sheets, menejer qo‘shganlar"))}
					${this.kpi(__("Sotib oldi"), `${num(s.ordered)} <small>${s.conversion}%</small>`,
						`${__("konversiya")} ${s.conversion_change == null ? "" : this.delta_pp(s.conversion_change)}`, "is-good", __("Shu davrda kelgan lidlardan buyurtma berganlari"))}
					${this.kpi(__("Lidlardan buyurtma"), money(s.revenue), `${__("to‘langan")}: ${money(s.paid_amount)}`, "is-money", __("Bekor qilinmagan buyurtmalar summasi"))}
					${this.kpi(__("Birinchi aloqagacha"), s.response_median == null ? "—" : ago(s.response_median),
						s.response_hour_pct == null ? __("hali ma’lumot yo‘q") : __("{0}% lidga 1 soat ichida", [s.response_hour_pct]),
						s.response_median != null && s.response_median > 60 ? "is-warn" : "", __("Lid kelgandan menejer bog‘langangacha (mediana)"))}
					${this.kpi(__("Qo‘ng‘iroqlar"), num(d.calls.total),
						`${__("gaplashildi")}: ${talk(d.managers.reduce((a, m) => a + m.talk, 0))}`)}
				</div>
				<div class="mp-sn-two">
					<div class="mp-sn-box">${this.box_head(__("Voronka"), __("shu davrda kelgan lidlar"))}${this.funnel_html(s)}</div>
					<div class="mp-sn-box">${this.box_head(__("Lidlar holati"), __("menejer yozgan natija bo‘yicha"))}${this.states_html(d.states, s.leads)}</div>
				</div>
				<div class="mp-sn-box">
					${this.box_head(d.series.unit === "day" ? __("Har kuni nechta lid tushdi") : __("Har oy nechta lid tushdi"), __("yashil qismi — shu lidlardan sotib olganlar"))}
					<div class="mp-sn-chart"></div>
				</div>
				<div class="mp-sn-box" data-wait-box>
					<div class="mp-sn-box__head">
						<div class="mp-sn-box__title">${__("Kutayotganlar")}</div>
						<div class="mp-sn-seg">
							<button data-wait="new" class="${this.state.wait === "new" ? "is-active" : ""}">${__("Gaplashilmagan")} <span>${d.waiting.new_count}</span></button>
							<button data-wait="no_result" class="${this.state.wait === "no_result" ? "is-active" : ""}">${__("Natija yozilmagan")} <span>${d.waiting.no_result_count}</span></button>
							<button data-wait="callbacks" class="${this.state.wait === "callbacks" ? "is-active" : ""}">${__("Qayta qo‘ng‘iroq")} <span>${d.waiting.callback_count}</span></button>
						</div>
					</div>
					<div class="mp-sn-wait"></div>
				</div>
				<div class="mp-sn-box">
					${this.box_head(__("Kimlar sotib oldi"), d.bought.count > d.bought.rows.length ? __("oxirgi {0} tasi, jami {1}", [d.bought.rows.length, d.bought.count]) : __("jami {0}", [d.bought.count]))}
					${this.bought_html(d.bought.rows)}
				</div>
				<div class="mp-sn-box">${this.box_head(__("Sotuv menejerlari"), __("shu davrdagi qo‘ng‘iroq va natijalar"))}${this.managers_html(d.managers)}</div>
				<div class="mp-sn-two">
					<div class="mp-sn-box">${this.box_head(__("Tovarlar bo‘yicha"), __("qaysi tovarga lid ko‘p va qanchasi sotildi"))}${this.items_html(d.items)}</div>
					<div class="mp-sn-box">${this.box_head(__("Manba va reklama"), __("lidlar qayerdan kelgan"))}${this.sources_html(d.sources)}</div>
				</div>
				<div class="mp-sn-box">${this.box_head(__("Oxirgi qo‘ng‘iroqlar"), __("tinglash va AI xulosasi"))}${this.calls_html(d.calls)}</div>
			`);
			this.render_wait();
			this.render_chart();
			this.bind();
		}

		// ---------- Kichik qismlar ----------
		kpi(label, value, hint = "", cls = "", title = "") {
			return `<div class="mp-sn-kpi ${cls}" title="${esc(title)}">
				<div class="mp-sn-kpi__label">${label}</div>
				<div class="mp-sn-kpi__value">${value}</div>
				${hint ? `<div class="mp-sn-kpi__hint">${hint}</div>` : ""}
			</div>`;
		}

		box_head(title, sub = "") {
			return `<div class="mp-sn-box__head"><div class="mp-sn-box__title">${title}${sub ? ` <span>${sub}</span>` : ""}</div></div>`;
		}

		change(p) {
			if (p === null || p === undefined) return "";
			const cls = p > 0 ? "up" : p < 0 ? "down" : "flat";
			return `<span class="mp-sn-chg mp-sn-chg--${cls}">${p > 0 ? "▲" : p < 0 ? "▼" : "•"} ${Math.abs(p)}%</span> ${__("oldingi {0} kunga nisbatan", [this.data.days])}`;
		}

		delta_pp(p) {
			const cls = p > 0 ? "up" : p < 0 ? "down" : "flat";
			return `<span class="mp-sn-chg mp-sn-chg--${cls}">${p > 0 ? "▲" : p < 0 ? "▼" : "•"} ${Math.abs(p)} ${__("punkt")}</span>`;
		}

		// Hozir: davrga bog'liq emas — bugun kimga qo'ng'iroq qilish kerak
		now_html(w) {
			const tile = (attrs, cls, value, label, sub) => `
				<button class="mp-sn-now__tile ${cls}" ${attrs}>
					<span class="mp-sn-now__value">${value}</span>
					<span class="mp-sn-now__label">${label}</span>
					<span class="mp-sn-now__sub">${sub}</span>
				</button>`;
			return `<div class="mp-sn-now">
				<div class="mp-sn-now__title">${__("Hozir")}</div>
				${tile('data-jump="new"', w.new_count ? (w.new_oldest_minutes > 60 ? "is-bad" : "is-warn") : "is-ok", num(w.new_count),
					__("lid bilan hali gaplashilmagan"), w.new_count ? __("eng eskisi {0} kutmoqda", [ago(w.new_oldest_minutes)]) : __("hammasiga qo‘ng‘iroq qilingan"))}
				${tile('data-jump="no_result"', w.no_result_count ? "is-warn" : "is-ok", num(w.no_result_count),
					__("gaplashilgan, natija yozilmagan"), w.no_result_count ? __("menejer natijani belgilashi kerak") : __("hamma natija yozilgan"))}
				${tile('data-jump="callbacks"', w.callback_overdue ? "is-bad" : w.callback_count ? "is-warn" : "is-ok", num(w.callback_count),
					__("qayta qo‘ng‘iroq vaqti keldi"), w.callback_overdue ? __("{0} tasi kechikkan", [w.callback_overdue]) : __("kechikkani yo‘q"))}
				${tile('data-panel="1"', w.site_orders ? "is-warn" : "is-ok", num(w.site_orders),
					__("saytdan buyurtma tasdiq kutmoqda"), w.site_orders ? (mp_sn_supervisor() ? __("Buyurtmalarni ko‘rish") : __("Sotuv panelida ochish")) : __("kutayotgan buyurtma yo‘q"))}
			</div>`;
		}

		funnel_html(s) {
			if (!s.leads) return `<div class="mp-sn-empty">${__("Bu davrda lid tushmagan")}</div>`;
			const steps = [
				[__("Lid tushdi"), s.leads, __("barcha manbalardan")],
				[__("Bog‘lanildi"), s.contacted, __("qo‘ng‘iroq yoki natija bor")],
				[__("Rozi bo‘ldi"), s.agreed, __("«Oladi» deb javob bergan")],
				[__("Buyurtma berdi"), s.ordered, __("buyurtma yaratilgan")],
				[__("Puli tushdi"), s.paid, __("Payme, Click yoki naqd")],
			];
			return `<div class="mp-sn-funnel">${steps.map(([label, n, hint], i) => {
				const prev = i ? steps[i - 1][1] : null;
				return `${i ? `<div class="mp-sn-funnel__drop">↓ ${pct(n, prev)}% ${__("o‘tdi")}</div>` : ""}
					<div class="mp-sn-funnel__step">
						<div class="mp-sn-funnel__label"><b>${label}</b><span>${hint}</span></div>
						<div class="mp-sn-funnel__bar"><i style="width:${Math.max(pct(n, s.leads), n ? 2 : 0)}%; background: var(--sn-step-${i})"></i></div>
						<div class="mp-sn-funnel__num"><b>${num(n)}</b><span>${pct(n, s.leads)}%</span></div>
					</div>`;
			}).join("")}</div>`;
		}

		states_html(states, total) {
			if (!total) return `<div class="mp-sn-empty">${__("Bu davrda lid tushmagan")}</div>`;
			return `
				<div class="mp-sn-stack">${states.filter((x) => x.count).map((x) =>
					`<i style="flex:${x.count}; background: var(--${STATE_COLOR[x.state]}-500)" title="${esc(__(x.state))}: ${x.count}"></i>`).join("")}</div>
				<div class="mp-sn-legend">${states.map((x) => `
					<div class="mp-sn-legend__row ${x.count ? "" : "is-zero"}">
						<span><i style="background: var(--${STATE_COLOR[x.state]}-500)"></i>${esc(__(x.state))}${x.state === "Yangi" ? ` <small class="mp-sn-muted">${__("natija yozilmagan")}</small>` : ""}</span>
						<b>${num(x.count)}</b><span class="mp-sn-muted">${pct(x.count, total)}%</span>
					</div>`).join("")}
				</div>`;
		}

		// Grafik: har ustun — bir kun (yoki oy). Balandligi — nechta lid tushdi, yashil qismi — ulardan nechtasi sotib oldi.
		// Ustun ustida soni, ostida kun va hafta kuni; ustunni bossangiz — o'sha kun ko'rsatiladi
		render_chart() {
			const { series } = this.data;
			const $el = this.$body.find(".mp-sn-chart");
			const pts = series.points;
			const total = pts.reduce((a, p) => a + p.leads, 0);
			if (!total) {
				$el.html(`<div class="mp-sn-empty">${__("Bu davrda lid tushmagan")}</div>`);
				return;
			}
			const daily = series.unit === "day";
			const max = Math.max(...pts.map((p) => p.leads));
			const step = Math.max(1, Math.ceil(max / 4));
			const top = step * Math.ceil(max / step);
			const ticks = [];
			for (let v = 0; v <= top; v += step) ticks.push(v);
			const best = pts.reduce((a, p) => (p.leads > a.leads ? p : a), pts[0]);
			const ordered = pts.reduce((a, p) => a + p.ordered, 0);
			const width = $el.width() || 800;
			const every = Math.max(1, Math.ceil((pts.length * 30) / width));
			const parse = (str) => { const [y, m, d] = str.split("-").map(Number); return new Date(y, m - 1, d); };
			const label = (p) => {
				const dt = parse(p.from);
				return daily ? `${dt.getDate()}-${__(MONTHS[dt.getMonth()]).toLowerCase()}, ${__(WEEKDAYS[dt.getDay()])}` : `${__(MONTHS[dt.getMonth()])} ${dt.getFullYear()}`;
			};
			const cols = pts.map((p, i) => {
				const dt = parse(p.from);
				const h = (p.leads / top) * 100, g = p.leads ? (p.ordered / p.leads) * 100 : 0;
				const month_start = daily && (i === 0 || dt.getDate() === 1);
				const show = i % every === 0 || i === pts.length - 1 || month_start;
				const weekend = daily && (dt.getDay() === 0 || dt.getDay() === 6);
				const tip = `${label(p)}: ${p.leads} ${__("ta lid")}${p.leads ? `, ${p.ordered} ${__("tasi sotib oldi")}` : ""}`;
				return `<button class="mp-sn-cc__col ${p.leads ? "" : "is-zero"} ${weekend ? "is-weekend" : ""}" data-from="${p.from}" data-to="${p.to}" title="${esc(tip)}">
					<span class="mp-sn-cc__area">
						${p.leads ? `<span class="mp-sn-cc__val">${p.leads}${p.ordered ? `<em>${p.ordered}✓</em>` : ""}</span>` : ""}
						<span class="mp-sn-cc__bar" style="height:${h}%"><span style="height:${g}%"></span></span>
					</span>
					<span class="mp-sn-cc__x">${show ? (daily ? `<b>${dt.getDate()}</b><small>${__(WEEKDAYS_SHORT[dt.getDay()])}</small>` : `<b>${__(MONTHS[dt.getMonth()]).slice(0, 3)}</b><small>${String(dt.getFullYear()).slice(2)}</small>`) : ""}</span>
					${month_start ? `<span class="mp-sn-cc__month">${__(MONTHS[dt.getMonth()])}</span>` : ""}
				</button>`;
			}).join("");
			$el.html(`
				<div class="mp-sn-cc__sum">
					<span>${__("Jami")}: <b>${num(total)}</b> ${__("ta lid")}</span>
					<span>${__("sotib oldi")}: <b>${num(ordered)}</b></span>
					<span>${__("eng ko‘p")}: <b>${esc(label(best))}</b> (${best.leads} ${__("ta")})</span>
					<span>${daily ? __("kuniga o‘rtacha") : __("oyiga o‘rtacha")}: <b>${(total / pts.length).toFixed(1)}</b></span>
				</div>
				<div class="mp-sn-cc">
					<div class="mp-sn-cc__grid">${ticks.map((v) => `<span style="bottom:${(v / top) * 100}%"><i>${v}</i></span>`).join("")}</div>
					<div class="mp-sn-cc__cols">${cols}</div>
				</div>
				<div class="mp-sn-cc__legend">
					<span><i class="is-lead"></i>${__("Lid tushdi")}</span><span><i class="is-sold"></i>${__("Sotib oldi")}</span>
					<span class="mp-sn-muted">${daily ? __("Ustunni bossangiz, o‘sha kun ko‘rsatiladi") : __("Ustunni bossangiz, o‘sha oy ko‘rsatiladi")}</span>
				</div>`);
		}

		render_wait() {
			const w = this.data.waiting;
			const mode = this.state.wait;
			const cfg = {
				new: { rows: w.new, count: w.new_count, empty: __("Hamma lid bilan gaplashilgan"), when: __("Kelgan"), last: __("Kutmoqda") },
				no_result: { rows: w.no_result, count: w.no_result_count, empty: __("Gaplashilgan hamma lidga natija yozilgan"), when: __("Qo‘ng‘iroq"), last: __("Kelgan") },
				callbacks: { rows: w.callbacks, count: w.callback_count, empty: __("Bugunga qayta qo‘ng‘iroq yo‘q"), when: __("Qayta qo‘ng‘iroq"), last: __("Menejer") },
			}[mode];
			const $el = this.$body.find(".mp-sn-wait");
			if (!cfg.rows.length) {
				$el.html(`<div class="mp-sn-empty mp-sn-empty--ok">✓ ${cfg.empty}</div>`);
				return;
			}
			const now = moment(w.now);
			const when_cell = (r) => {
				if (mode === "callbacks") {
					const late = r.keyingi_qongiroq < w.today;
					return `${esc(frappe.datetime.str_to_user(r.keyingi_qongiroq))}${late ? ` ${pill("kechikkan", "red")}` : ""}`;
				}
				if (mode === "no_result") return r.qongiroq ? esc(when(r.qongiroq)) : `<span class="mp-sn-muted">${__("qo‘ng‘iroqdan keyin qo‘shilgan")}</span>`;
				return esc(when(r.creation));
			};
			const last_cell = (r) => {
				if (mode === "callbacks") return esc(r.menejer_ismi || "—");
				if (mode === "no_result") return esc(when(r.creation));
				const waited = now.diff(moment(r.creation), "minutes");
				return `<b class="${waited > 60 ? "mp-sn-bad" : ""}">${ago(waited)}</b>`;
			};
			$el.html(`
			${mode === "no_result" ? `<div class="mp-sn-note">${__("Bu mijozlar bilan menejer gaplashgan, lekin Sotuv panelida natija («Oladi», «Olmaydi», «Keyinroq»…) yozmagan. Natija yozilmasa, lid «Yangi» bo‘lib qoladi va qayta qo‘ng‘iroq eslatmasi ishlamaydi.")}</div>` : ""}
			<div class="mp-sn-table mp-sn-table--wait">
				<div class="mp-sn-tr mp-sn-tr--head">
					<span>${__("Mijoz")}</span><span>${__("Tovar")}</span><span>${__("Manba")}</span>
					<span>${cfg.when}</span><span class="mp-sn-num">${cfg.last}</span>
				</div>
				${cfg.rows.map((r) => `
					<a class="mp-sn-tr ${mode === "callbacks" && r.keyingi_qongiroq < w.today ? "is-late" : ""}" href="/desk/murojaat/${encodeURIComponent(r.name)}">
						<span class="mp-sn-who"><b>${esc(r.mijoz_ismi || "—")}</b><small>${esc(r.telefon || "")}</small></span>
						<span class="mp-sn-cut" data-label="${__("Tovar")}">${r.tovar_nomi ? esc(r.tovar_nomi) : `<span class="mp-sn-muted">${__("ko‘rsatilmagan")}</span>`}</span>
						<span class="mp-sn-muted" data-label="${__("Manba")}">${esc(__(r.manba || ""))}</span>
						<span data-label="${cfg.when}">${when_cell(r)}</span>
						<span class="mp-sn-num" data-label="${cfg.last}">${last_cell(r)}</span>
					</a>`).join("")}
			</div>
			${cfg.count > cfg.rows.length ? `<div class="mp-sn-foot">${__("Ko‘rsatilgan: {0} ta, jami {1} ta", [cfg.rows.length, cfg.count])}</div>` : ""}`);
		}

		bought_html(rows) {
			if (!rows.length) return `<div class="mp-sn-empty">${__("Bu davrda kelgan lidlardan hali hech kim buyurtma bermagan")}</div>`;
			return `<div class="mp-sn-table mp-sn-table--bought">
				<div class="mp-sn-tr mp-sn-tr--head">
					<span>${__("Mijoz")}</span><span>${__("Tovar")}</span><span>${__("Buyurtma")}</span><span class="mp-sn-num">${__("Summa")}</span>
					<span>${__("To‘lov")}</span><span>${__("Menejer")}</span>
				</div>
				${rows.map((r) => `
					<a class="mp-sn-tr" href="${r.buyurtma ? `/desk/sales-order/${encodeURIComponent(r.buyurtma)}` : `/desk/murojaat/${encodeURIComponent(r.lead)}`}">
						<span class="mp-sn-who"><b>${esc(r.mijoz || "—")}</b><small>${esc(r.telefon || "")}</small></span>
						<span class="mp-sn-cut" data-label="${__("Tovar")}">${esc(r.tovar || "—")}</span>
						<span class="mp-sn-muted mp-sn-nowrap" data-label="${__("Buyurtma")}">${esc(r.buyurtma || "")}<small>${esc(when(r.sana))}</small></span>
						<span class="mp-sn-num" data-label="${__("Summa")}"><b>${r.summa ? money(r.summa) : "—"}</b></span>
						<span data-label="${__("To‘lov")}">${pill(r.tolov, PAY_COLOR[r.tolov])}${r.usul ? ` <small class="mp-sn-muted">${esc(r.usul)}</small>` : ""}</span>
						<span class="mp-sn-cut" data-label="${__("Menejer")}">${esc(r.menejer || "—")}</span>
					</a>`).join("")}
			</div>`;
		}

		managers_html(rows) {
			if (!rows.length) return `<div class="mp-sn-empty">${__("Sotuv menejeri yo‘q. Do‘kon sozlamalarida a’zolarga «Sotuv menejer» rolini qo‘shing.")}</div>`;
			const best = Math.max(...rows.map((r) => r.sales_amount)) || 1;
			return `<div class="mp-sn-table mp-sn-table--mgr">
				<div class="mp-sn-tr mp-sn-tr--head">
					<span>${__("Menejer")}</span><span class="mp-sn-num">${__("Qo‘ng‘iroq")}</span><span class="mp-sn-num">${__("Gaplashdi")}</span>
					<span>${__("Natijalar")}</span><span class="mp-sn-num">${__("Sotuv")}</span><span class="mp-sn-num">${__("Summa")}</span>
				</div>
				${rows.map((r) => `
					<div class="mp-sn-tr">
						<span class="mp-sn-who"><b>${esc(r.name || r.user)}</b><small>${r.contacts} ${__("ta mijoz bilan ishladi")}</small></span>
						<span class="mp-sn-num" data-label="${__("Qo‘ng‘iroq")}"><b>${num(r.calls)}</b><small>${r.calls ? __("{0} ta javob", [r.answered]) : ""}</small></span>
						<span class="mp-sn-num" data-label="${__("Gaplashdi")}">${talk(r.talk)}</span>
						<span class="mp-sn-res" data-label="${__("Natijalar")}">${r.results ? `<span class="mp-sn-res__list">${[
							["Oladi", r.oladi], ["Keyinroq", r.keyinroq], ["Javob bermadi", r.javob_bermadi], ["Olmaydi", r.olmaydi],
						].filter((x) => x[1]).map(([s, n]) => `<span><i style="background: var(--${STATE_COLOR[s]}-500)"></i>${esc(__(s))} <b>${n}</b></span>`).join("")}</span>` : `<span class="mp-sn-muted">—</span>`}</span>
						<span class="mp-sn-num" data-label="${__("Sotuv")}"><b>${num(r.sales)}</b><small>${r.contacts ? `${r.conversion}%` : ""}</small></span>
						<span class="mp-sn-num mp-sn-sum" data-label="${__("Summa")}"><b>${r.sales_amount ? money(r.sales_amount) : "—"}</b>
							<span class="mp-sn-meter"><i style="width:${((r.sales_amount / best) * 100).toFixed(1)}%"></i></span></span>
					</div>`).join("")}
			</div>
			<div class="mp-sn-foot">${__("«Sotuv» — menejer «Oladi» deb tasdiqlagan buyurtmalar (liddan yaratilgan va saytdagi). Foiz — ishlagan mijozlaridan nechtasi sotib oldi.")}</div>`;
		}

		items_html(rows) {
			if (!rows.length) return `<div class="mp-sn-empty">${__("Bu davrda lid tushmagan")}</div>`;
			const max = Math.max(...rows.map((r) => r.leads)) || 1;
			return rows.map((r) => `
				<div class="mp-sn-bar">
					<div class="mp-sn-bar__top">
						<span class="mp-sn-cut">${r.tid ? `<span class="mp-sn-tid">${esc(r.tid)}</span>` : ""}${esc(r.name || __("Tovar ko‘rsatilmagan"))}</span>
						<span><b>${num(r.leads)}</b> ${__("lid")} · <b>${num(r.ordered)}</b> ${__("sotildi")} <span class="mp-sn-muted">${r.conversion}%</span></span>
					</div>
					<div class="mp-sn-meter mp-sn-meter--two"><i style="width:${((r.leads / max) * 100).toFixed(1)}%"></i><b style="width:${((r.ordered / max) * 100).toFixed(1)}%"></b></div>
					${r.revenue ? `<div class="mp-sn-bar__sub">${money(r.revenue)}</div>` : ""}
				</div>`).join("");
		}

		sources_html(src) {
			if (!src.manba.length) return `<div class="mp-sn-empty">${__("Bu davrda lid tushmagan")}</div>`;
			const block = (rows) => {
				const max = Math.max(...rows.map((r) => r.leads)) || 1;
				return rows.map((r) => `
					<div class="mp-sn-bar">
						<div class="mp-sn-bar__top">
							<span class="mp-sn-cut">${esc(__(r.name))}</span>
							<span><b>${num(r.leads)}</b> ${__("lid")} · <b>${num(r.ordered)}</b> ${__("sotildi")} <span class="mp-sn-muted">${pct(r.ordered, r.leads)}%</span></span>
						</div>
						<div class="mp-sn-meter mp-sn-meter--two"><i style="width:${((r.leads / max) * 100).toFixed(1)}%"></i><b style="width:${((r.ordered / max) * 100).toFixed(1)}%"></b></div>
					</div>`).join("");
			};
			return `${block(src.manba)}
				${src.kampaniya.length ? `<div class="mp-sn-sub">${__("Reklama kampaniyalari")}</div>${block(src.kampaniya)}` : ""}`;
		}

		// Oxirgi qo'ng'iroqlar: xulosasi bo'lmasa ham ko'rinadi — yozuvni tinglash mumkin, AI holati va sababi yoziladi
		calls_html(c) {
			const off = c.blockers && c.blockers.length;
			const head = `<div class="mp-sn-ai__stat">
				${off ? `<span class="mp-sn-ai__off">⚠ ${__("AI tahlil o‘chiq")}: ${c.blockers.map(esc).join("; ")}</span>`
					: `<span class="mp-sn-ai__on">● ${__("AI tahlil yoqilgan")}</span>`}
				<span class="mp-sn-muted">${__("Shu davrda: {0} ta qo‘ng‘iroq, {1} tasida yozuv bor, {2} tasiga AI xulosa yozgan", [c.total, c.recorded, c.transcribed])}${c.failed ? ` · <span class="mp-sn-bad">${__("{0} tasida xato", [c.failed])}</span>` : ""}</span>
			</div>`;
			if (!c.rows.length) return `${head}<div class="mp-sn-empty">${__("Bu davrda qo‘ng‘iroq bo‘lmagan")}</div>`;
			const state = (r) => ({
				tayyor: `<div class="mp-sn-ai__text"><span class="mp-sn-ai__tag">AI</span>${esc(r.ai_xulosa).replace(/\n/g, "<br>")}</div>`,
				jarayonda: `<div class="mp-sn-ai__state">⏳ ${__("AI suhbatni matnga aylantirmoqda…")}</div>`,
				navbatda: `<div class="mp-sn-ai__state">⏳ ${__("AI navbatida — 15 daqiqa ichida xulosa chiqadi")}</div>`,
				xato: `<div class="mp-sn-ai__state is-bad">⚠ ${__("AI xulosa yoza olmadi")}: ${esc(r.xato_matni || "")}</div>`,
				ochiq: `<div class="mp-sn-ai__state">${__("AI o‘chiq — xulosa yozilmaydi")}</div>`,
				qisqa: `<div class="mp-sn-ai__state">${__("Juda qisqa qo‘ng‘iroq — tahlil qilinmaydi")}</div>`,
				yozuvsiz: `<div class="mp-sn-ai__state">${__("Ovoz yozuvi kelmagan")}</div>`,
			}[r.ai] || "");
			return `${head}<div class="mp-sn-ai">${c.rows.map((r) => `
				<div class="mp-sn-ai__row">
					<div class="mp-sn-ai__meta">
						<b>${esc(r.mijoz_ismi || r.telefon || __("Raqam noma’lum"))}</b>
						<a href="/desk/telefon-qongiroq/${encodeURIComponent(r.name)}">${__("Ochish")} ›</a>
					</div>
					<div class="mp-sn-muted mp-sn-ai__sub">${r.yonalish === "Kiruvchi" ? "📥 " + __("Kiruvchi") : "📤 " + __("Chiquvchi")} · ${esc(when(r.boshlandi))} · ${talk(r.davomiyligi)}${r.menejer_ismi ? ` · ${esc(r.menejer_ismi)}` : ""}</div>
					${r.yozuv ? mp.voice_note(r.yozuv, {}) : ""}
					${state(r)}
				</div>`).join("")}</div>`;
		}

		bind() {
			this.$body.find("[data-wait]").on("click", (e) => {
				this.state.wait = e.currentTarget.dataset.wait;
				$(e.currentTarget).addClass("is-active").siblings().removeClass("is-active");
				this.render_wait();
			});
			this.$body.find("[data-jump]").on("click", (e) => {
				this.state.wait = e.currentTarget.dataset.jump;
				this.$body.find(`[data-wait="${this.state.wait}"]`).addClass("is-active").siblings().removeClass("is-active");
				this.render_wait();
				this.$body.find("[data-wait-box]").get(0).scrollIntoView({ behavior: "smooth", block: "start" });
			});
			// Nazoratchida Sotuv paneli yo'q (faqat ko'radi) — buyurtmalar ro'yxati ochiladi
			this.$body.find("[data-panel]").on("click", () => (mp_sn_supervisor() ? frappe.set_route("List", "Sales Order") : frappe.set_route("sotuv-paneli")));
			this.$body.find(".mp-sn-cc__col").on("click", (e) => {
				const { from, to } = e.currentTarget.dataset;
				this.set_range(from, to, "custom");
			});
			if (this.$body.find(".mp-sn-ai").length) mp.voice_init(this.$body.find(".mp-sn-ai"));
		}
	}

	function inject_style() {
		if (document.getElementById("mp-sn-style")) return;
		$(`<style id="mp-sn-style">
			.mp-sn { padding: 4px var(--padding-md, 15px) 48px; }
			.page-form .mp-sn-filter { flex: 0 0 150px; max-width: 150px; }
			.page-form .mp-sn-filter--wide { flex-basis: 210px; max-width: 210px; }
			.mp-sn-empty { padding: 28px 8px; text-align: center; color: var(--text-muted); }
			.mp-sn-empty--ok { color: var(--green-600, #16a34a); }
			.mp-sn-muted { color: var(--text-muted); }
			.mp-sn-bad { color: var(--red-600, #dc2626); }
			.mp-sn-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-bottom: 14px; }
			.mp-sn-head__title { font-size: var(--text-xl); font-weight: 600; color: var(--heading-color); }
			.mp-sn-tag { padding: 2px 10px; border-radius: 10px; background: var(--subtle-fg); color: var(--text-muted); font-size: var(--text-xs); }

			/* Hozir */
			.mp-sn-now { display: grid; grid-template-columns: auto repeat(4, minmax(0, 1fr)); gap: 10px; align-items: stretch; margin-bottom: 14px; }
			.mp-sn-now__title { writing-mode: vertical-rl; transform: rotate(180deg); align-self: center; font-size: var(--text-xs); font-weight: 600;
				letter-spacing: .08em; color: var(--text-muted); }
			.mp-sn-now__tile { display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 12px; align-items: center;
				padding: 12px 16px; text-align: left; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg);
				background: var(--card-bg); cursor: pointer; transition: border-color .15s, transform .15s; }
			.mp-sn-now__tile:hover { transform: translateY(-1px); border-color: var(--gray-400); }
			.mp-sn-now__value { grid-row: span 2; font-size: 30px; font-weight: 700; line-height: 1; color: var(--heading-color); font-variant-numeric: tabular-nums; }
			.mp-sn-now__label { font-weight: 600; color: var(--heading-color); line-height: 1.3; }
			.mp-sn-now__sub { font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-now__tile.is-warn { background: var(--bg-orange); border-color: var(--orange-200, #fed7aa); }
			.mp-sn-now__tile.is-warn .mp-sn-now__value { color: var(--orange-600, #ea580c); }
			.mp-sn-now__tile.is-bad { background: var(--bg-red); border-color: var(--red-200, #fecaca); }
			.mp-sn-now__tile.is-bad .mp-sn-now__value { color: var(--red-600, #dc2626); }
			.mp-sn-now__tile.is-ok .mp-sn-now__value { color: var(--green-600, #16a34a); }

			/* KPI */
			.mp-sn-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
			.mp-sn-kpi { padding: 14px 16px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); min-width: 0; }
			.mp-sn-kpi__label { font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sn-kpi__value { margin-top: 4px; font-size: 24px; font-weight: 600; color: var(--heading-color); white-space: nowrap; overflow: hidden;
				text-overflow: ellipsis; font-variant-numeric: tabular-nums; }
			.mp-sn-kpi__value small { font-size: var(--text-md); font-weight: 600; color: var(--green-600, #16a34a); }
			.mp-sn-kpi__hint { margin-top: 2px; font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-kpi.is-good .mp-sn-kpi__value { color: var(--green-700, #15803d); }
			.mp-sn-kpi.is-money .mp-sn-kpi__value { font-size: 20px; line-height: 30px; }
			.mp-sn-kpi.is-warn .mp-sn-kpi__value { color: var(--orange-600, #ea580c); }
			.mp-sn-chg { font-weight: 600; }
			.mp-sn-chg--up { color: var(--green-600, #16a34a); }
			.mp-sn-chg--down { color: var(--red-600, #dc2626); }
			.mp-sn-chg--flat { color: var(--text-muted); }

			/* Qutilar */
			.mp-sn-box { margin-bottom: 14px; padding: 14px 16px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); min-width: 0; }
			.mp-sn-box__head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; margin-bottom: 12px; }
			.mp-sn-box__title { font-weight: 600; color: var(--heading-color); }
			.mp-sn-box__title span { margin-left: 6px; font-weight: 400; font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sn-foot { margin-top: 8px; font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-sub { margin: 14px 0 6px; font-size: var(--text-sm); font-weight: 600; color: var(--heading-color); }
			.mp-sn-two { display: grid; grid-template-columns: 1.25fr 1fr; gap: 14px; }
			.mp-sn-two > .mp-sn-box { margin-bottom: 14px; }
			.mp-sn-seg { display: inline-flex; padding: 3px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-sn-seg button { border: 0; background: none; padding: 4px 10px; border-radius: var(--border-radius-sm); font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sn-seg button span { margin-left: 4px; font-weight: 600; }
			.mp-sn-seg button.is-active { background: var(--card-bg); color: var(--text-color); box-shadow: var(--shadow-sm); }

			/* Voronka */
			.mp-sn-funnel__step { display: grid; grid-template-columns: 150px minmax(0, 1fr) 72px; gap: 12px; align-items: center; }
			.mp-sn-funnel__label { display: flex; flex-direction: column; min-width: 0; }
			.mp-sn-funnel__label b { color: var(--heading-color); font-weight: 600; }
			.mp-sn-funnel__label span { font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-sn-funnel__bar { height: 26px; border-radius: 6px; background: var(--subtle-fg); overflow: hidden; }
			.mp-sn-funnel { --sn-step-0: #3b5bdb; --sn-step-1: #4c6ef5; --sn-step-2: #5c7cfa; --sn-step-3: #748ffc; --sn-step-4: #2f9e44; }
			.mp-sn-funnel__bar i { display: block; height: 100%; border-radius: 6px; transition: width .4s ease; }
			.mp-sn-funnel__num { display: flex; flex-direction: column; align-items: flex-end; font-variant-numeric: tabular-nums; }
			.mp-sn-funnel__num b { font-size: var(--text-lg); color: var(--heading-color); }
			.mp-sn-funnel__num span { font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-funnel__drop { margin: 2px 0 2px 162px; font-size: var(--text-xs); color: var(--text-muted); }

			/* Holatlar */
			.mp-sn-stack { display: flex; gap: 2px; height: 14px; border-radius: 7px; overflow: hidden; margin: 4px 0 14px; }
			.mp-sn-stack i { display: block; height: 100%; }
			.mp-sn-legend__row { display: grid; grid-template-columns: minmax(0, 1fr) 56px 48px; gap: 8px; align-items: center; padding: 6px 0;
				border-top: 1px solid var(--border-color); font-variant-numeric: tabular-nums; }
			.mp-sn-legend__row:first-child { border-top: 0; }
			.mp-sn-legend__row > b, .mp-sn-legend__row > span:last-child { text-align: right; }
			.mp-sn-legend__row i { display: inline-block; width: 10px; height: 10px; margin-right: 8px; border-radius: 3px; vertical-align: -1px; }
			.mp-sn-legend__row.is-zero { opacity: .5; }

			/* Jadvallar */
			.mp-sn-table { overflow-x: auto; }
			.mp-sn-tr { display: grid; gap: 12px; align-items: center; padding: 9px 4px; border-top: 1px solid var(--border-color); color: var(--text-color); min-width: 0; }
			a.mp-sn-tr:hover { background: var(--subtle-fg); text-decoration: none; color: var(--text-color); }
			.mp-sn-tr--head { border-top: 0; padding-top: 0; font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-tr.is-late { background: var(--bg-red); }
			.mp-sn-table--wait .mp-sn-tr { grid-template-columns: minmax(150px, 1.3fr) minmax(120px, 1.2fr) 100px 150px 140px; min-width: 700px; }
			.mp-sn-table--bought .mp-sn-tr { grid-template-columns: minmax(150px, 1.3fr) minmax(120px, 1.1fr) 175px 130px 170px minmax(100px, 1fr); min-width: 880px; }
			.mp-sn-table--mgr .mp-sn-tr { grid-template-columns: minmax(160px, 1.3fr) 90px 110px minmax(220px, 1.6fr) 80px minmax(150px, 1fr); min-width: 860px; }
			.mp-sn-nowrap { white-space: nowrap; }
			.mp-sn-num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
			.mp-sn-num small, .mp-sn-tr > span small { display: block; font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-who { display: flex; flex-direction: column; min-width: 0; }
			.mp-sn-who b { color: var(--heading-color); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-sn-who small { font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-cut { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-sn-res__list { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
			.mp-sn-res__list b { color: var(--heading-color); }
			.mp-sn-res i { display: inline-block; width: 8px; height: 8px; margin-right: 4px; border-radius: 50%; }
			.mp-sn-pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: var(--text-xs); font-weight: 500; white-space: nowrap;
				background: var(--bg-gray, var(--subtle-fg)); color: var(--text-muted); }
			.mp-sn-pill--green { background: var(--bg-green); color: var(--green-700, #15803d); }
			.mp-sn-pill--orange { background: var(--bg-orange); color: var(--orange-700, #c2410c); }
			.mp-sn-pill--red { background: var(--bg-red); color: var(--red-700, #b91c1c); }

			/* Ulush chiziqlari */
			.mp-sn-meter { position: relative; display: block; height: 5px; margin-top: 5px; border-radius: 3px; background: var(--subtle-fg); overflow: hidden; }
			.mp-sn-meter i { display: block; height: 100%; min-width: 4px; border-radius: 3px; background: #4c6ef5; }
			.mp-sn-meter--two i { background: var(--blue-200, #bfdbfe); }
			.mp-sn-meter--two b { position: absolute; left: 0; top: 0; height: 100%; border-radius: 3px; background: var(--green-500, #22c55e); }
			.mp-sn-bar { padding: 8px 0; border-top: 1px solid var(--border-color); }
			.mp-sn-bar:first-child, .mp-sn-sub + .mp-sn-bar { border-top: 0; padding-top: 0; }
			.mp-sn-bar__top { display: flex; justify-content: space-between; gap: 10px; font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
			.mp-sn-bar__top > span:last-child { white-space: nowrap; }
			.mp-sn-bar__sub { margin-top: 3px; font-size: var(--text-xs); color: var(--text-muted); }
			.mp-sn-tid { display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 4px; background: var(--subtle-fg);
				font-family: var(--font-family-monospace, monospace); font-size: var(--text-xs); color: var(--text-muted); }

			/* Grafik */
			.mp-sn-cc__sum { display: flex; flex-wrap: wrap; gap: 4px 18px; margin-bottom: 14px; font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sn-cc__sum b { color: var(--heading-color); }
			.mp-sn-cc { position: relative; height: 240px; padding: 0 0 52px 28px; }
			.mp-sn-cc__grid { position: absolute; left: 28px; right: 0; top: 18px; bottom: 52px; }
			.mp-sn-cc__grid span { position: absolute; left: 0; right: 0; border-top: 1px dashed var(--border-color); }
			.mp-sn-cc__grid span:first-child { border-top: 1px solid var(--gray-300, #d1d5db); }
			.mp-sn-cc__grid i { position: absolute; left: -28px; width: 22px; top: -8px; text-align: right; font-style: normal; font-size: 11px; color: var(--text-muted); }
			.mp-sn-cc__cols { position: relative; display: flex; align-items: stretch; gap: 3px; height: 100%; padding-top: 18px; }
			.mp-sn-cc__col { position: relative; flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; padding: 0; border: 0; background: none;
				border-radius: 4px; cursor: pointer; }
			.mp-sn-cc__col:hover { background: var(--subtle-fg); }
			.mp-sn-cc__col.is-weekend .mp-sn-cc__x small { color: var(--red-500, #ef4444); }
			.mp-sn-cc__area { position: relative; flex: 1; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }
			.mp-sn-cc__bar { position: relative; display: flex; flex-direction: column; justify-content: flex-end; width: min(70%, 28px);
				border-radius: 4px 4px 0 0; background: #8b9cf7; overflow: hidden; }
			.mp-sn-cc__bar > span { display: block; width: 100%; background: #2f9e44; }
			.mp-sn-cc__val { margin-bottom: 3px; font-size: 11px; font-weight: 600; line-height: 1; color: var(--heading-color); white-space: nowrap; }
			.mp-sn-cc__val em { margin-left: 3px; font-style: normal; color: #2f9e44; }
			.mp-sn-cc__x { position: absolute; left: 0; right: 0; bottom: -34px; display: flex; flex-direction: column; align-items: center; line-height: 1.2; }
			.mp-sn-cc__x b { font-size: 12px; color: var(--heading-color); font-weight: 600; }
			.mp-sn-cc__x small { font-size: 10px; color: var(--text-muted); }
			.mp-sn-cc__month { position: absolute; bottom: -50px; left: 2px; font-size: 10px; font-weight: 600; color: var(--text-muted); white-space: nowrap; }
			.mp-sn-cc__legend { display: flex; flex-wrap: wrap; gap: 6px 18px; margin-top: 12px; font-size: var(--text-sm); }
			.mp-sn-cc__legend i { display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 2px; vertical-align: -1px; }
			.mp-sn-cc__legend i.is-lead { background: #8b9cf7; }
			.mp-sn-cc__legend i.is-sold { background: #2f9e44; }
			.mp-sn-note { margin-bottom: 10px; padding: 8px 12px; border-radius: var(--border-radius-md); background: var(--bg-orange); color: var(--orange-800, #9a3412); font-size: var(--text-sm); }
			.mp-sn-ai__tag { display: inline-block; margin-right: 6px; padding: 0 5px; border-radius: 4px; background: var(--bg-purple, #f3e8ff);
				color: var(--purple-700, #7e22ce); font-size: 10px; font-weight: 700; vertical-align: 1px; }

			/* AI */
			.mp-sn-ai__stat { display: flex; flex-wrap: wrap; gap: 6px 16px; margin-bottom: 10px; font-size: var(--text-sm); }
			.mp-sn-ai__on { color: var(--green-600, #16a34a); font-weight: 600; }
			.mp-sn-ai__off { color: var(--orange-700, #c2410c); font-weight: 600; }
			.mp-sn-ai { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
			.mp-sn-ai__row { display: grid; gap: 6px; align-content: start; padding: 10px 12px; border: 1px solid var(--border-color);
				border-radius: var(--border-radius-md); color: var(--text-color); min-width: 0; }
			.mp-sn-ai__meta { display: flex; justify-content: space-between; gap: 10px; font-size: var(--text-sm); }
			.mp-sn-ai__meta a { flex: none; color: var(--text-muted); }
			.mp-sn-ai__sub { font-size: var(--text-xs); }
			.mp-sn-ai__state { font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sn-ai__state.is-bad { color: var(--red-600, #dc2626); }
			.mp-sn-ai__meta b { color: var(--heading-color); }
			.mp-sn-ai__text { font-size: var(--text-sm); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; }

			@media (max-width: 1200px) { .mp-sn-kpis { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
			@media (max-width: 900px) {
				.mp-sn-two { grid-template-columns: 1fr; }
				.mp-sn-ai { grid-template-columns: 1fr; }
				.mp-sn-now { grid-template-columns: 1fr 1fr; }
				.mp-sn-now__title { grid-column: 1 / -1; writing-mode: horizontal-tb; transform: none; align-self: start; }
			}
			@media (max-width: 640px) {
				.page-form .mp-sn-filter, .page-form .mp-sn-filter--wide { flex: 1 1 45%; max-width: none; }
				.mp-sn-now { grid-template-columns: 1fr; }
				.mp-sn-cc__cols { gap: 1px; }
				.mp-sn-cc__val { font-size: 10px; }
				.mp-sn-cc__val em { display: none; }
				.mp-sn-kpis { grid-template-columns: 1fr 1fr; }
				.mp-sn-kpi.is-money { grid-column: 1 / -1; }
				.mp-sn-kpi.is-money .mp-sn-kpi__value { font-size: 24px; }
				/* Jadval qatorlari — kartochka: tepada mijoz/menejer, ostida «yorliq — qiymat» qatorlari */
				.mp-sn-table { overflow: visible; }
				.mp-sn-table .mp-sn-tr { display: block; min-width: 0 !important; padding: 10px 4px; }
				.mp-sn-table .mp-sn-tr--head { display: none; }
				.mp-sn-table .mp-sn-tr > [data-label] { display: flex; justify-content: flex-end; align-items: baseline; flex-wrap: wrap; gap: 4px 10px;
					padding: 2px 0; text-align: right; white-space: normal; overflow: visible; }
				.mp-sn-table .mp-sn-tr > [data-label]::before { content: attr(data-label); flex: none; margin-right: auto; text-align: left; color: var(--text-muted); font-size: var(--text-xs); }
				.mp-sn-table .mp-sn-tr > .mp-sn-who { margin-bottom: 4px; }
				.mp-sn-tr > [data-label] small { display: inline; margin-left: 6px; }
				.mp-sn-res__list { justify-content: flex-end; }
				.mp-sn-sum { flex-wrap: wrap; }
				.mp-sn-sum .mp-sn-meter { flex-basis: 100%; }
				.mp-sn-funnel__step { grid-template-columns: 110px minmax(0, 1fr) 56px; gap: 8px; }
				.mp-sn-funnel__label span { display: none; }
				.mp-sn-funnel__drop { margin-left: 118px; }
			}
		</style>`).appendTo(document.head);
	}
})();
