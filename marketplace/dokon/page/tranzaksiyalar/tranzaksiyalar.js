// Tranzaksiyalar: do'konga Payme, Click va Naqd orqali qilingan to'lovlar (kassa.transactions).
// Har qator — bitta to'lov urinishi: vaqt, noyob To'lov ID, provayder, holat, mijoz, telefon, tovar ID, summa.
// Tovar ID bosilsa — shu mijoz nima xarid qilgani (kassa.transaction_items).

frappe.pages["tranzaksiyalar"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Tranzaksiyalar"), single_column: true });
	wrapper.tx = new Tranzaksiyalar(page);
};

frappe.pages["tranzaksiyalar"].on_page_show = function (wrapper) {
	wrapper.tx?.load();
};

const MP_TX_PROVIDER_CLS = { Payme: "cyan", Click: "blue", Naqd: "orange" };
const MP_TX_STATUS_CLS = { "To'langan": "green", Kutilmoqda: "orange", Bekor: "red", Qaytarilgan: "gray" };

class Tranzaksiyalar {
	constructor(page) {
		this.page = page;
		this.state = { preset: "month", from: null, to: null, provider: "", status: "", q: "" };
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.make_filters();
		this.$body = $(`<div class="mp-tx"></div>`).appendTo(page.main);
		this.inject_style();
		this.apply_preset();
	}

	make_filters() {
		this.preset = this.page.add_field({
			fieldname: "preset", label: __("Davr"), fieldtype: "Select", default: "month",
			options: [
				{ value: "today", label: __("Bugun") }, { value: "yesterday", label: __("Kecha") },
				{ value: "7", label: __("Oxirgi 7 kun") }, { value: "month", label: __("Shu oy") },
				{ value: "prev_month", label: __("O'tgan oy") }, { value: "all", label: __("Hammasi") },
				{ value: "custom", label: __("Boshqa sanalar") },
			],
			change: () => {
				const v = this.preset.get_value();
				if (this._preset_silent || v === this.state.preset || v === "custom") return;
				this.state.preset = v;
				this.apply_preset();
				this.load();
			},
		});
		// Sana maydoni "change"ni kechikib chaqiradi: davr tanlovidan qo'yilgan qiymat bo'lsa — "Boshqa sanalar"ga o'tmaymiz
		const on_date = (key, field) => () => {
			const v = field.get_value() || null;
			if (v === (this.state[key] || null)) return;
			this.state[key] = v;
			this.set_custom();
		};
		this.from = this.page.add_field({ fieldname: "from", label: __("Dan"), fieldtype: "Date", change: () => on_date("from", this.from)() });
		this.to = this.page.add_field({ fieldname: "to", label: __("Gacha"), fieldtype: "Date", change: () => on_date("to", this.to)() });
		const select = (fieldname, label, options) => {
			const f = this.page.add_field({
				fieldname, label, fieldtype: "Select",
				options: options.map(([value, text]) => ({ value, label: text })),
				change: () => {
					const v = f.get_value() || "";
					if (v === this.state[fieldname]) return;
					this.state[fieldname] = v;
					this.load();
				},
			});
			return f;
		};
		this.provider = select("provider", __("Provayder"), [["", __("Barcha provayderlar")], ["Payme", "Payme"], ["Click", "Click"], ["Naqd", __("Naqd")]]);
		this.status = select("status", __("Holat"), [["", __("Barcha holatlar")], ["To'langan", __("To'langan")], ["Kutilmoqda", __("Kutilmoqda")], ["Bekor", __("Bekor")], ["Qaytarilgan", __("Qaytarilgan")]]);
		this.search = this.page.add_field({ fieldname: "q", label: __("To'lov ID, mijoz, telefon yoki tovar ID"), fieldtype: "Data",
			change: () => { this.state.q = this.search.get_value() || ""; this.load(); } });
	}

	set_custom() {
		if (this.state.preset !== "custom") {
			this.state.preset = "custom";
			this._preset_silent = true;
			this.preset.set_value("custom").then(() => (this._preset_silent = false));
		}
		this.load();
	}

	apply_preset() {
		const d = (x) => frappe.datetime.obj_to_str(x);
		const t = new Date();
		const shift = (n) => { const x = new Date(); x.setDate(x.getDate() + n); return x; };
		const ranges = {
			today: [d(t), d(t)], yesterday: [d(shift(-1)), d(shift(-1))], 7: [d(shift(-6)), d(t)],
			month: [d(new Date(t.getFullYear(), t.getMonth(), 1)), d(t)],
			prev_month: [d(new Date(t.getFullYear(), t.getMonth() - 1, 1)), d(new Date(t.getFullYear(), t.getMonth(), 0))],
			all: [null, null],
		};
		if (!(this.state.preset in ranges)) return;
		[this.state.from, this.state.to] = ranges[this.state.preset];
		this.from.set_value(this.state.from || "");
		this.to.set_value(this.state.to || "");
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-tx__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		this.data = await frappe.xcall("marketplace.kassa.transactions", {
			from_date: this.state.from, to_date: this.state.to, provider: this.state.provider || null,
			status: this.state.status || null, q: this.state.q || null,
		});
		if (this.data.need_shop) return this.render_need_shop();
		this.render();
	}

	// Admin do'kon panelida emas: do'konni Do'konlar panelida tanlaydi. To'liq yuklash — boshqa oynada
	// do'kon panelidan chiqilgan bo'lsa, eski menyu va tepadagi "do'koni paneli" qatori qolib ketmasin
	render_need_shop() {
		this.$body.html(`<div class="mp-tx__empty text-muted">
			<p>${__("Bu sahifa do‘kon uchun. Do‘konlar panelida do‘konni tanlab, «Do‘kon paneliga kirish» tugmasini bosing.")}</p>
			<button class="btn btn-default btn-sm">${__("Do‘konlar paneli")}</button></div>`);
		this.$body.find("button").on("click", () => (window.location.href = "/desk/shops-overview"));
	}

	money(x) {
		return `${format_number(x || 0, null, 0)} so‘m`;
	}

	render() {
		const esc = frappe.utils.escape_html;
		const { rows, totals, total, pending } = this.data;
		const card = (key, label, v) => `
			<button class="mp-tx__card ${this.state.provider === key ? "is-active" : ""}" data-provider="${key}">
				<span class="mp-tx__label">${label}</span>
				<b>${this.money(v.amount)}</b>
				<small>${v.count} ${__("ta to‘langan")}</small>
			</button>`;
		const body = rows.length
			? rows.map((r) => `
				<tr>
					<td class="nowrap">${esc(frappe.datetime.str_to_user(r.time))}</td>
					<td><code class="mp-tx__id" title="${__("Nusxalash")}" data-copy="${esc(r.id)}">${esc(r.id)}</code></td>
					<td><span class="indicator-pill ${MP_TX_PROVIDER_CLS[r.provider] || "gray"}">${esc(r.provider)}</span></td>
					<td><span class="indicator-pill ${MP_TX_STATUS_CLS[r.status] || "gray"}">${esc(__(r.status))}</span></td>
					<td><b>${esc(r.customer_name || "—")}</b></td>
					<td class="nowrap">${r.phone ? `<a href="tel:${esc(r.phone)}">${esc(r.phone)}</a>` : "—"}</td>
					<td>${r.products.length
						? `<button class="mp-tx__product" data-order="${esc(r.order)}" title="${__("Nima xarid qilgan")}">${esc(r.products[0])}</button>${
							r.products.length > 1 ? ` <span class="text-muted small">+${r.products.length - 1}</span>` : ""}`
						: "—"}</td>
					<td class="mp-tx__sum">${this.money(r.amount)}</td>
				</tr>`).join("")
			: `<tr><td colspan="8" class="mp-tx__empty text-muted">${__("Bu filtr bo‘yicha to‘lov yo‘q")}</td></tr>`;
		this.$body.html(`
			<div class="mp-tx__cards">
				${card("", __("Jami to‘langan"), total)}
				${card("Payme", "Payme", totals.Payme)}
				${card("Click", "Click", totals.Click)}
				${card("Naqd", __("Naqd"), totals.Naqd)}
			</div>
			${pending ? `<div class="mp-tx__pending">⏳ ${__("{0} ta to‘lov kutilmoqda", [pending])} —
				<a href="#" data-status="Kutilmoqda">${__("ko‘rish")}</a></div>` : ""}
			<div class="mp-tx__wrap"><table class="mp-tx__table">
				<thead><tr>
					<th>${__("Vaqt")}</th><th>${__("To‘lov ID")}</th><th>${__("Provayder")}</th><th>${__("Holat")}</th>
					<th>${__("Mijoz")}</th><th>${__("Telefon")}</th><th>${__("Tovar ID")}</th><th class="mp-tx__sum">${__("Summa")}</th>
				</tr></thead>
				<tbody>${body}</tbody>
			</table></div>`);
		this.$body.find("[data-provider]").on("click", (e) => {
			const p = e.currentTarget.dataset.provider;
			this.state.provider = this.state.provider === p ? "" : p;
			this.provider.set_value(this.state.provider);
			this.load();
		});
		this.$body.find("[data-status]").on("click", (e) => {
			e.preventDefault();
			this.state.status = "Kutilmoqda";
			this.status.set_value("Kutilmoqda");
			this.load();
		});
		this.$body.find("[data-copy]").on("click", (e) => {
			frappe.utils.copy_to_clipboard(e.currentTarget.dataset.copy);
		});
		this.$body.find("[data-order]").on("click", (e) => this.show_items(e.currentTarget.dataset.order));
	}

	// Tovar ID bosilganda: shu mijoz nima xarid qilgan
	async show_items(order) {
		const esc = frappe.utils.escape_html;
		const d = await frappe.xcall("marketplace.kassa.transaction_items", { order });
		const rows = d.items.map((i) => `
			<tr>
				<td class="mp-tx__pic">${i.image ? `<img src="${esc(i.image)}" alt="">` : ""}</td>
				<td><b>${esc(i.name)}</b>${i.variant ? `<div class="text-muted small">${esc(i.variant)}</div>` : ""}
					<div><code>${esc(i.product_id)}</code></div></td>
				<td class="mp-tx__sum">${format_number(i.qty, null, 0)}</td>
				<td class="mp-tx__sum">${this.money(i.rate)}</td>
				<td class="mp-tx__sum">${this.money(i.amount)}</td>
			</tr>`).join("");
		const dlg = new frappe.ui.Dialog({ title: __("{0} xarid qilgan", [d.customer_name || ""]), size: "large" });
		dlg.$body.html(`
			<div class="text-muted small" style="margin-bottom:10px">${esc(d.phone || "")} ·
				<a href="/desk/sales-order/${encodeURIComponent(d.order)}">${esc(d.order)}</a> · ${esc(frappe.datetime.str_to_user(d.date))}</div>
			<table class="mp-tx__table mp-tx__items">
				<thead><tr><th></th><th>${__("Tovar")}</th><th class="mp-tx__sum">${__("Soni")}</th><th class="mp-tx__sum">${__("Narxi")}</th><th class="mp-tx__sum">${__("Summa")}</th></tr></thead>
				<tbody>${rows}</tbody>
				<tfoot><tr><td colspan="4" class="mp-tx__sum">${__("Jami")}</td><td class="mp-tx__sum">${this.money(d.total)}</td></tr></tfoot>
			</table>`);
		dlg.show();
	}

	inject_style() {
		if (document.getElementById("mp-tx-style")) return;
		$(`<style id="mp-tx-style">
			.mp-tx { padding: 4px var(--padding-md, 15px) 40px; }
			.mp-tx__cards { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
			.mp-tx__card { display: grid; gap: 2px; text-align: left; padding: 12px 14px; border-radius: var(--border-radius-lg);
				border: 1px solid var(--border-color); background: var(--card-bg); cursor: pointer; }
			.mp-tx__card.is-active { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
			.mp-tx__card b { font-size: var(--text-xl); color: var(--heading-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-tx__label { font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: .04em; }
			.mp-tx__card small { color: var(--text-muted); }
			.mp-tx__pending { margin: -2px 0 12px; font-size: var(--text-sm); color: var(--orange-600, #ea580c); }
			.mp-tx__wrap { overflow-x: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-tx__table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
			.mp-tx__table th { color: var(--text-muted); font-weight: 600; text-align: left; padding: 9px 12px;
				border-bottom: 1px solid var(--border-color); white-space: nowrap; }
			.mp-tx__table td { padding: 9px 12px; border-top: 1px solid var(--border-color); vertical-align: middle; }
			.mp-tx__table .nowrap { white-space: nowrap; }
			.mp-tx__id { cursor: copy; font-size: var(--text-xs); white-space: nowrap; }
			.mp-tx__product { border: 1px solid var(--border-color); background: var(--subtle-fg); border-radius: 6px; padding: 2px 8px;
				font-family: var(--font-stack-monospace, monospace); font-size: var(--text-xs); color: var(--primary); cursor: pointer; white-space: nowrap; }
			.mp-tx__product:hover { border-color: var(--primary); }
			.mp-tx__sum { text-align: right !important; white-space: nowrap; font-weight: 600; }
			.mp-tx__empty { padding: 40px 10px; text-align: center; }
			.mp-tx__items .mp-tx__pic { width: 52px; }
			.mp-tx__items img { width: 44px; height: 44px; object-fit: cover; border-radius: 8px; }
			.mp-tx__items tfoot td { border-top: 2px solid var(--border-color); }
			@media (max-width: 760px) { .mp-tx__cards { grid-template-columns: 1fr 1fr; } }
		</style>`).appendTo(document.head);
	}
}
