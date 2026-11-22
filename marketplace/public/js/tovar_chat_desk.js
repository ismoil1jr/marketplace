// Sotuv paneli → «Tovar murojaatlari»: chapda mijozlar chatlari (har biri — bitta tovar bo'yicha), o'ngda chat
// (public/js/tovar_chat.js, MpChat). Server: marketplace/sotuv/tovar_chat.py (royxat, ochish, yuborish ...).
// Yangi xabar: Frappe realtime «mp_tovar_chat» — ochiq chat va ro'yxat darhol yangilanadi.
window.MpTovarPanel = class MpTovarPanel {
	constructor(sp) {
		this.sp = sp; // SotuvPaneli (sotuv_paneli.js)
		this.q = "";
	}

	async load() {
		const data = await frappe.xcall("marketplace.sotuv.tovar_chat.royxat", { q: this.q || null });
		if (data.need_shop) return this.sp.render_need_shop();
		this.data = data;
		if (!this.$root || !$.contains(document, this.$root[0])) this.render();
		else this.render_list();
		const want = this.sp.state.open;
		if (want && want !== this.current) this.open(want);
	}

	render() {
		this.chat?.destroy();
		this.chat = null;
		this.current = null;
		const d = this.data;
		this.sp.$body.html(`
			${this.sp.modes_html({ buyurtma: d.order_new, murojaat: d.lead_new, tovar: d.yangi })}
			<div class="mp-tc">
				<div class="mp-tc__side">
					<input class="form-control mp-tc__search" type="search" placeholder="${__("Mijoz, telefon yoki tovar…")}">
					<div class="mp-tc__list" data-tc-list></div>
				</div>
				<div class="mp-tc__main" data-tc-main>
					<div class="mp-tc__pick text-muted">${__("Chap tomondan chatni tanlang. Mijoz tovar sahifasida «Sotuvchi bilan bog‘lanish»ni bosib yozganda shu yerga tushadi.")}</div>
				</div>
			</div>`);
		this.$root = this.sp.$body.find(".mp-tc");
		this.fit();
		if (!this._resize) {
			this._resize = frappe.utils.debounce(() => this.fit(), 100);
			window.addEventListener("resize", this._resize);
		}
		this.sp.bind_modes();
		const $s = this.$root.find(".mp-tc__search").val(this.q);
		$s.on("input", frappe.utils.debounce(() => { this.q = $s.val(); this.load(); }, 300));
		this.$root.on("click", "[data-thread]", (e) => this.open(e.currentTarget.dataset.thread));
		this.render_list();
	}

	render_list() {
		const esc = frappe.utils.escape_html;
		const rows = this.data.rows || [];
		const $list = this.$root.find("[data-tc-list]");
		if (!rows.length) {
			$list.html(`<div class="mp-tc__none text-muted">${this.q ? __("Hech narsa topilmadi") : __("Hali tovar bo‘yicha murojaat yo‘q")}</div>`);
		} else {
			$list.html(rows.map((r) => `
				<button type="button" class="mp-tc__row ${r.unread ? "is-unread" : ""} ${r.name === this.current ? "is-open" : ""}" data-thread="${esc(r.name)}">
					${r.thumb ? `<img src="${esc(r.thumb)}" alt="" loading="lazy">` : `<span class="mp-tc__ph">💬</span>`}
					<span class="mp-tc__row-main">
						<b>${esc(r.mijoz_ismi || r.telefon || r.name)}</b>
						<small class="mp-tc__item">${esc(r.tovar_nomi || "")}</small>
						<small>${r.oxirgi_kimdan === "Sotuvchi" ? `${__("Siz")}: ` : ""}${esc(r.oxirgi_xabar || "")}</small>
					</span>
					<span class="mp-tc__row-side">
						<time>${this.when(r.oxirgi_vaqt)}</time>
						${r.unread ? `<span class="mp-tc__n">${r.unread}</span>` : ""}
					</span>
				</button>`).join(""));
		}
		// Rejim tugmasidagi «N yangi»
		this.sp.set_mode_badge("tovar", this.data.yangi);
	}

	// Panel ekranning qolgan qismiga sig'sin: tepada admin qatori / sarlavha bo'lsa ham javob yozish joyi ko'rinib tursin
	fit() {
		const el = this.$root && this.$root[0];
		if (!el || !el.isConnected) return;
		const top = el.getBoundingClientRect().top + window.scrollY;
		const h = Math.max(380, (window.visualViewport?.height || window.innerHeight) - top - 12);
		el.style.height = `${h}px`;
	}

	when(v) {
		if (!v) return "";
		const s = String(v);
		return s.slice(0, 10) === frappe.datetime.get_today() ? s.slice(11, 16) : frappe.datetime.str_to_user(s.slice(0, 10));
	}

	open(name) {
		if (this.current === name && this.chat) return;
		const r = (this.data.rows || []).find((x) => x.name === name) || {};
		const esc = frappe.utils.escape_html;
		this.chat?.destroy();
		this.current = name;
		this.sp.state.open = name;
		window.mp_tovar_open = name; // shu chat ochiq — umumiy ovozli xabar chiqmasin (seller_notify.js)
		this.$root.addClass("is-chat");
		this.fit();
		this.$root.find(".mp-tc__row").removeClass("is-open").filter(`[data-thread="${CSS.escape(name)}"]`).addClass("is-open");
		const $main = this.$root.find("[data-tc-main]").html(`
			<div class="mp-tc__head">
				<button type="button" class="btn btn-default btn-sm mp-tc__back" aria-label="${__("Ro‘yxatga qaytish")}">←</button>
				<div class="mp-tc__who">
					<b>${esc(r.mijoz_ismi || "")}</b>
					${r.telefon ? `<a href="tel:${esc(r.telefon)}">${esc(r.telefon)}</a>` : ""}
				</div>
				<a class="btn btn-default btn-sm" data-product target="_blank" rel="noopener" hidden>${__("Tovarni saytda ko‘rish")}</a>
			</div>
			<div class="mp-tc__chat"></div>`);
		$main.find(".mp-tc__back").on("click", () => {
			this.$root.removeClass("is-chat");
			this.chat?.destroy();
			this.chat = null;
			this.current = this.sp.state.open = window.mp_tovar_open = null;
			$main.html(`<div class="mp-tc__pick text-muted">${__("Chap tomondan chatni tanlang.")}</div>`);
		});
		const el = $main.find(".mp-tc__chat")[0];
		el.classList.add("mpc--desk");
		const call = (method, data, file) => MpChat.call(method, data, file, frappe.csrf_token);
		this.chat = new MpChat(el, {
			side: "Sotuvchi",
			poll: 15000, // asosiy yangilanish — realtime; bu faqat zaxira
			empty: __("Hali xabar yo‘q"),
			toast: (t) => frappe.show_alert({ message: t, indicator: "red" }),
			transport: {
				open: (since, read) => call("ochish", { name, since, oqidi: read }),
				send: (fields, file) => call("yuborish", Object.assign({ name }, fields), file),
				edit: (xabar, matn) => call("tahrirlash", { xabar, matn }),
				remove: (xabar) => call("ochirish", { xabar }),
			},
			onChange: (info) => {
				if (info && info.tovar && info.tovar.url) $main.find("[data-product]").attr("href", info.tovar.url).prop("hidden", false);
				if (info && info.mijoz) $main.find(".mp-tc__who b").text(info.mijoz);
				this.refresh_list_soon();
			},
		});
		this.chat.start();
	}

	// Ro'yxatdagi o'qilmagan sonlar va oxirgi xabar — tez-tez chaqirilsa ham bitta so'rov
	refresh_list_soon() {
		clearTimeout(this._t);
		this._t = setTimeout(async () => {
			const data = await frappe.xcall("marketplace.sotuv.tovar_chat.royxat", { q: this.q || null });
			if (data.need_shop || !this.$root || !$.contains(document, this.$root[0])) return;
			this.data = data;
			this.render_list();
		}, 400);
	}

	on_realtime(data) {
		if (data.thread && data.thread === this.current) this.chat?.poll();
		this.refresh_list_soon();
	}

	destroy() {
		if (this._resize) window.removeEventListener("resize", this._resize);
		this._resize = null;
		this.chat?.destroy();
		this.chat = null;
		this.current = null;
		this.$root = null;
		window.mp_tovar_open = null;
	}
};

// Panel uslubi (chatning o'zi — tovar_chat.css)
$(`<style id="mp-tc-style">
	.mp-tc { display: grid; grid-template-columns: minmax(260px, 340px) 1fr; grid-template-rows: minmax(0, 1fr); height: calc(100vh - 210px); min-height: 380px;
		border: 1px solid var(--border-color); border-radius: var(--border-radius-lg, 12px); overflow: hidden; background: var(--card-bg); }
	.mp-tc__side { display: flex; flex-direction: column; min-height: 0; overflow: hidden; border-right: 1px solid var(--border-color); }
	.mp-tc__search { margin: 10px; width: auto; }
	.mp-tc__list { flex: 1; overflow-y: auto; }
	.mp-tc__none { padding: 24px 16px; text-align: center; }
	.mp-tc__row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border: 0; border-top: 1px solid var(--border-color);
		background: none; text-align: left; color: var(--text-color); }
	.mp-tc__row:hover { background: var(--subtle-fg); }
	.mp-tc__row.is-open { background: var(--control-bg); box-shadow: inset 3px 0 0 var(--primary); }
	.mp-tc__row img, .mp-tc__ph { width: 44px; height: 44px; flex: none; border-radius: 10px; object-fit: cover; background: var(--subtle-fg);
		display: grid; place-items: center; }
	.mp-tc__row-main { display: grid; flex: 1; min-width: 0; gap: 1px; }
	.mp-tc__row-main > * { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.mp-tc__row-main small { color: var(--text-muted); }
	.mp-tc__item { color: var(--text-color) !important; font-weight: 500; }
	.mp-tc__row.is-unread .mp-tc__row-main small:last-child { color: var(--text-color); font-weight: 600; }
	.mp-tc__row-side { display: grid; justify-items: end; gap: 4px; flex: none; }
	.mp-tc__row-side time { font-size: 11px; color: var(--text-muted); }
	.mp-tc__n { min-width: 20px; height: 20px; padding: 0 6px; border-radius: 10px; background: var(--primary); color: #fff;
		font-size: 11px; font-weight: 700; line-height: 20px; text-align: center; }
	.mp-tc__main { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; }
	.mp-tc__pick { margin: auto; max-width: 340px; padding: 20px; text-align: center; }
	.mp-tc__head { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border-color); }
	.mp-tc__who { display: grid; flex: 1; min-width: 0; }
	.mp-tc__who a { font-size: var(--text-sm); }
	.mp-tc__back { display: none; }
	.mp-tc__chat { flex: 1; min-height: 0; }
	@media (max-width: 767px) {
		.mp-tc { grid-template-columns: 1fr; }
		.mp-tc.is-chat .mp-tc__side, .mp-tc:not(.is-chat) .mp-tc__main { display: none; }
		.mp-tc__side { border-right: 0; }
		.mp-tc__back { display: inline-block; }
	}
</style>`).appendTo(document.head);
