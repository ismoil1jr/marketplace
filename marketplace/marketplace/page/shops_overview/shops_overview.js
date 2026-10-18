// Do'konlar paneli: barcha mijoz do'konlari, ularning sayti (jonli ko'rinish) va asosiy ko'rsatkichlar.

frappe.pages["shops-overview"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Do'konlar paneli"),
		single_column: true,
	});
	wrapper.overview = new ShopsOverview(page);
};

frappe.pages["shops-overview"].on_page_show = function (wrapper) {
	wrapper.overview?.load();
};

class ShopsOverview {
	constructor(page) {
		this.page = page;
		this.state = { q: "", status: "" };
		this.page.set_primary_action(__("Yangi do'kon"), () => frappe.new_doc("Shop"), "add");
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-ov"></div>`).appendTo(page.main);
		this.inject_style();
	}

	async load() {
		this.$body.html(`<div class="mp-ov__loading text-muted">${__("Yuklanmoqda…")}</div>`);
		const { message } = await frappe.call("marketplace.admin.get_shops_overview");
		this.data = message;
		this.render();
	}

	render() {
		const { shops, totals } = this.data;
		const esc = frappe.utils.escape_html;
		// UZS uchun Frappe "лв" belgisini ko'rsatadi — o'zimiz formatlaymiz
		const fmt = (n) => `${format_number(n, null, 0)} so‘m`;

		const stat = (label, value, hint = "") => `
			<div class="mp-stat">
				<div class="mp-stat__label">${label}</div>
				<div class="mp-stat__value">${value}</div>
				${hint ? `<div class="mp-stat__hint">${hint}</div>` : ""}
			</div>`;

		this.$body.html(`
			<div class="mp-stats">
				${stat(__("Do'konlar"), totals.shops || 0, `${totals.active || 0} ${__("ta faol")}`)}
				${stat(__("Saytdagi tovarlar"), totals.items || 0)}
				${stat(__("Buyurtmalar (7 kun)"), totals.orders_week || 0)}
				${stat(__("Shablonlar"), "A · B · C", __("Vitrina · Instagram · Katalog"))}
			</div>
			<div class="mp-toolbar">
				<input class="form-control mp-search" type="search" placeholder="${__("Do'kon nomi yoki slug…")}" value="${esc(this.state.q)}">
				<div class="mp-seg">
					${["", "Active", "Draft", "Suspended"]
						.map((s) => `<button class="${this.state.status === s ? "is-active" : ""}" data-status="${s}">${s ? __(s) : __("Hammasi")}</button>`)
						.join("")}
				</div>
			</div>
			<div class="mp-grid"></div>
		`);

		const filtered = shops.filter(
			(s) =>
				(!this.state.status || s.status === this.state.status) &&
				(!this.state.q || `${s.shop_name} ${s.name}`.toLowerCase().includes(this.state.q.toLowerCase()))
		);

		const $grid = this.$body.find(".mp-grid");
		if (!filtered.length) {
			$grid.html(`<div class="mp-empty text-muted">${shops.length ? __("Mos do'kon topilmadi") : __("Hali do'kon yo'q. «Yangi do'kon» tugmasini bosing.")}</div>`);
		}

		for (const s of filtered) {
			const color = s.brand_color || "#1F5C4A";
			const statusCls = { Active: "green", Draft: "orange", Suspended: "red" }[s.status] || "gray";
			const site = `${location.origin}${s.url}`;
			const card = $(`
				<div class="mp-card">
					<div class="mp-card__preview">
						<div class="mp-phone">
							<iframe data-src="${s.url}" title="${esc(s.shop_name)}" loading="lazy" tabindex="-1"></iframe>
						</div>
						${s.status !== "Active" ? `<div class="mp-card__veil">${__("Mijozlarga yopiq")}</div>` : ""}
					</div>
					<div class="mp-card__info">
						<div class="mp-card__head">
							<span class="mp-avatar" style="background:${esc(color)}">${s.logo ? `<img src="${esc(s.logo)}" alt="">` : esc(s.initials)}</span>
							<div class="mp-card__title">
								<a href="/desk/shop/${encodeURIComponent(s.name)}" class="mp-card__name">${esc(s.shop_name)}</a>
								<div class="text-muted small">${esc([s.city, s.instagram && "@" + s.instagram.replace(/^@/, "")].filter(Boolean).join(" · "))}</div>
							</div>
							<span class="indicator-pill ${statusCls}">${__(s.status)}</span>
						</div>
						<a class="mp-url" href="${esc(site)}" target="_blank" rel="noopener">${esc(site.replace(/^https?:\/\//, ""))}</a>
						<div class="mp-kpis">
							<div><b>${s.items}</b><span>${__("tovar")}</span></div>
							<div><b>${s.orders_week}</b><span>${__("buyurtma, 7 kun")}</span></div>
							<div><b>${fmt(s.revenue)}</b><span>${__("to'langan")}</span></div>
						</div>
						<div class="mp-tags">
							${s.payments.map((p) => `<span class="mp-tag">${esc(p)}</span>`).join("")}
							<span class="mp-tag mp-tag--muted">${__("Shablon")}: ${esc(s.layout_style || "vitrina")}</span>
							<span class="mp-tag mp-tag--muted">${s.members.length} ${__("a'zo")}</span>
						</div>
						<div class="mp-layouts">
							<span class="text-muted small">${__("Ko'rib chiqish")}:</span>
							<a href="${s.url}?layout=vitrina" target="_blank" rel="noopener">A ${__("Vitrina")}</a>
							<a href="${s.url}?layout=story" target="_blank" rel="noopener">B ${__("Instagram")}</a>
							<a href="${s.url}?layout=katalog" target="_blank" rel="noopener">C ${__("Katalog")}</a>
						</div>
						<div class="mp-actions">
							<button class="btn btn-primary btn-sm" data-act="enter">${frappe.utils.icon("log-in", "xs")} ${__("Do'kon paneliga kirish")}</button>
							<a class="btn btn-default btn-sm" href="${esc(site)}" target="_blank" rel="noopener">${frappe.utils.icon("external-link", "xs")} ${__("Saytni ochish")}</a>
							<button class="btn btn-default btn-sm" data-act="copy">${frappe.utils.icon("copy", "xs")} ${__("Havola")}</button>
							<a class="btn btn-default btn-sm" href="/desk/item?shop=${encodeURIComponent(s.name)}">${__("Tovarlar")}</a>
							<a class="btn btn-default btn-sm" href="/desk/sales-order?shop=${encodeURIComponent(s.name)}">${__("Buyurtmalar")}</a>
							<a class="btn btn-default btn-sm" href="/desk/shop/${encodeURIComponent(s.name)}">${__("Sozlamalar")}</a>
						</div>
					</div>
				</div>
			`).appendTo($grid);

			card.find("[data-act=enter]").on("click", () => marketplace_enter_shop(s.name));
			card.find("[data-act=copy]").on("click", () => {
				frappe.utils.copy_to_clipboard(site);
			});
		}

		this.lazy_previews($grid);
		this.bind_toolbar();
	}

	// Jonli ko'rinishlar faqat ekranga chiqqanda yuklanadi: 1000 ta do'konda ham sahifa sekinlashmaydi
	lazy_previews($grid) {
		const io = new IntersectionObserver(
			(entries) => {
				for (const e of entries) {
					if (!e.isIntersecting) continue;
					e.target.src = e.target.dataset.src;
					io.unobserve(e.target);
				}
			},
			{ rootMargin: "200px" }
		);
		$grid.find("iframe[data-src]").each((_, el) => io.observe(el));
	}

	bind_toolbar() {
		const $search = this.$body.find(".mp-search");
		$search.on(
			"input",
			frappe.utils.debounce(() => {
				this.state.q = $search.val();
				this.render();
				this.$body.find(".mp-search").trigger("focus").get(0).setSelectionRange(9999, 9999);
			}, 250)
		);
		this.$body.find("[data-status]").on("click", (e) => {
			this.state.status = e.currentTarget.dataset.status;
			this.render();
		});
	}

	inject_style() {
		if (document.getElementById("mp-ov-style")) return;
		$(`<style id="mp-ov-style">
			.mp-ov { padding: 4px 0 40px; }
			.mp-ov__loading, .mp-empty { padding: 60px 0; text-align: center; }
			.mp-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 18px; }
			.mp-stat { padding: 16px 18px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-stat__label { color: var(--text-muted); font-size: var(--text-sm); }
			.mp-stat__value { margin-top: 4px; font-size: 26px; font-weight: 600; color: var(--heading-color); }
			.mp-stat__hint { color: var(--text-muted); font-size: var(--text-xs); }
			.mp-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 16px; }
			.mp-search { max-width: 320px; }
			.mp-seg { display: inline-flex; padding: 3px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-seg button { border: 0; background: none; padding: 5px 12px; border-radius: var(--border-radius-sm); font-size: var(--text-sm); color: var(--text-muted); }
			.mp-seg button.is-active { background: var(--card-bg); color: var(--text-color); box-shadow: var(--shadow-sm); }
			.mp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(520px, 1fr)); gap: 16px; }
			@media (max-width: 640px) { .mp-grid { grid-template-columns: 1fr; } }
			.mp-card { display: grid; grid-template-columns: 200px 1fr; overflow: hidden; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			@media (max-width: 640px) { .mp-card { grid-template-columns: 1fr; } }
			.mp-card__preview { position: relative; display: grid; place-items: center; padding: 14px; background: var(--subtle-fg); }
			.mp-phone { width: 172px; height: 344px; overflow: hidden; border: 6px solid #1b1b1a; border-radius: 26px; background: #fff; }
			.mp-phone iframe { width: 390px; height: 780px; border: 0; transform: scale(.4103); transform-origin: 0 0; pointer-events: none; }
			.mp-card__veil { position: absolute; inset: 0; display: grid; place-items: center; background: rgb(0 0 0 / .45); color: #fff; font-weight: 600; }
			.mp-card__info { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; min-width: 0; }
			.mp-card__head { display: flex; align-items: center; gap: 12px; }
			.mp-card__title { flex: 1; min-width: 0; }
			.mp-card__name { font-size: var(--text-lg); font-weight: 600; color: var(--heading-color); }
			.mp-avatar { display: grid; place-items: center; flex: none; width: 44px; height: 44px; overflow: hidden; border-radius: 50%; color: #fff; font-weight: 700; }
			.mp-avatar img { width: 100%; height: 100%; object-fit: cover; }
			.mp-url { font-size: var(--text-sm); color: var(--text-muted); word-break: break-all; }
			.mp-url:hover { color: var(--primary); }
			.mp-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
			.mp-kpis > div { padding: 10px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-kpis b { display: block; font-size: var(--text-lg); color: var(--heading-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.mp-kpis span { color: var(--text-muted); font-size: var(--text-xs); }
			.mp-tags { display: flex; flex-wrap: wrap; gap: 6px; }
			.mp-tag { padding: 2px 8px; border-radius: 10px; background: var(--bg-green); color: var(--text-on-green); font-size: var(--text-xs); }
			.mp-tag--muted { background: var(--subtle-fg); color: var(--text-muted); }
			.mp-layouts { display: flex; gap: 12px; align-items: center; font-size: var(--text-sm); }
			.mp-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
		</style>`).appendTo(document.head);
	}
}
