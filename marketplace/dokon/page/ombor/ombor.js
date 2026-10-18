// Ombor: sotuvchining barcha tovarlari rasmi, nomi va qoldig'i. Umumiy sonni yozib "Saqlash" bosiladi.

frappe.pages["ombor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Ombor"),
		single_column: true,
	});
	wrapper.ombor = new OmborPage(page);
};

frappe.pages["ombor"].on_page_show = function (wrapper) {
	// Saqlanmagan o'zgarishlar bo'lsa, qayta yuklab o'chirib yubormaymiz
	if (!Object.keys(wrapper.ombor.edits).length) wrapper.ombor.load();
};

class OmborPage {
	constructor(page) {
		this.page = page;
		this.state = { q: "", filter: "", shop: "" };
		this.edits = {}; // {item_code: yangi son}
		this.open = new Set(); // ochilgan andozalar
		this.page.set_secondary_action(__("Yangilash"), () => this.load(true), "refresh");
		this.$body = $(`<div class="mp-om"></div>`).appendTo(page.main);
		this.$bar = $(`
			<div class="mp-om__bar">
				<span class="mp-om__bar-text"></span>
				<button class="btn btn-default btn-sm" data-act="reset">${__("Bekor qilish")}</button>
				<button class="btn btn-primary btn-sm" data-act="save">${__("Saqlash")}</button>
			</div>`).appendTo(page.main);
		this.$bar.find("[data-act=save]").on("click", () => this.save());
		this.$bar.find("[data-act=reset]").on("click", () => {
			this.edits = {};
			this.render();
		});
		this.inject_style();
	}

	async load(force) {
		if (force && Object.keys(this.edits).length && !(await this.confirm_discard())) return;
		this.edits = {};
		this.$body.html(`<div class="mp-om__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		this.update_bar();
		const { message } = await frappe.call("marketplace.stock_page.get_stock_overview", { shop: this.state.shop || null });
		this.data = message;
		this.state.shop = message.shop || "";
		this.render();
	}

	confirm_discard() {
		return new Promise((resolve) =>
			frappe.confirm(__("Saqlanmagan o'zgarishlar o'chadi. Davom etasizmi?"), () => resolve(true), () => resolve(false))
		);
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

		this.$body.html(`
			<div class="mp-om__hint">${frappe.utils.icon("info", "sm")} ${__("Omborda hozir nechta bor bo'lsa, o'shani yozing (qo'shiladigan sonni emas, umumiy sonni)")}</div>
			<div class="mp-om__toolbar">
				${shops.length ? `<select class="form-control mp-om__shop">
					<option value="">${__("Do'konni tanlang")}</option>
					${shops.map((s) => `<option value="${esc(s.name)}" ${s.name === this.state.shop ? "selected" : ""}>${esc(s.shop_name)}</option>`).join("")}
				</select>` : ""}
				<input class="form-control mp-om__search" type="search" placeholder="${__("Tovar nomi yoki turi…")}" value="${esc(this.state.q)}">
				<div class="mp-om__chips">
					${chips.map(([k, l]) => `<button class="${this.state.filter === k ? "is-active" : ""}" data-filter="${k}">${l} <span>${counts[k]}</span></button>`).join("")}
				</div>
			</div>
			<div class="mp-om__list"></div>
		`);

		const q = this.state.q.trim().toLowerCase();
		const list = products.filter((p) => {
			if (q && !`${p.name} ${p.category || ""} ${p.variants.map((v) => v.label).join(" ")}`.toLowerCase().includes(q)) return false;
			if (this.state.filter === "out") return p.status === "Tugagan";
			if (this.state.filter === "low") return p.status === "Kam qolgan" || (p.status !== "Tugagan" && p.low_variants);
			return true;
		});

		const $list = this.$body.find(".mp-om__list");
		if (!this.data.shop) {
			$list.html(`<div class="mp-om__empty text-muted">${__("Do'konni tanlang")}</div>`);
		} else if (!list.length) {
			$list.html(`<div class="mp-om__empty text-muted">${products.length ? __("Mos tovar topilmadi") : __("Hali tovar yo'q")}</div>`);
		}
		for (const p of list) $list.append(this.card(p));

		this.bind();
		this.update_bar();
	}

	card(p) {
		const esc = frappe.utils.escape_html;
		const open = this.open.has(p.code) || (this.state.q && p.is_template);
		const pic = p.picture
			? `<img src="${esc(p.picture)}" alt="" loading="lazy">`
			: `<span>${esc((p.name || "?").charAt(0).toUpperCase())}</span>`;
		const badge = (s) => (s ? `<span class="indicator-pill ${s === "Tugagan" ? "red" : "orange"}">${__(s)}</span>` : "");
		const total = p.is_template ? this.template_total(p) : this.qty_of(p.code, p.actual);

		const variants_hint = p.is_template
			? `${p.variants.length} ${__("ta variant")}${p.low_variants ? ` · <span class="mp-om__warn">${p.low_variants} ${__("tasi kam/tugagan")}</span>` : ""}`
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
					${p.is_template
						? `<div class="mp-om__total"><b data-total="${esc(p.code)}">${format_number(total, null, 0)}</b><span>${__("dona")}</span></div>
						   <span class="mp-om__chev">${frappe.utils.icon("down", "sm")}</span>`
						: this.input_cell(p.code, p.actual, p.reserved)}
				</div>
				${p.is_template ? `<div class="mp-om__variants">
					${p.variants.length
						? p.variants.map((v) => `
							<div class="mp-om__row">
								<div class="mp-om__label">${esc(v.label)} ${badge(v.status)}</div>
								${this.input_cell(v.code, v.actual, v.reserved, p.code)}
							</div>`).join("")
						: `<div class="text-muted small">${__("Variantlar hali yaratilmagan")}</div>`}
				</div>` : ""}
			</div>`;
	}

	input_cell(code, actual, reserved, parent = "") {
		const esc = frappe.utils.escape_html;
		const val = this.qty_of(code, actual);
		return `
			<div class="mp-om__qty">
				<input type="number" min="0" step="1" inputmode="numeric" class="form-control ${code in this.edits ? "is-changed" : ""}"
					data-item="${esc(code)}" data-actual="${actual}" data-parent="${esc(parent)}" value="${val}">
				${reserved > 0 ? `<div class="mp-om__reserved">${__("zaxirada")} ${format_number(reserved, null, 0)}</div>` : ""}
			</div>`;
	}

	qty_of(code, actual) {
		return code in this.edits ? this.edits[code] : actual;
	}

	template_total(p) {
		return p.variants.reduce((s, v) => s + (Number(this.qty_of(v.code, v.actual)) || 0), 0);
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
		this.$body.find(".mp-om__shop").on("change", async (e) => {
			if (Object.keys(this.edits).length && !(await this.confirm_discard())) return this.render();
			this.state.shop = e.target.value;
			this.edits = {};
			this.load();
		});
		this.$body.find("[data-toggle]").on("click", (e) => {
			const code = e.currentTarget.dataset.toggle;
			this.open.has(code) ? this.open.delete(code) : this.open.add(code);
			$(e.currentTarget).closest(".mp-om__card").toggleClass("is-open");
		});
		this.$body.find("input[data-item]").on("input", (e) => {
			const el = e.target;
			const actual = Number(el.dataset.actual);
			if (el.value === "" || Number(el.value) === actual) delete this.edits[el.dataset.item];
			else this.edits[el.dataset.item] = el.value;
			el.classList.toggle("is-changed", el.dataset.item in this.edits);
			const parent = el.dataset.parent && this.data.products.find((p) => p.code === el.dataset.parent);
			if (parent) this.$body.find(`[data-total="${CSS.escape(parent.code)}"]`).text(format_number(this.template_total(parent), null, 0));
			this.update_bar();
		});
	}

	update_bar() {
		const n = Object.keys(this.edits).length;
		this.$bar.toggleClass("is-visible", n > 0);
		this.$bar.find(".mp-om__bar-text").text(`${n} ${__("ta tovar o'zgardi")}`);
	}

	async save() {
		const rows = Object.entries(this.edits).map(([item_code, qty]) => ({ item_code, qty }));
		const bad = rows.find((r) => !/^\d+$/.test(String(r.qty).trim()));
		if (bad) {
			frappe.msgprint(__("Son 0 yoki undan katta butun son bo'lishi kerak"));
			return;
		}
		if (!rows.length) return;
		const $btn = this.$bar.find("[data-act=save]").prop("disabled", true);
		try {
			const { message } = await frappe.call({
				method: "marketplace.stock_page.save_stock",
				args: { rows, shop: this.state.shop || null },
				freeze: true,
				freeze_message: __("Saqlanmoqda…"),
			});
			frappe.show_alert({ message: `${message || 0} ${__("ta tovar qoldig'i yangilandi")}`, indicator: "green" });
			this.edits = {};
			this.load();
		} finally {
			$btn.prop("disabled", false);
		}
	}

	inject_style() {
		if (document.getElementById("mp-om-style")) return;
		$(`<style id="mp-om-style">
			.mp-om { padding: 4px 0 90px; }
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
			.mp-om__variants { display: none; border-top: 1px solid var(--border-color); padding: 4px 14px 8px 82px; }
			.mp-om__card.is-open .mp-om__variants { display: block; }
			.mp-om__row { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px dashed var(--border-color); }
			.mp-om__row:last-child { border-bottom: 0; }
			.mp-om__label { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; color: var(--text-color); }
			.mp-om__qty { flex: none; width: 96px; text-align: right; }
			.mp-om__qty input { text-align: right; font-weight: 600; }
			.mp-om__qty input.is-changed { border-color: var(--primary); box-shadow: 0 0 0 2px var(--bg-blue); }
			.mp-om__reserved { margin-top: 2px; color: var(--text-muted); font-size: var(--text-xs); white-space: nowrap; }
			.mp-om__bar { position: sticky; bottom: 12px; z-index: 5; display: none; align-items: center; gap: 8px; justify-content: flex-end;
				margin: -70px 0 12px; padding: 10px 14px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg);
				background: var(--card-bg); box-shadow: var(--shadow-lg); }
			.mp-om__bar.is-visible { display: flex; }
			.mp-om__bar-text { margin-right: auto; font-weight: 600; color: var(--heading-color); }
			@media (max-width: 640px) {
				.mp-om__head { padding: 10px; gap: 10px; }
				.mp-om__pic { width: 44px; height: 44px; }
				.mp-om__variants { padding-left: 14px; }
				.mp-om__qty { width: 80px; }
				.mp-om__search { max-width: none; }
			}
		</style>`).appendTo(document.head);
	}
}
