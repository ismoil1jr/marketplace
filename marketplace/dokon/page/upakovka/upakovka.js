// Upakovka: menejer tasdiqlagan buyurtmalarni kuryer kelguncha yig'ib, qadoqlab qo'yish (upakovka.py).
// Ro'yxat: mijoz, nima tayyorlash kerak (nomi × soni), kuryer/olib ketadi, tasdiqlangan vaqti.
// Bosilganda — tovarlar rasmlari (mijoz olgan rangda), rang/o'lcham, soni; "📦 Upakovka qilindi" tugmasi.

frappe.pages["upakovka"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Upakovka"), single_column: true });
	wrapper.upakovka = new Upakovka(page);
};

frappe.pages["upakovka"].on_page_show = function (wrapper) {
	wrapper.upakovka?.load();
};

class Upakovka {
	constructor(page) {
		this.page = page;
		this.tab = "todo";
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-up"></div>`).appendTo(page.main);
		this.inject_style();
		// Menejer "Oladi" degan zahoti ro'yxat yangilanadi (seller_desk._notify_users → marketplace_new_order)
		frappe.realtime.on("marketplace_new_order", () => this.load());
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-up__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		this.data = await frappe.xcall("marketplace.upakovka.orders", { tab: this.tab });
		this.render();
	}

	when(s) {
		return s ? frappe.datetime.str_to_user(s) : "";
	}

	method(o) {
		return o.delivery_method === "Kuryer"
			? `🚚 ${__("Kuryer")}${o.courier ? ` · ${frappe.utils.escape_html(o.courier)}` : ""}`
			: `🏬 ${__("Mijoz o‘zi olib ketadi")}`;
	}

	row(o) {
		const esc = frappe.utils.escape_html;
		return `
			<div class="mp-up__row ${o.packed ? "is-done" : ""}" data-order="${esc(o.name)}" role="button" tabindex="0">
				<div class="mp-up__main">
					<b>${esc(o.customer_name || "—")}</b>
					<small>${esc(o.name)} · ${this.method(o)}</small>
					<div class="mp-up__lines">${o.lines.map((l) => `<span>${esc(l)}</span>`).join("")}</div>
				</div>
				<div class="mp-up__side">
					<b>${format_number(o.qty, null, 0)} ${__("dona")}</b>
					${o.packed
						? `<span class="indicator-pill green">📦 ${__("Tayyor")}</span><small>${esc(this.when(o.packed_at))}${o.packer ? ` · ${esc(o.packer)}` : ""}</small>${o.delivered ? `<small>✅ ${__("topshirilgan")}</small>` : ""}`
						: `<span class="indicator-pill orange">⏳ ${__("Tayyorlash kerak")}</span><small>${__("tasdiqlandi")}: ${esc(this.when(o.confirmed_at))}</small>`}
				</div>
			</div>`;
	}

	render() {
		const d = this.data;
		const esc = frappe.utils.escape_html;
		const tab = (key, label) =>
			`<button class="btn btn-sm ${this.tab === key ? "btn-primary" : "btn-default"}" data-tab="${key}">${label} · ${d.counts[key]}</button>`;
		const empty = this.tab === "done" ? __("Hali upakovka qilingan buyurtma yo‘q") : __("Tayyorlanadigan buyurtma yo‘q — menejer tasdiqlagani shu yerga tushadi");
		this.$body.html(`
			<div class="mp-up__tabs">${tab("todo", __("Tayyorlash kerak"))}${tab("done", __("Tayyorlanganlar"))}<span class="mp-up__shop text-muted">${esc(d.shop_name || "")}</span></div>
			${d.rows.length ? `<div class="mp-up__list">${d.rows.map((o) => this.row(o)).join("")}</div>` : `<div class="mp-up__empty text-muted">${empty}</div>`}
		`);
		this.$body.find("[data-tab]").on("click", (e) => {
			this.tab = $(e.currentTarget).attr("data-tab");
			this.load();
		});
		this.$body.find(".mp-up__row").on("click keydown", (e) => {
			if (e.type === "keydown" && e.key !== "Enter") return;
			this.open($(e.currentTarget).attr("data-order"));
		});
	}

	async open(name) {
		const o = await frappe.xcall("marketplace.upakovka.order", { name });
		const esc = frappe.utils.escape_html;
		const dialog = new frappe.ui.Dialog({ title: `${esc(o.customer_name || o.name)} · ${format_number(o.qty, null, 0)} ${__("dona")}`, size: "large" });
		dialog.$body.html(`
			<div class="mp-up-d">
				<div class="mp-up-d__who">
					<div><b>${esc(o.customer_name || "—")}</b>${o.phone ? ` · <a href="tel:${esc(o.phone)}">${esc(o.phone)}</a>` : ""}</div>
					<div class="mp-up-d__meta">${esc(o.name)} · ${this.method(o)}</div>
					${o.address ? `<div class="mp-up-d__addr">📍 ${esc(o.address)}</div>` : ""}
					<button type="button" class="btn btn-default btn-xs mp-up-d__print" data-print>🖨 ${__("Yorliq chop etish (5×3 sm)")}</button>
				</div>
				${o.packed ? `<div class="mp-up-d__done">📦 ${__("Upakovka qilingan")}: ${esc(this.when(o.packed_at))}${o.packer ? ` · ${esc(o.packer)}` : ""}</div>` : ""}
				<div class="mp-up-d__items">${o.items.map((i, n) => `
					<div class="mp-up-d__item">
						<div class="mp-up-d__pics">${i.images.length
							? i.images.map((p, k) => `<img src="${esc(p.src)}" alt="" loading="lazy" data-img="${n}:${k}">`).join("")
							: `<div class="mp-up-d__noimg">${frappe.utils.icon("image", "lg")}</div>`}</div>
						<div class="mp-up-d__info">
							<b>${esc(i.name)}</b>
							${i.variant ? `<span class="mp-up-d__var">${esc(i.variant)}</span>` : ""}
							<div class="mp-up-d__qty">${format_number(i.qty, null, 0)} <small>${__("dona")}</small></div>
						</div>
					</div>`).join("")}</div>
			</div>`);
		this.bind_images(dialog, o);
		dialog.$body.find("[data-print]").on("click", () => this.print_label(o));
		// Nazoratchi (Shop Member «Nazoratchi») faqat ko'radi — tugmalar yo'q
		if (frappe.boot.marketplace_shop?.supervisor) {
			// faqat ko'rish
		} else if (!o.packed && !o.delivered) {
			if (!o.confirmed) {
				dialog.$body.append(`<div class="mp-up-d__wait">${__("Menejer hali mijoz bilan gaplashib tasdiqlamagan")}</div>`);
			} else {
				dialog.set_primary_action(`📦 ${__("Upakovka qilindi")}`, () =>
					frappe.confirm(__("Buyurtma to‘liq yig‘ildi va qadoqlandimi? ({0} dona)", [format_number(o.qty, null, 0)]), async () => {
						await frappe.xcall("marketplace.upakovka.mark_packed", { name: o.name });
						frappe.show_alert({ message: __("Tayyor — kuryerga xabar ketdi"), indicator: "green" });
						dialog.hide();
						this.load();
					})
				);
			}
		} else if (o.packed && !o.delivered) {
			dialog.set_secondary_action_label(__("Adashib bosildi — qaytarish"));
			dialog.set_secondary_action(async () => {
				await frappe.xcall("marketplace.upakovka.unpack", { name: o.name });
				dialog.hide();
				this.load();
			});
		}
		dialog.show();
	}

	// Ixtiyoriy: 50×30 mm yorliq (Uzum'dagidek) — buyurtma ID, mijoz, telefon, manzil, tovarlar × soni.
	// Upakovkachi uni qutiga yopishtiradi, kuryer buyurtmani tez topadi. Yorliq printeri bo'lmasa, oddiy A4 ga ham chiqadi.
	print_label(o) {
		const esc = frappe.utils.escape_html;
		const items = o.items.map((i) => `${esc(i.name)}${i.variant ? ` (${esc(i.variant)})` : ""} × ${format_number(i.qty, null, 0)}`).join(", ");
		const html = `<!doctype html><html><head><meta charset="utf-8"><title>${esc(o.name)}</title>
			<style>
				@page { size: 50mm 30mm; margin: 2mm; }
				html, body { margin: 0; padding: 0; }
				body { width: 46mm; font: 7pt/1.25 Arial, Helvetica, sans-serif; color: #000; }
				.id { font-size: 10pt; font-weight: 700; letter-spacing: .02em; margin-bottom: 1mm; }
				.who { font-weight: 700; }
				.addr, .items { overflow: hidden; display: -webkit-box; -webkit-box-orient: vertical; }
				.addr { -webkit-line-clamp: 2; }
				.items { -webkit-line-clamp: 2; margin-top: 1mm; font-size: 6.5pt; }
				.shop { margin-top: 1mm; font-size: 6pt; color: #333; }
			</style></head><body>
			<div class="id">${esc(o.name)}</div>
			<div class="who">${esc(o.customer_name || "")}${o.phone ? ` · ${esc(o.phone)}` : ""}</div>
			<div class="addr">${esc(o.delivery_method === "Kuryer" ? (o.address || "") : __("Mijoz o‘zi olib ketadi"))}</div>
			<div class="items">${items}</div>
			<div class="shop">${esc(this.data.shop_name || "")} · ${format_number(o.qty, null, 0)} ${__("dona")}</div>
			<script>window.onload = () => { window.print(); setTimeout(() => window.close(), 500); };</script>
			</body></html>`;
		const w = window.open("", "_blank", "width=420,height=320");
		if (!w) return frappe.show_alert({ message: __("Brauzer yangi oynani bloklagan — ruxsat bering"), indicator: "orange" });
		w.document.open();
		w.document.write(html);
		w.document.close();
	}

	// Rasm bosilganda — katta ko'rinish (kuryer sahifasidagi bilan bir xil)
	bind_images(dialog, o) {
		dialog.$body.find("[data-img]").on("click", (e) => {
			const [n, k] = e.currentTarget.dataset.img.split(":").map(Number);
			const pics = o.items[n].images.map((p) => p.full || p.src);
			let at = k;
			const $v = $(`
				<div class="mp-up-view" role="dialog" aria-label="${__("Rasm")}">
					<img alt="">
					${pics.length > 1 ? `<button class="mp-up-view__nav" data-step="-1" aria-label="${__("Oldingi")}">‹</button>
						<button class="mp-up-view__nav mp-up-view__nav--next" data-step="1" aria-label="${__("Keyingi")}">›</button>` : ""}
					<button class="mp-up-view__close" aria-label="${__("Yopish")}">✕</button>
				</div>`).appendTo(document.body);
			const show = () => $v.find("img").attr("src", pics[at]);
			const on_key = (ev) => { if (ev.key !== "Escape") return; ev.stopPropagation(); ev.preventDefault(); close(); };
			const close = () => { $v.remove(); document.removeEventListener("keydown", on_key, true); };
			show();
			$v.on("click", (ev) => {
				const step = $(ev.target).closest("[data-step]").attr("data-step");
				if (step) { at = (at + Number(step) + pics.length) % pics.length; return show(); }
				close();
			});
			document.addEventListener("keydown", on_key, true);
		});
	}

	inject_style() {
		if (document.getElementById("mp-up-style")) return;
		$(`<style id="mp-up-style">
			.mp-up { max-width: 900px; margin: 0 auto; padding: 8px var(--padding-md, 15px) 40px; }
			.mp-up__empty { padding: 60px 0; text-align: center; }
			.mp-up__tabs { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
			.mp-up__shop { margin-left: auto; font-size: var(--text-sm); }
			.mp-up__list { display: grid; gap: 10px; }
			.mp-up__row { display: grid; grid-template-columns: 1fr auto; gap: 8px 16px; padding: 12px 14px; cursor: pointer;
				border: 1px solid var(--border-color); border-left: 4px solid var(--orange-500, #f97316); border-radius: var(--border-radius-lg); background: var(--card-bg); color: var(--text-color); }
			.mp-up__row.is-done { border-left-color: var(--green-500, #22c55e); }
			.mp-up__row:hover, .mp-up__row:focus-visible { background: var(--subtle-fg); outline: none; }
			.mp-up__main { display: grid; gap: 2px; min-width: 0; }
			.mp-up__main > b { font-size: var(--text-lg); }
			.mp-up__main small { color: var(--text-muted); }
			.mp-up__lines { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
			.mp-up__lines span { padding: 3px 10px; border-radius: 999px; background: var(--subtle-fg); font-size: var(--text-sm); font-weight: 600; }
			.mp-up__side { display: grid; justify-items: end; align-content: start; gap: 4px; text-align: right; white-space: nowrap; }
			.mp-up__side > b { font-size: var(--text-lg); font-variant-numeric: tabular-nums; }
			.mp-up__side small { color: var(--text-muted); }
			@media (max-width: 560px) { .mp-up__row { grid-template-columns: 1fr; } .mp-up__side { justify-items: start; text-align: left; } }

			.mp-up-d__who { display: grid; gap: 3px; margin-bottom: 12px; padding: 10px 12px; border-radius: var(--border-radius-lg); background: var(--subtle-fg); }
			.mp-up-d__who > div:first-child { font-size: var(--text-lg); }
			.mp-up-d__meta { color: var(--text-muted); font-size: var(--text-sm); }
			.mp-up-d__addr { font-weight: 600; }
			.mp-up-d__print { justify-self: start; margin-top: 4px; }
			.mp-up-d__done { margin-bottom: 10px; padding: 8px 12px; border-radius: var(--border-radius-lg); background: var(--bg-green, #f0fdf4); color: var(--green-700, #15803d); font-weight: 600; }
			.mp-up-d__items { display: grid; gap: 10px; }
			.mp-up-d__item { display: grid; grid-template-columns: auto 1fr; gap: 16px; padding: 10px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-up-d__pics { display: flex; gap: 6px; max-width: 332px; overflow-x: auto; }
			.mp-up-d__pics img { width: 160px; height: 200px; flex: none; object-fit: cover; border-radius: var(--border-radius); background: var(--subtle-fg); cursor: zoom-in; }
			.mp-up-d__noimg { width: 160px; height: 200px; display: grid; place-items: center; border-radius: var(--border-radius); background: var(--subtle-fg); color: var(--text-muted); }
			.mp-up-d__info { display: grid; align-content: start; gap: 6px; min-width: 0; }
			.mp-up-d__info > b { font-size: var(--text-lg); line-height: 1.3; }
			.mp-up-d__var { justify-self: start; padding: 2px 10px; border-radius: 999px; background: var(--subtle-fg); font-size: var(--text-sm); }
			.mp-up-d__qty { font-size: 28px; font-weight: 700; color: var(--heading-color); line-height: 1.1; }
			.mp-up-d__qty small { font-size: var(--text-md); font-weight: 500; color: var(--text-muted); }
			.mp-up-d__wait { margin-top: 12px; padding: 10px 12px; border-radius: var(--border-radius-lg); background: var(--subtle-fg); color: var(--text-muted); font-weight: 600; }
			@media (max-width: 560px) { .mp-up-d__item { grid-template-columns: 1fr; } .mp-up-d__pics img, .mp-up-d__noimg { width: 70vw; max-width: 260px; height: 300px; } }

			.mp-up-view { position: fixed; inset: 0; z-index: 2000; display: grid; place-items: center; background: rgba(0,0,0,.92); }
			.mp-up-view img { max-width: 100vw; max-height: 100vh; object-fit: contain; }
			.mp-up-view button { position: absolute; border: 0; background: rgba(255,255,255,.14); color: #fff; border-radius: 999px; width: 44px; height: 44px; font-size: 22px; line-height: 1; }
			.mp-up-view__close { top: 14px; right: 14px; }
			.mp-up-view__nav { top: 50%; left: 12px; transform: translateY(-50%); font-size: 30px; }
			.mp-up-view__nav--next { left: auto; right: 12px; }
		</style>`).appendTo(document.head);
	}
}
