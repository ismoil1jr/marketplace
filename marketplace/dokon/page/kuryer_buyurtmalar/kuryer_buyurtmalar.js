// Kuryer: yetkaziladigan buyurtmalar (kuryer.py). Mijoz bosilganda — nima olgani rasmlari bilan, nechtadan va manzili;
// manzil bosilganda Google Maps yoki Yandex Maps tanlanadi va o'sha xaritada yo'l ko'rsatiladi.

frappe.pages["kuryer-buyurtmalar"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Yetkaziladigan buyurtmalar"), single_column: true });
	wrapper.deliveries = new KuryerBuyurtmalar(page);
};

frappe.pages["kuryer-buyurtmalar"].on_page_show = function (wrapper) {
	wrapper.deliveries?.load();
};

const MP_PAY_COLOR = { "To'langan": "green", Kutilmoqda: "orange", Bekor: "red" };

// Chiziqli ikonkalar (lucide): telefon, manzil, doimiy mijoz
const MP_KB_ICONS = {
	phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
	pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
	user_plus: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
	user_check: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m16 11 2 2 4-4"/>',
};
const mp_kb_icon = (name) =>
	`<svg class="mp-kb__ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${MP_KB_ICONS[name]}</svg>`;

class KuryerBuyurtmalar {
	constructor(page) {
		this.page = page;
		this.tab = "active";
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-kb"></div>`).appendTo(page.main);
		this.inject_style();
		frappe.realtime.on("marketplace_new_order", () => this.load());
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-kb__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		this.data = await frappe.xcall("marketplace.kuryer.deliveries", { tab: this.tab });
		this.render();
	}

	money(x) {
		return `${format_number(x || 0, null, 0)} so‘m`;
	}

	// +998998011026 -> +998 99 801 10 26
	phone(value) {
		const d = (value || "").replace(/\D/g, "");
		if (d.length !== 12) return value || "";
		return `+${d.slice(0, 3)} ${d.slice(3, 5)} ${d.slice(5, 8)} ${d.slice(8, 10)} ${d.slice(10, 12)}`;
	}

	pill(text, color) {
		return `<span class="indicator-pill ${color} mp-kb__pill">${frappe.utils.escape_html(text)}</span>`;
	}

	pay(o) {
		const esc = frappe.utils.escape_html;
		const cash_todo = o.payment_method === "Naqd" && o.payment_status === "Kutilmoqda";
		return `${this.pill(o.payment_status || "—", MP_PAY_COLOR[o.payment_status] || "gray")}
			<small>${esc(o.payment_method || "")}${cash_todo ? ` · ${__("pulni oling")}` : ""}${o.cash_in_hand ? ` · ${__("naqd sizda")}` : ""}</small>`;
	}

	row(o) {
		const esc = frappe.utils.escape_html;
		return `
			<div class="mp-kb__row" data-order="${esc(o.name)}" role="button" tabindex="0">
				<div class="mp-kb__c mp-kb__cust"><b>${esc(o.customer_name || "—")}</b><small>${esc(o.name)}${o.loyal ? ` · ${__("doimiy mijoz")}` : ""}</small></div>
				<div class="mp-kb__c mp-kb__phone">${o.phone ? `<a href="tel:${esc(o.phone)}" data-tel>${mp_kb_icon("phone")}${esc(this.phone(o.phone))}</a>` : "—"}</div>
				<div class="mp-kb__c" data-label="${__("Holat")}">${this.pill(o.state, o.state_color)}</div>
				<div class="mp-kb__c mp-kb__shop" data-label="${__("Do‘kon")}">${esc(o.shop_name || "")}</div>
				<div class="mp-kb__c mp-kb__pay" data-label="${__("To‘lov")}">${this.pay(o)}</div>
				<div class="mp-kb__c mp-kb__sum">${this.money(o.amount)}</div>
			</div>`;
	}

	render() {
		const d = this.data;
		const tab = (key, label) =>
			`<button class="btn btn-sm ${this.tab === key ? "btn-primary" : "btn-default"}" data-tab="${key}">${label} · ${d.counts[key]}</button>`;
		const empty = this.tab === "done" ? __("Hali topshirilgan buyurtma yo‘q") : __("Yetkaziladigan buyurtma yo‘q");
		this.$body.html(`
			<div class="mp-kb__tabs">${tab("active", __("Yetkazilishi kerak"))}${tab("done", __("Topshirilganlar"))}</div>
			${d.rows.length ? `
				<div class="mp-kb__table">
					<div class="mp-kb__head">
						<div>${__("Mijoz")}</div><div>${__("Telefon")}</div><div>${__("Holat")}</div>
						<div>${__("Do‘kon")}</div><div>${__("To‘lov holati")}</div><div class="text-right">${__("Summa")}</div>
					</div>
					${d.rows.map((o) => this.row(o)).join("")}
				</div>` : `<div class="mp-kb__empty text-muted">${empty}</div>`}
		`);
		this.$body.find("[data-tab]").on("click", (e) => {
			this.tab = $(e.currentTarget).attr("data-tab");
			this.load();
		});
		this.$body.find("[data-tel]").on("click", (e) => e.stopPropagation());
		this.$body.find(".mp-kb__row").on("click keydown", (e) => {
			if (e.type === "keydown" && e.key !== "Enter") return;
			this.open($(e.currentTarget).attr("data-order"));
		});
	}

	async open(order) {
		const o = await frappe.xcall("marketplace.kuryer.delivery", { order });
		const esc = frappe.utils.escape_html;
		const dialog = new frappe.ui.Dialog({ title: esc(o.customer_name || o.name), size: "large" });
		const pieces = o.items.reduce((n, i) => n + i.qty, 0);
		const r = o.route;
		dialog.$body.html(`
			<div class="mp-kb-d">
				<div class="mp-kb-d__top">
					<div>
						<div class="mp-kb-d__meta">${esc(o.name)} · ${esc(o.shop_name || "")}</div>
						<div class="mp-kb-d__pills">${this.pill(o.state, o.state_color)} ${this.pay(o)}</div>
					</div>
					<div class="mp-kb-d__acts">
						${o.phone ? `<a class="btn btn-default mp-kb-d__call" href="tel:${esc(o.phone)}">${mp_kb_icon("phone")}${esc(this.phone(o.phone))}</a>` : ""}
						<button type="button" class="btn btn-default mp-kb-d__call" data-loyal>
							${o.loyal ? `${mp_kb_icon("user_check")}${__("Doimiy mijoz anketasi")}` : `${mp_kb_icon("user_plus")}${__("Doimiy mijozga qo‘shish")}`}</button>
					</div>
				</div>

				<div class="mp-kb-d__sec">${__("Manzil")}</div>
				${r.text ? `
					<button type="button" class="mp-kb-d__addr" data-addr>
						<span class="mp-kb-d__pin">${mp_kb_icon("pin")}</span>
						<span><b>${esc(r.text)}</b>
							<small>${r.source === "mijoz" ? __("Doimiy mijoz anketasidagi manzil") + " · " : ""}${__("Bosing — yo‘l ko‘rsatiladi")}</small></span>
						<span class="mp-kb-d__go">${__("Yo‘l")} →</span>
					</button>
					<div class="mp-kb-d__maps" data-maps hidden>
						<div class="mp-kb-d__ask">${__("Qaysi xaritada yo‘l ko‘rsatilsin?")}</div>
						<div class="mp-kb-d__mapbtns">
							<a class="mp-kb-d__map mp-kb-d__map--google" data-map="google" target="_blank" rel="noopener">
								<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#34a853" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Z"/><circle cx="12" cy="9" r="2.6" fill="#fff"/></svg>
								Google Maps</a>
							<a class="mp-kb-d__map mp-kb-d__map--yandex" data-map="yandex" target="_blank" rel="noopener">
								<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#fc3f1d" d="M12 2a7 7 0 0 0-7 7c0 5.2 7 13 7 13s7-7.8 7-13a7 7 0 0 0-7-7Z"/><circle cx="12" cy="9" r="2.6" fill="#fff"/></svg>
								Yandex Maps</a>
						</div>
						${r.lat ? "" : `<div class="mp-kb-d__hint">${__("Manzil matn ko‘rinishida — O‘zbekistonda uni Yandex aniqroq topadi. Google topmasa, Yandex’ni tanlang.")}</div>`}
					</div>` :`<div class="text-muted mp-kb-d__noaddr">${__("Manzil yozilmagan — mijozga qo‘ng‘iroq qilib so‘rang")}</div>`}

				<div class="mp-kb-d__sec">${__("Tovarlar")} · ${format_number(pieces, null, 0)} ${__("dona")}</div>
				<div class="mp-kb-d__items">${o.items.map((i, n) => this.item(i, n)).join("")}</div>

				<div class="mp-kb-d__total"><span>${__("Jami")}</span><b>${this.money(o.amount)}</b></div>
				${o.payment_method === "Naqd" && o.payment_status === "Kutilmoqda"
					? `<div class="mp-kb-d__cash">${__("Mijozdan {0} naqd oling", [this.money(o.amount)])}</div>` : ""}
				${o.state === "To'lov kutilmoqda"
					?`<div class="mp-kb-d__wait">${__("Mijoz hali to‘lamagan ({0}) — to‘lovdan keyin topshiring", [esc(o.payment_method || "")])}</div>` : ""}
			</div>`);

		this.bind_maps(dialog, r);
		this.bind_images(dialog, o);
		this.deliver_action(dialog, o);
		dialog.$body.find("[data-loyal]").on("click", () => {
			dialog.hide();
			this.loyal_customer(o.name);
		});
		dialog.show();
	}

	// Buyurtma formasidagi "Mijozni ro'yxatga olish" bilan bir xil (doimiy_mijoz.from_order): ro'yxatda bo'lsa —
	// anketasi ochiladi, bo'lmasa buyurtmadagi ism va telefon bilan yangi anketa. Topshirgandan keyin — avval so'raladi
	async loyal_customer(order, after_delivery = false) {
		const r = await frappe.xcall("marketplace.marketplace.doctype.doimiy_mijoz.doimiy_mijoz.from_order", { order });
		if (r.existing) {
			if (!after_delivery) frappe.set_route("Form", "Doimiy Mijoz", r.existing);
			return;
		}
		const go = () => frappe.new_doc("Doimiy Mijoz", r);
		if (!after_delivery) return go();
		frappe.confirm(
			__("Mijozni doimiy mijozlar ro‘yxatiga qo‘shamizmi? (tug‘ilgan kuni va farzandlari — chegirma va sovg‘alar uchun)"),
			go
		);
	}

	item(i, n) {
		const esc = frappe.utils.escape_html;
		const pics = i.images.length
			? i.images.map((p, k) => `<img src="${esc(p.src)}" alt="" loading="lazy" data-img="${n}:${k}">`).join("")
			: `<div class="mp-kb-d__noimg">${frappe.utils.icon("image", "lg")}</div>`;
		return `
			<div class="mp-kb-d__item">
				<div class="mp-kb-d__pics">${pics}</div>
				<div class="mp-kb-d__info">
					<b>${esc(i.name)}</b>
					${i.variant ? `<span class="mp-kb-d__var">${esc(i.variant)}</span>` : ""}
					<div class="mp-kb-d__qty"><span class="mp-kb-d__n">${format_number(i.qty, null, 0)} ${__("ta")}</span>
						<span class="text-muted">× ${this.money(i.rate)}</span><b>${this.money(i.amount)}</b></div>
				</div>
			</div>`;
	}

	bind_maps(dialog, r) {
		if (!r.text) return;
		const dest = r.lat ? `${r.lat},${r.lng}` : r.query;
		const urls = {
			google: `https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=${encodeURIComponent(dest)}`,
			yandex: `https://yandex.uz/maps/?rtt=auto&rtext=~${encodeURIComponent(dest)}`,
		};
		const $maps = dialog.$body.find("[data-maps]");
		$maps.find("[data-map]").each((_, a) => (a.href = urls[a.dataset.map]));
		dialog.$body.find("[data-addr]").on("click", () => $maps.prop("hidden", !$maps.prop("hidden")));
	}

	// Rasm bosilganda — to'liq o'lchamda, ekran bo'ylab; bir nechta rasm bo'lsa ‹ › bilan almashadi
	bind_images(dialog, o) {
		dialog.$body.find("[data-img]").on("click", (e) => {
			const [n, k] = e.currentTarget.dataset.img.split(":").map(Number);
			const pics = o.items[n].images.map((p) => p.full || p.src);
			let at = k;
			const $v = $(`
				<div class="mp-kb-view" role="dialog" aria-label="${__("Rasm")}">
					<img alt="">
					${pics.length > 1 ? `<button class="mp-kb-view__nav" data-step="-1" aria-label="${__("Oldingi")}">‹</button>
						<button class="mp-kb-view__nav mp-kb-view__nav--next" data-step="1" aria-label="${__("Keyingi")}">›</button>` : ""}
					<button class="mp-kb-view__close" aria-label="${__("Yopish")}">✕</button>
				</div>`).appendTo(document.body);
			const show = () => $v.find("img").attr("src", pics[at]);
			// Esc faqat rasmni yopsin: capture bosqichida ushlanadi, orqadagi oynaga (modal) yetib bormaydi
			const on_key = (ev) => {
				if (ev.key !== "Escape") return;
				ev.stopPropagation();
				ev.preventDefault();
				close();
			};
			const close = () => {
				$v.remove();
				document.removeEventListener("keydown", on_key, true);
			};
			show();
			$v.on("click", (ev) => {
				const step = $(ev.target).closest("[data-step]").attr("data-step");
				if (step) {
					at = (at + Number(step) + pics.length) % pics.length;
					return show();
				}
				close();
			});
			document.addEventListener("keydown", on_key, true);
		});
	}

	// Formadagi kuryer tugmasi bilan bir xil: naqdda — pulni oldi va tovarni berdi; to'langanida — tovarni berdi
	deliver_action(dialog, o) {
		// Tugma faqat kuryerga: courier_delivered bosganni kuryer deb yozadi va naqdni "uning qo'lida" qiladi.
		// Do'konchi/admin buyurtma formasidagi "Topshirildi (naqd)" ("Pulni kim oldi?") bilan belgilaydi
		if (!frappe.boot.marketplace_shop?.courier) {
			dialog.set_primary_action(__("Buyurtmani ochish"), () => {
				dialog.hide();
				frappe.set_route("Form", "Sales Order", o.name);
			});
			return;
		}
		const delivered = o.state === "Topshirilgan";
		const cash = o.payment_method === "Naqd" && o.payment_status !== "To'langan";
		const paid = o.payment_status === "To'langan";
		if (delivered || o.payment_status === "Bekor" || (!cash && !paid)) return;
		const label = cash ? __("Naqd olindi, mijozga topshirildi") : __("Mijozga topshirildi");
		const question = cash
			? __("Mijozdan {0} naqd oldingizmi va tovarni berdingizmi?", [this.money(o.amount)])
			: __("Tovarni mijozga berdingizmi?");
		dialog.set_primary_action(label, () =>
			frappe.confirm(question, async () => {
				const r = await frappe.xcall("marketplace.seller_desk.courier_delivered", { order: o.name });
				frappe.show_alert({
					message: r === "cash" ? __("Topshirildi. Pul «Qo‘limdagi naqd»da — keyin do‘kon kassiriga topshiring") : __("Topshirildi"),
					indicator: "green",
				});
				dialog.hide();
				this.load();
				this.loyal_customer(o.name, true);
			})
		);
	}

	inject_style() {
		if (document.getElementById("mp-kb-style")) return;
		$(`<style id="mp-kb-style">
			.mp-kb { max-width: 1100px; margin: 0 auto; padding: 8px 0 40px; }
			.mp-kb__empty { padding: 60px 0; text-align: center; }
			.mp-kb__tabs { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
			.mp-kb__table { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); overflow: hidden; }
			.mp-kb__head, .mp-kb__row { display: grid; align-items: center; gap: 12px; padding: 10px 14px;
				grid-template-columns: minmax(150px, 1.4fr) 170px 150px minmax(100px, 1fr) 150px 130px; }
			.mp-kb__head { font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted);
				background: var(--subtle-fg); }
			.mp-kb__row { border-top: 1px solid var(--border-color); cursor: pointer; color: var(--text-color); }
			.mp-kb__row:hover, .mp-kb__row:focus-visible { background: var(--subtle-fg); outline: none; }
			.mp-kb__c { min-width: 0; }
			.mp-kb__cust { display: grid; }
			.mp-kb__cust b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
			.mp-kb__cust small, .mp-kb__pay small { color: var(--text-muted); }
			.mp-kb__pay { display: grid; justify-items: start; gap: 2px; }
			.mp-kb__phone a { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; color: var(--text-color); }
			.mp-kb__ic { width: 16px; height: 16px; flex: none; color: var(--text-muted); }
			.mp-kb__sum { text-align: right; font-weight: 600; white-space: nowrap; font-variant-numeric: tabular-nums; }
			.mp-kb__pill { white-space: nowrap; }
			@media (max-width: 760px) {
				.mp-kb { padding: 8px 12px 40px; }
				.mp-kb__head { display: none; }
				.mp-kb__row { grid-template-columns: 1fr auto; gap: 6px 10px; padding: 12px; }
				.mp-kb__cust { grid-column: 1; }
				.mp-kb__sum { grid-column: 2; grid-row: 1; }
				.mp-kb__phone { grid-column: 1 / -1; }
				.mp-kb__phone a { display: inline-block; padding: 4px 0; }
				.mp-kb__c[data-label] { grid-column: 1 / -1; display: flex; align-items: center; gap: 8px; }
				.mp-kb__c[data-label]::before { content: attr(data-label); min-width: 64px; font-size: var(--text-xs); color: var(--text-muted); }
				.mp-kb__pay { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
			}

			.mp-kb-d__top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
			.mp-kb-d__meta { color: var(--text-muted); font-size: var(--text-sm); }
			.mp-kb-d__pills { display: flex; align-items: center; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
			.mp-kb-d__pills small { color: var(--text-muted); }
			.mp-kb-d__acts { display: flex; gap: 8px; flex-wrap: wrap; }
			.mp-kb-d__call { min-height: 40px; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
			.mp-kb-d__sec { margin: 18px 0 8px; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: .04em; }
			.mp-kb-d__addr { display: flex; align-items: center; gap: 10px; width: 100%; padding: 12px 14px; text-align: left; cursor: pointer;
				border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); color: var(--text-color); }
			.mp-kb-d__addr:hover { background: var(--subtle-fg); }
			.mp-kb-d__addr > span:nth-child(2) { display: grid; flex: 1; min-width: 0; }
			.mp-kb-d__addr small { color: var(--text-muted); }
			.mp-kb-d__pin { display: grid; place-items: center; width: 36px; height: 36px; flex: none; border-radius: 50%;
				background: var(--subtle-fg); }
			.mp-kb-d__pin .mp-kb__ic { width: 18px; height: 18px; color: var(--text-color); }
			.mp-kb-d__go { font-weight: 600; color: var(--primary); white-space: nowrap; }
			.mp-kb-d__maps { margin-top: 8px; padding: 12px; border-radius: var(--border-radius-lg); background: var(--subtle-fg); }
			.mp-kb-d__ask { font-weight: 600; margin-bottom: 8px; }
			.mp-kb-d__mapbtns { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
			.mp-kb-d__map { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 48px; padding: 8px;
				border-radius: var(--border-radius-lg); border: 1px solid var(--border-color); background: var(--card-bg);
				font-weight: 600; color: var(--text-color); }
			.mp-kb-d__map:hover { text-decoration: none; color: var(--text-color); border-color: var(--gray-500); }
			.mp-kb-d__map svg { width: 22px; height: 22px; flex: none; }
			.mp-kb-d__hint { margin-top: 8px; font-size: var(--text-sm); color: var(--text-muted); }
			.mp-kb-d__noaddr { padding: 8px 0; }
			.mp-kb-d__items { display: grid; gap: 10px; }
			.mp-kb-d__item { display: grid; grid-template-columns: auto 1fr; gap: 16px; padding: 10px;
				border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-kb-d__pics { display: flex; gap: 6px; max-width: 332px; overflow-x: auto; scroll-snap-type: x mandatory; }
			.mp-kb-d__pics img { width: 160px; height: 200px; flex: none; object-fit: cover; border-radius: var(--border-radius);
				background: var(--subtle-fg); cursor: zoom-in; scroll-snap-align: start; outline: 1px solid rgba(0,0,0,.06); outline-offset: -1px; }
			.mp-kb-d__noimg { width: 160px; height: 200px; display: grid; place-items: center; border-radius: var(--border-radius);
				background: var(--subtle-fg); color: var(--text-muted); }
			.mp-kb-d__info { display: grid; align-content: start; gap: 6px; min-width: 0; }
			.mp-kb-d__info > b { font-size: var(--text-lg); line-height: 1.3; }
			.mp-kb-d__var { justify-self: start; padding: 2px 10px; border-radius: 999px; background: var(--subtle-fg); font-size: var(--text-sm); }
			.mp-kb-d__qty { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; font-variant-numeric: tabular-nums; }
			.mp-kb-d__qty b { margin-left: auto; }
			.mp-kb-d__n { font-size: var(--text-lg); font-weight: 700; color: var(--heading-color); }
			.mp-kb-d__total { display: flex; justify-content: space-between; align-items: baseline; margin-top: 14px; padding-top: 12px;
				border-top: 1px solid var(--border-color); font-size: var(--text-lg); }
			.mp-kb-d__total b { font-size: 22px; font-variant-numeric: tabular-nums; }
			.mp-kb-d__cash, .mp-kb-d__wait { margin-top: 10px; padding: 10px 12px; border-radius: var(--border-radius-lg); font-weight: 600; }
			.mp-kb-d__cash { background: var(--bg-orange, #fff7ed); color: var(--orange-700, #c2410c); }
			.mp-kb-d__wait { background: var(--subtle-fg); color: var(--text-muted); }
			@media (max-width: 560px) {
				.mp-kb-d__item { grid-template-columns: 1fr; }
				.mp-kb-d__pics img, .mp-kb-d__noimg { width: 70vw; max-width: 260px; height: 300px; }
				.mp-kb-d__acts { width: 100%; }
				.mp-kb-d__call { flex: 1 1 100%; }
			}

			.mp-kb-view { position: fixed; inset: 0; z-index: 2000; display: grid; place-items: center; background: rgba(0,0,0,.92); }
			.mp-kb-view img { max-width: 100vw; max-height: 100vh; object-fit: contain; }
			.mp-kb-view button { position: absolute; border: 0; background: rgba(255,255,255,.14); color: #fff; border-radius: 999px;
				width: 44px; height: 44px; font-size: 22px; line-height: 1; }
			.mp-kb-view__close { top: 14px; right: 14px; }
			.mp-kb-view__nav { top: 50%; left: 12px; transform: translateY(-50%); font-size: 30px; }
			.mp-kb-view__nav--next { left: auto; right: 12px; }
		</style>`).appendTo(document.head);
	}
}
