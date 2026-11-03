// Ombor: sotuvchining barcha tovarlari qoldig'i — faqat ko'rish.
// Kirim tovar formasining "Ombor" tabida qilinadi ("Kirim qilish" tugmasi o'sha yerga olib boradi), kamayish — faqat sotuvdan.
// Variantli tovar ochilganda rang × o'lcham bo'yicha qoldiq (mp.stock_grid). "Kirim tarixi" — kimdan, nechta, necha puldan.

frappe.pages["ombor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Ombor"),
		single_column: true,
	});
	wrapper.ombor = new OmborPage(page);
};

frappe.pages["ombor"].on_page_show = function (wrapper) {
	wrapper.ombor.load();
};

class OmborPage {
	constructor(page) {
		this.page = page;
		this.state = { q: "", filter: "", shop: "", view: "stock" };
		this.grids = {}; // andoza: get_variant_matrix natijasi
		this.open = new Set(); // ochilgan andozalar
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-om"></div>`).appendTo(page.main);
		this.inject_style();
	}

	async load() {
		this.grids = {};
		this.movements = null;
		if (!this.data) this.$body.html(`<div class="mp-om__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		const { message } = await frappe.call("marketplace.stock_page.get_stock_overview", { shop: this.state.shop || null });
		this.data = message;
		this.state.shop = message.shop || "";
		this.render();
	}

	render() {
		const esc = frappe.utils.escape_html;
		const { products = [], shops = [] } = this.data;
		const counts = {
			"": products.length,
			low: products.filter((p) => p.status === "Kam qolgan" || (p.status !== "Tugagan" && p.low_variants)).length,
			out: products.filter((p) => p.status === "Tugagan").length,
		};
		const chips = [
			["", __("Hammasi")],
			["low", __("Kam qolgan")],
			["out", __("Tugagan")],
		];
		const total = products.reduce((a, p) => a + Math.max(p.actual, 0), 0);
		const stock_view = this.state.view === "stock";

		this.$body.html(`
			<div class="mp-om__hint">${frappe.utils.icon("info", "sm")}<span>${__("Bu sahifa faqat ko'rish uchun. Yangi tovar kelsa — tovarni oching, <b>Ombor</b> tabida qaysi kontragentdan olganingizni, rang, o'lcham, nechta kelganini va necha puldan olganingizni yozing. Ombor faqat kirim bilan ko'payadi, sotuvda o'zi kamayadi.")}</span></div>
			<div class="mp-om__tabs">
				<button class="${stock_view ? "is-active" : ""}" data-view="stock">${__("Qoldiq")} <span>${format_number(total, null, 0)} ${__("dona")}</span></button>
				<button class="${stock_view ? "" : "is-active"}" data-view="log">${__("Kirim tarixi")}</button>
			</div>
			<div class="mp-om__toolbar">
				${shops.length ? `<select class="form-control mp-om__shop">
					<option value="">${__("Do'konni tanlang")}</option>
					${shops.map((s) => `<option value="${esc(s.name)}" ${s.name === this.state.shop ? "selected" : ""}>${esc(s.shop_name)}</option>`).join("")}
				</select>` : ""}
				${stock_view ? `
				<input class="form-control mp-om__search" type="search" placeholder="${__("Tovar nomi yoki turi…")}" value="${esc(this.state.q)}">
				<div class="mp-om__chips">
					${chips.map(([k, l]) => `<button class="${this.state.filter === k ? "is-active" : ""}" data-filter="${k}">${l} <span>${counts[k]}</span></button>`).join("")}
				</div>` : ""}
			</div>
			<div class="mp-om__list"></div>
		`);

		const $list = this.$body.find(".mp-om__list");
		if (!this.data.shop) {
			$list.html(`<div class="mp-om__empty text-muted">${__("Do'konni tanlang")}</div>`);
		} else if (!stock_view) {
			this.render_log($list);
		} else {
			const q = this.state.q.trim().toLowerCase();
			const list = products.filter((p) => {
				if (q && !`${p.name} ${p.category || ""} ${p.variants.map((v) => v.label).join(" ")}`.toLowerCase().includes(q)) return false;
				if (this.state.filter === "out") return p.status === "Tugagan";
				if (this.state.filter === "low") return p.status === "Kam qolgan" || (p.status !== "Tugagan" && p.low_variants);
				return true;
			});
			if (!list.length) {
				$list.html(`<div class="mp-om__empty text-muted">${products.length ? __("Mos tovar topilmadi") : __("Hali tovar yo'q")}</div>`);
			}
			for (const p of list) $list.append(this.card(p));
		}
		this.bind();
	}

	async render_log($list) {
		if (!this.movements) {
			$list.html(`<div class="mp-om__empty text-muted">${__("Yuklanmoqda…")}</div>`);
			this.movements = await frappe.xcall("marketplace.stock_page.get_movements", { shop: this.state.shop || null });
		}
		$list.html(`<div class="mp-om__log">${mp.journal(this.movements, { show_item: true, empty: __("Hali kirim bo'lmagan") })}</div>`);
	}

	card(p) {
		const esc = frappe.utils.escape_html;
		const open = this.open.has(p.code) || (this.state.q && p.is_template);
		const pic = p.picture
			? `<img src="${esc(p.picture)}" alt="" loading="lazy">`
			: `<span>${esc((p.name || "?").charAt(0).toUpperCase())}</span>`;
		const badge = (s) => (s ? `<span class="indicator-pill ${s === "Tugagan" ? "red" : "orange"}">${__(s)}</span>` : "");
		// Holatlar alohida: jadvalda omborda bori (actual) ko'rinadi, holat esa buyurtmaga band qilinganini ayirib
		// hisoblanadi — bori bor, lekin hammasi band bo'lsa "tugagan" emas, "buyurtmaga band" deymiz
		const count = (fn) => p.variants.filter(fn).length;
		const warn = [
			[count((v) => v.status === "Kam qolgan"), __("tasi kam qolgan")],
			[count((v) => v.status === "Tugagan" && v.actual <= 0), __("tasi tugagan")],
			[count((v) => v.status === "Tugagan" && v.actual > 0), __("tasi buyurtmaga band")],
		]
			.filter(([n]) => n)
			.map(([n, label]) => `${n} ${label}`)
			.join(", ");
		const variants_hint = p.is_template
			? `${p.variants.length} ${__("ta variant")}${warn ? ` · <span class="mp-om__warn">${warn}</span>` : ""}`
			: "";

		return `
			<div class="mp-om__card ${open ? "is-open" : ""}" data-code="${esc(p.code)}">
				<div class="mp-om__head" ${p.is_template ? `data-toggle="${esc(p.code)}"` : ""}>
					<div class="mp-om__pic">${pic}</div>
					<div class="mp-om__info">
						<div class="mp-om__name">${esc(p.name)} ${badge(p.status)}</div>
						<div class="mp-om__meta">${esc([p.category, p.price ? `${format_number(p.price, null, 0)} so‘m` : ""].filter(Boolean).join(" · "))}</div>
						${variants_hint ? `<div class="mp-om__meta">${variants_hint}</div>` : ""}
					</div>
					<div class="mp-om__total"><b>${format_number(p.actual, null, 0)}</b><span>${__("dona")}${p.reserved > 0 ? ` · ${__("zaxirada")} ${format_number(p.reserved, null, 0)}` : ""}</span></div>
					<button class="btn btn-default btn-xs mp-om__add" data-kirim="${esc(p.code)}">${__("+ Kirim qilish")}</button>
					${p.is_template ? `<span class="mp-om__chev">${frappe.utils.icon("down", "sm")}</span>` : ""}
				</div>
				${p.is_template ? `<div class="mp-om__variants"><div data-grid="${esc(p.code)}"><div class="text-muted small">${__("Yuklanmoqda…")}</div></div></div>` : ""}
			</div>`;
	}

	// Andoza ochilganda: rang × o'lcham bo'yicha omborda nechta bor
	async mount_grid(code) {
		const $el = this.$body.find(`[data-grid="${CSS.escape(code)}"]`);
		if (!$el.length) return;
		this.grids[code] = this.grids[code] || (await frappe.xcall("marketplace.seller_desk.get_variant_matrix", { template: code }));
		$el.html(mp.stock_grid(this.grids[code]));
	}

	bind() {
		const $search = this.$body.find(".mp-om__search");
		$search.on(
			"input",
			frappe.utils.debounce(() => {
				this.state.q = $search.val();
				this.render();
				this.$body.find(".mp-om__search").trigger("focus").get(0).setSelectionRange(9999, 9999);
			}, 250)
		);
		this.$body.find("[data-filter]").on("click", (e) => {
			this.state.filter = e.currentTarget.dataset.filter;
			this.render();
		});
		this.$body.find("[data-view]").on("click", (e) => {
			this.state.view = e.currentTarget.dataset.view;
			this.render();
		});
		this.$body.find(".mp-om__shop").on("change", (e) => {
			this.state.shop = e.target.value;
			this.load();
		});
		this.$body.find("[data-kirim]").on("click", (e) => {
			e.stopPropagation();
			mp.open_ombor_of = e.currentTarget.dataset.kirim;
			frappe.set_route("Form", "Item", e.currentTarget.dataset.kirim);
		});
		this.$body.find("[data-toggle]").on("click", (e) => {
			const code = e.currentTarget.dataset.toggle;
			this.open.has(code) ? this.open.delete(code) : this.open.add(code);
			const $card = $(e.currentTarget).closest(".mp-om__card").toggleClass("is-open");
			if ($card.hasClass("is-open")) this.mount_grid(code);
		});
		this.$body.find(".mp-om__card.is-open[data-code]").each((_, el) => this.mount_grid(el.dataset.code));
	}

	inject_style() {
		if (document.getElementById("mp-om-style")) return;
		$(`<style id="mp-om-style">
			.mp-om { padding: 4px var(--padding-md, 15px) 40px; }
			.mp-om__tabs { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--border-color); }
			.mp-om__tabs button { border: 0; background: none; padding: 8px 14px; margin-bottom: -1px; border-bottom: 2px solid transparent;
				color: var(--text-muted); font-weight: 600; }
			.mp-om__tabs button span { margin-left: 6px; font-weight: 400; }
			.mp-om__tabs button.is-active { color: var(--heading-color); border-bottom-color: var(--primary); }
			.mp-om__log { padding: 6px 14px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-om__log .mp-jr { max-height: none; }
			.mp-om__add { flex: none; }
			.mp-om__hint { display: flex; gap: 8px; align-items: center; padding: 10px 14px; margin-bottom: 14px; border-radius: var(--border-radius-md);
				background: var(--bg-blue); color: var(--text-on-blue); font-size: var(--text-sm); }
			.mp-om__toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
			.mp-om__search { flex: 1 1 220px; max-width: 360px; }
			.mp-om__shop { flex: 0 1 220px; }
			.mp-om__chips { display: inline-flex; flex-wrap: wrap; gap: 6px; }
			.mp-om__chips button { border: 1px solid var(--border-color); background: var(--card-bg); padding: 5px 12px; border-radius: 16px;
				font-size: var(--text-sm); color: var(--text-muted); }
			.mp-om__chips button span { margin-left: 4px; opacity: .7; }
			.mp-om__chips button.is-active { background: var(--text-color); border-color: var(--text-color); color: var(--fg-color, var(--card-bg)); }
			.mp-om__list { display: flex; flex-direction: column; gap: 10px; }
			.mp-om__empty { padding: 60px 0; text-align: center; }
			.mp-om__card { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); overflow: hidden; }
			.mp-om__head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; }
			.mp-om__head[data-toggle] { cursor: pointer; }
			.mp-om__head[data-toggle]:hover { background: var(--subtle-fg); }
			.mp-om__pic { flex: none; width: 56px; height: 56px; border-radius: var(--border-radius-md); overflow: hidden; background: var(--subtle-fg);
				display: grid; place-items: center; color: var(--text-muted); font-weight: 600; font-size: 20px; }
			.mp-om__pic img { width: 100%; height: 100%; object-fit: cover; }
			.mp-om__info { flex: 1; min-width: 0; }
			.mp-om__name { font-weight: 600; color: var(--heading-color); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
			.mp-om__meta { color: var(--text-muted); font-size: var(--text-sm); }
			.mp-om__warn { color: var(--orange-500, #d97706); }
			.mp-om__total { text-align: right; line-height: 1.1; }
			.mp-om__total b { display: block; font-size: var(--text-xl); color: var(--heading-color); }
			.mp-om__total span { color: var(--text-muted); font-size: var(--text-xs); }
			.mp-om__chev { transition: transform .15s; color: var(--text-muted); }
			.mp-om__card.is-open .mp-om__chev { transform: rotate(180deg); }
			.mp-om__variants { display: none; border-top: 1px solid var(--border-color); padding: 10px 14px 12px 82px; }
			.mp-om__card.is-open .mp-om__variants { display: block; }
			@media (max-width: 640px) {
				.mp-om__head { padding: 10px; gap: 10px; flex-wrap: wrap; }
				.mp-om__info { flex-basis: calc(100% - 140px); }
				.mp-om__add { margin-left: auto; }
				.mp-om__pic { width: 44px; height: 44px; }
				.mp-om__variants { padding-left: 14px; }
				.mp-om__search { max-width: none; }
			}
		</style>`).appendTo(document.head);
	}
}
