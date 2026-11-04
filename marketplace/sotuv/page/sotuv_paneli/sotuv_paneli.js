// Sotuv paneli: do'konning sotuv menejeri to'lanmagan buyurtmalar (sotuv/api.py) va Instagram murojaatlari
// (sotuv/murojaat.py) bilan ishlaydi. Chapda ro'yxat, o'ngda karta: tovarlar, qo'ng'iroqlar (audio), natija yozish.

frappe.pages["sotuv-paneli"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Sotuv paneli"), single_column: true });
	wrapper.sotuv = new SotuvPaneli(page);
};

frappe.pages["sotuv-paneli"].on_page_show = function (wrapper) {
	wrapper.sotuv?.load();
};

const MP_VIEWS = [
	// Yangi — menejer hali gaplashmagan: kuryer ularni ko'rmaydi (sotuv/api._filters)
	["yangi", "Yangi (tekshirilmagan)"],
	["tolanmagan", "To‘lanmagan"],
	["bugun", "Bugun qayta qo‘ng‘iroq"],
	["bekor", "Bekor qilingan"],
	["hammasi", "Hammasi"],
];
const MP_RESULTS = ["Oladi", "Olmaydi", "Javob bermadi", "Keyinroq"];
const MP_RESULT_CLS = { Oladi: "green", Olmaydi: "red", "Javob bermadi": "orange", Keyinroq: "blue" };
// Buyurtma holati ranglari (sotuv/api._state) — menejer bir qarashda ko'rsin
const MP_STATE_CLS = {
	"Saytda yakunlanmagan": "purple",
	"To'lov kutilmoqda": "orange",
	"Naqd — to'lanmagan": "blue",
	"To'langan": "green",
	"Bekor qilingan": "red",
};
const MP_STATE_HINT = {
	"Saytda yakunlanmagan": "mijoz saytda to‘lov usulini tanlamagan",
	"To'lov kutilmoqda": "Payme/Click to‘lovi kutilmoqda",
	"Naqd — to'lanmagan": "naqd, topshirishda to‘laydi",
	"To'langan": "pul tushgan",
	"Bekor qilingan": "buyurtma bekor",
};
const mp_state_pill = (state) => `<span class="indicator-pill ${MP_STATE_CLS[state] || "gray"}">${frappe.utils.escape_html(__(state))}</span>`;
// Murojaatlar (Instagram lead-forma)
const MP_LEAD_VIEWS = [
	["yangi", "Yangi"],
	["bugun", "Bugun qayta qo‘ng‘iroq"],
	["jarayonda", "Jarayonda"],
	["hammasi", "Hammasi"],
	// Natija bo'yicha (rangli nuqta — ro'yxatdagi holat belgisi bilan bir xil)
	["oladi", "Oladi", "Oladi"],
	["keyinroq", "Keyinroq", "Keyinroq"],
	["javob_bermadi", "Javob bermadi", "Javob bermadi"],
	["olmaydi", "Olmaydi", "Olmaydi"],
	["buyurtma_berdi", "Buyurtma berdi", "Buyurtma berdi"],
];
const MP_LEAD_CLS = { Yangi: "purple", Oladi: "green", Olmaydi: "red", "Javob bermadi": "orange", Keyinroq: "blue", "Buyurtma berdi": "green" };
const mp_lead_pill = (holat) => `<span class="indicator-pill ${MP_LEAD_CLS[holat] || "gray"}">${frappe.utils.escape_html(__(holat))}</span>`;

class SotuvPaneli {
	constructor(page) {
		this.page = page;
		this.state = { mode: "buyurtma", view: "yangi", q: "", open: null };
		this.page.set_secondary_action(__("Yangilash"), () => this.load(), "refresh");
		this.$body = $(`<div class="mp-sp"></div>`).appendTo(page.main);
		this.inject_style();
	}

	async load() {
		if (!this.data) this.$body.html(`<div class="mp-sp__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		const leads = this.state.mode === "murojaat";
		this.data = await frappe.xcall(leads ? "marketplace.sotuv.murojaat.get_leads" : "marketplace.sotuv.api.get_orders", {
			view: this.state.view, q: this.state.q || null,
		});
		if (this.data.need_shop) return this.render_need_shop();
		// Mijoz qo'ng'iroq qildi, buyurtmasi ham, murojaati ham yo'q — call-center raqamni shu yerda tekshiradi
		if (this.data.must && !this.must_btn) this.must_btn = this.page.add_inner_button(__("🔎 Majburiy tovar: raqam"), () => this.must_dialog());
		this.render();
		if (this.state.open) this.open(this.state.open, false);
	}

	// Admin do'kon panelida emas: do'konni Do'konlar panelida tanlaydi. To'liq yuklash — boshqa oynada
	// do'kon panelidan chiqilgan bo'lsa, eski menyu va tepadagi "do'koni paneli" qatori qolib ketmasin
	render_need_shop() {
		this.$body.html(`<div class="mp-sp__empty text-muted">
			<p>${__("Bu sahifa do‘kon uchun. Do‘konlar panelida do‘konni tanlab, «Do‘kon paneliga kirish» tugmasini bosing.")}</p>
			<button class="btn btn-default btn-sm">${__("Do‘konlar paneli")}</button></div>`);
		this.$body.find("button").on("click", () => (window.location.href = "/desk/shops-overview"));
	}

	render() {
		const esc = frappe.utils.escape_html;
		const { rows, counts, shop_name } = this.data;
		const leads = this.state.mode === "murojaat";
		const views = leads ? MP_LEAD_VIEWS : MP_VIEWS;
		// Rejim almashtirgichi: yangi murojaatlar soni buyurtmalar rejimida ham ko'rinib tursin
		const lead_new = leads ? counts.yangi : this.data.lead_new;
		this.$body.html(`
			<div class="mp-sp__modes">
				<button class="${leads ? "" : "is-active"}" data-mode="buyurtma">🛒 ${__("Buyurtmalar")}</button>
				<button class="${leads ? "is-active" : ""} ${lead_new ? "is-due" : ""}" data-mode="murojaat">📣 ${__("Murojaatlar")}${lead_new ? ` <span>${lead_new} ${__("yangi")}</span>` : ""}</button>
			</div>
			<div class="mp-sp__top">
				<div class="mp-sp__tabs">${views.map(([v, l, holat], i) => `${holat && !views[i - 1][2] ? `<span class="mp-sp__tabs-sep"></span>` : ""}
					<button class="${this.state.view === v ? "is-active" : ""} ${v === "bugun" && counts.bugun ? "is-due" : ""}" data-view="${v}">
						${holat ? `<i class="mp-sp__dot" style="--c: var(--${MP_LEAD_CLS[holat]}-500)"></i>` : ""}${__(l)} <span>${counts[v] || 0}</span></button>`).join("")}
				</div>
				<input class="form-control mp-sp__search" type="search" placeholder="${leads ? __("Ism, telefon, kitob, tovar ID yoki kampaniya…") : __("Ism, telefon yoki buyurtma raqami…")}" value="${esc(this.state.q)}">
			</div>
			<div class="mp-sp__shop text-muted small">
				<b>${esc(shop_name || "")}</b>
				${leads ? "" : `<span class="mp-sp__legend">${Object.keys(MP_STATE_CLS).map((s) => `<span title="${esc(MP_STATE_HINT[s])}">${mp_state_pill(s)}</span>`).join("")}</span>`}
			</div>
			<div class="mp-sp__grid">
				<div class="mp-sp__list">${rows.length ? rows.map((r) => (leads ? this.lead_row(r) : this.row(r))).join("") : `<div class="mp-sp__empty text-muted">${leads ? __("Bu bo‘limda murojaat yo‘q") : __("Bu bo‘limda buyurtma yo‘q")}</div>`}</div>
				<div class="mp-sp__card"><div class="mp-sp__empty text-muted">${leads ? __("Chapdan murojaatni tanlang") : __("Chapdan buyurtmani tanlang")}</div></div>
			</div>`);
		this.bind();
	}

	lead_row(r) {
		const esc = frappe.utils.escape_html;
		const due = r.keyingi_qongiroq ? `<span class="mp-sp__due">⏰ ${frappe.datetime.str_to_user(r.keyingi_qongiroq)}</span>` : "";
		return `
			<div class="mp-sp__row mp-sp__row--${MP_LEAD_CLS[r.holat] || "gray"} ${this.state.open === r.name ? "is-open" : ""}" data-open="${esc(r.name)}">
				<div class="mp-sp__row-main">
					<b>${esc(r.mijoz_ismi || "—")}</b>
					<a class="mp-sp__tel" href="tel:${esc(r.telefon || "")}">${esc(r.telefon || "")}</a>
					<div class="text-muted small">${r.shahar ? `📍 ${esc(r.shahar)} · ` : ""}${esc(r.manba || "")}${r.kampaniya ? ` · ${esc(r.kampaniya)}` : ""} · ${esc(frappe.datetime.str_to_user(r.creation))}${r.calls ? ` · 📞 ${r.calls}` : ""}</div>
					${r.izoh ? `<div class="mp-sp__note-line small">💬 ${esc(r.izoh)}</div>` : ""}
				</div>
				<div class="mp-sp__row-side">
					${r.tovar_nomi ? `<b class="mp-sp__book">📘 ${esc(r.tovar_nomi)}</b>` : `<span class="text-muted small">${__("Tovar ko‘rsatilmagan")}</span>`}
					${r.tovar ? `<span class="mp-sp__tid" title="${__("Tovar ID")}">ID: ${esc(r.tovar)}</span>` : ""}
					${mp_lead_pill(r.holat)}${due}
				</div>
			</div>`;
	}

	row(r) {
		const esc = frappe.utils.escape_html;
		const res = r.mp_aloqa_natija
			? `<span class="indicator-pill ${MP_RESULT_CLS[r.mp_aloqa_natija] || "gray"}">${esc(r.mp_aloqa_natija)}${r.mp_aloqa_kanal ? ` · ${esc(r.mp_aloqa_kanal)}` : ""}</span>`
			: `<span class="indicator-pill gray">${__("Hali gaplashilmagan")}</span>`;
		const due = r.mp_keyingi_qongiroq ? `<span class="mp-sp__due">⏰ ${frappe.datetime.str_to_user(r.mp_keyingi_qongiroq)}</span>` : "";
		return `
			<div class="mp-sp__row mp-sp__row--${MP_STATE_CLS[r.state] || "gray"} ${this.state.open === r.name ? "is-open" : ""}" data-open="${esc(r.name)}">
				<div class="mp-sp__row-main">
					<b>${esc(r.customer_name || r.customer || "—")}</b>
					<a class="mp-sp__tel" href="tel:${esc(r.customer_phone || "")}">${esc(r.customer_phone || "")}</a>
					<div class="text-muted small">${mp_state_pill(r.state)} ${esc(r.name)} · ${frappe.datetime.str_to_user(String(r.creation).slice(0, 10))}${r.calls ? ` · 📞 ${r.calls}` : ""}</div>
					${r.last_note ? `<div class="mp-sp__note-line small">📌 ${esc(r.last_note)}</div>` : ""}
				</div>
				<div class="mp-sp__row-side">
					<b>${this.money(r.grand_total)}</b>
					${res}${due}
				</div>
			</div>`;
	}

	bind() {
		this.$body.find("[data-mode]").on("click", (e) => {
			const mode = e.currentTarget.dataset.mode;
			if (mode === this.state.mode) return;
			Object.assign(this.state, { mode, view: mode === "murojaat" ? "yangi" : "tolanmagan", open: null, q: "" });
			this.load();
		});
		this.$body.find("[data-view]").on("click", (e) => {
			this.state.view = e.currentTarget.dataset.view;
			this.state.open = null;
			this.load();
		});
		const $s = this.$body.find(".mp-sp__search");
		$s.on("input", frappe.utils.debounce(() => {
			this.state.q = $s.val();
			this.load().then(() => this.$body.find(".mp-sp__search").trigger("focus"));
		}, 350));
		this.$body.find("[data-open]").on("click", (e) => {
			if ($(e.target).closest("a").length) return; // telefon havolasi — qo'ng'iroq
			this.open(e.currentTarget.dataset.open);
		});
	}

	async open(name, scroll = true) {
		this.state.open = name;
		this.$body.find(".mp-sp__row").removeClass("is-open").filter(`[data-open="${CSS.escape(name)}"]`).addClass("is-open");
		const $card = this.$body.find(".mp-sp__card");
		$card.html(`<div class="mp-sp__empty text-muted">${__("Yuklanmoqda…")}</div>`);
		const leads = this.state.mode === "murojaat";
		const d = await frappe.xcall(leads ? "marketplace.sotuv.murojaat.get_lead" : "marketplace.sotuv.api.get_order", { name });
		if (this.state.open !== name) return;
		this.order = d;
		$card.html(leads ? this.lead_card(d) : this.card(d));
		leads ? this.bind_lead_card($card, d) : this.bind_card($card, d);
		if (scroll && window.innerWidth < 900) $card.get(0).scrollIntoView({ behavior: "smooth", block: "start" });
	}

	card(d) {
		const esc = frappe.utils.escape_html;
		const n = (x) => format_number(x || 0, null, 0);
		const items = d.items.map((i) => `
			<tr>
				<td>${i.image ? `<img src="${esc(i.image)}" alt="">` : ""}<span><b>${esc(i.name)}</b>${i.variant ? `<br><small class="text-muted">${esc(i.variant)}</small>` : ""}</span></td>
				<td class="num">${n(i.qty)}</td><td class="num">${this.money(i.rate)}</td><td class="num"><b>${this.money(i.amount)}</b></td>
			</tr>`).join("");
		const call_html = (c, attach) => this.call_html(c, attach);
		const calls = d.calls.length
			? d.calls.map((c) => call_html(c, false)).join("")
			: `<div class="text-muted small">${__("Bu mijoz bilan hali qo‘ng‘iroq yozuvi yo‘q. Telefondagi ilova yozuvni o‘zi yuboradi.")}</div>`;
		const unlinked = (d.unlinked || []).length
			? `<div class="mp-sp__sec">${__("Raqami aniqlanmagan qo‘ng‘iroqlar (oxirgi 3 kun)")} <span class="text-muted">${d.unlinked.length}</span></div>
				<div class="text-muted small">${__("Ilova raqamni yubormagan. Shu mijoz bilan gaplashgan bo‘lsangiz — biriktiring.")}</div>
				<div class="mp-sp__calls">${d.unlinked.map((c) => call_html(c, true)).join("")}</div>`
			: "";
		const pinned = d.logs.find((l) => l.izoh);
		const pin_html = pinned
			? `<div class="mp-sp__pin">
				<div class="mp-sp__pin-head">
					<b>📌 ${__("Oxirgi izoh")}</b>
					<span class="indicator-pill ${MP_RESULT_CLS[pinned.natija] || "gray"}">${esc(pinned.natija)}</span>
					${pinned.keyingi_qongiroq ? `<span class="mp-sp__due">⏰ ${frappe.datetime.str_to_user(pinned.keyingi_qongiroq)}</span>` : ""}
				</div>
				<div class="mp-sp__pin-text">${esc(pinned.izoh)}</div>
				<div class="small text-muted">${esc(frappe.datetime.str_to_user(pinned.creation))} · ${esc(pinned.menejer_ismi || "")}${pinned.buyurtma !== d.name ? ` · ${esc(pinned.buyurtma)}` : ""}</div>
			</div>`
			: "";
		const logs = d.logs.length
			? d.logs.map((l) => `
				<div class="mp-sp__log">
					<span class="indicator-pill ${MP_RESULT_CLS[l.natija] || "gray"}">${esc(l.natija)}</span>
					<span class="small">${esc(l.kanal)} · ${esc(frappe.datetime.str_to_user(l.creation))} · ${esc(l.menejer_ismi || "")}${l.buyurtma !== d.name ? ` · <span class="text-muted">${esc(l.buyurtma)}</span>` : ""}</span>
					${l.keyingi_qongiroq ? `<span class="small mp-sp__due">⏰ ${frappe.datetime.str_to_user(l.keyingi_qongiroq)}</span>` : ""}
					${l.bekor_qilindi ? `<span class="small text-danger">${__("buyurtma bekor qilindi")}</span>` : ""}
					${l.izoh ? `<div class="small">${esc(l.izoh)}</div>` : ""}
				</div>`).join("")
			: `<div class="text-muted small">${__("Hali natija yozilmagan")}</div>`;
		const phone = esc(d.customer_phone || "");
		return `
			<div class="mp-sp__head">
				<div>
					<div class="mp-sp__name">${esc(d.customer_name || "—")}</div>
					<div class="mp-sp__contacts">
						<a class="btn btn-xs btn-default" href="tel:${phone}">📞 ${phone}</a>
						<a class="btn btn-xs btn-default" href="sms:${phone}">✉️ SMS</a>
					</div>
				</div>
				<div class="mp-sp__total"><b>${this.money(d.grand_total)}</b><div class="small text-muted">${esc(d.name)}</div><div>${mp_state_pill(d.state)}</div></div>
			</div>
			${d.delivery_method ? `<div class="small text-muted mp-sp__deliv">🚚 ${esc(d.delivery_method)}${d.delivery_address ? ` — ${esc(d.delivery_address)}` : ""}</div>` : ""}
			${d.courier_open ? (d.confirmed
				? `<div class="small mp-sp__conf is-ok">✅ ${__("Tasdiqlangan — kuryer yetkazishni ko‘radi")}</div>`
				: `<div class="small mp-sp__conf">⏳ ${__("Kuryer hali ko‘rmaydi: mijoz bilan gaplashib, manzilni aniqlang va «Oladi»ni belgilang")}</div>`) : ""}
			${pin_html}
			${this.must_html(d.mandatory)}
			<div class="mp-sp__sec">${__("Xarid qilingan tovarlar")}</div>
			<table class="mp-sp__items"><thead><tr><th>${__("Tovar")}</th><th class="num">${__("Soni")}</th><th class="num">${__("Narxi")}</th><th class="num">${__("Summa")}</th></tr></thead><tbody>${items}</tbody></table>

			<div class="mp-sp__sec">${__("Natija yozish")}</div>
			<div class="mp-sp__form">
				<div class="mp-sp__seg" data-group="kanal">
					<button data-val="Qo‘ng‘iroq" class="is-active">📞 ${__("Qo‘ng‘iroq qilindi")}</button>
					<button data-val="SMS">✉️ ${__("SMS yozildi")}</button>
				</div>
				<div class="mp-sp__seg" data-group="natija">${MP_RESULTS.map((r) => `<button data-val="${r}" class="is-${MP_RESULT_CLS[r]}">${__(r)}</button>`).join("")}</div>
				${d.courier_open && !d.confirmed ? `<div class="small mp-sp__conf is-ok" data-oladi-hint hidden>✅ ${__("Saqlangach buyurtma kuryerga o‘tadi")}</div>` : ""}
				${d.courier_open ? `<label class="small text-muted">${__("Yetkazish manzili — mijoz bilan aniqlashtiring")}
					<textarea class="form-control" rows="2" data-manzil>${esc(d.delivery_address || "")}</textarea>
				</label>` : ""}
				<label class="mp-sp__cancel" hidden>
					<input type="checkbox" data-cancel ${d.can_cancel ? "checked" : "disabled"}>
					${d.can_cancel ? __("Buyurtma bekor qilinsin (tovar yana sotuvga chiqadi)") : __("Bu buyurtmani bekor qilib bo‘lmaydi (topshirilgan, to‘langan yoki allaqachon bekor)")}
				</label>
				<label class="small text-muted">${__("Qayta qo‘ng‘iroq sanasi (shu kuni eslatiladi)")}
					<input class="form-control input-sm" type="date" data-next min="${frappe.datetime.get_today()}">
				</label>
				<textarea class="form-control" rows="2" data-izoh placeholder="${__("Izoh: nima dedi, qachon oladi…")}"></textarea>
				<button class="btn btn-primary btn-sm" data-save>${__("Saqlash")}</button>
			</div>

			<div class="mp-sp__sec">${__("Izohlar va natijalar tarixi")} <span class="text-muted">${d.logs.length || ""}</span></div>
			<div class="mp-sp__logs">${logs}</div>
			<div class="mp-sp__sec">${__("Qo‘ng‘iroqlar")} <span class="text-muted">${d.calls.length || ""}</span></div>
			<div class="mp-sp__calls">${calls}</div>
			${unlinked}`;
	}

	bind_card($card, d) {
		mp.voice_init($card);
		this.bind_must($card, d.customer_phone, () => this.open(d.name, false));
		$card.find("[data-attach]").on("click", async (e) => {
			e.currentTarget.disabled = true;
			const fresh = await frappe.xcall("marketplace.sotuv.api.attach_call", { call: e.currentTarget.dataset.attach, order: d.name });
			frappe.show_alert({ message: __("Qo‘ng‘iroq buyurtmaga biriktirildi"), indicator: "green" });
			this.order = fresh;
			$card.html(this.card(fresh));
			this.bind_card($card, fresh);
		});
		const pick = { kanal: "Qo‘ng‘iroq", natija: null };
		$card.find(".mp-sp__seg button").on("click", (e) => {
			const $b = $(e.currentTarget);
			const group = $b.closest(".mp-sp__seg").data("group");
			pick[group] = $b.data("val");
			$b.addClass("is-active").siblings().removeClass("is-active");
			if (group === "natija") {
				$card.find(".mp-sp__cancel").prop("hidden", pick.natija !== "Olmaydi");
				$card.find("[data-oladi-hint]").prop("hidden", pick.natija !== "Oladi");
			}
		});
		$card.find("[data-save]").on("click", async (e) => {
			if (!pick.natija) return frappe.show_alert({ message: __("Natijani tanlang: Oladi, Olmaydi, Javob bermadi yoki Keyinroq"), indicator: "orange" });
			const bekor = pick.natija === "Olmaydi" && $card.find("[data-cancel]").is(":checked") ? 1 : 0;
			const go = async () => {
				e.currentTarget.disabled = true;
				try {
					const r = await frappe.xcall("marketplace.sotuv.api.save_result", {
						order: d.name, kanal: pick.kanal, natija: pick.natija, bekor,
						izoh: $card.find("[data-izoh]").val() || null,
						manzil: $card.find("[data-manzil]").val() || null,
						keyingi_qongiroq: $card.find("[data-next]").val() || null,
					});
					frappe.show_alert({ message: r.cancelled ? __("Saqlandi, buyurtma bekor qilindi") : __("Saqlandi"), indicator: "green" });
					await this.load();
				} finally {
					e.currentTarget.disabled = false;
				}
			};
			bekor ? frappe.confirm(__("Buyurtma bekor qilinadi va tovar yana sotuvga chiqadi. Davom etilsinmi?"), go) : go();
		});
	}

	// AI (sotuv/stt.py): qisqa tahlil ko'rinib turadi, to'liq transkript — bosilganda ochiladi
	ai_html(c) {
		const esc = frappe.utils.escape_html;
		if (c.ai_xulosa || c.transkript) {
			return `<div class="mp-sp__ai">
				${c.ai_xulosa ? `<div class="mp-sp__ai-sum"><span class="mp-sp__ai-tag">AI</span>${esc(c.ai_xulosa).replace(/\n/g, "<br>")}</div>` : ""}
				${c.transkript ? `<details><summary>${__("Transkript")}</summary><div class="mp-sp__ai-text">${esc(c.transkript).replace(/\n/g, "<br>")}</div></details>` : ""}
			</div>`;
		}
		if (c.holat === "Transkripsiya") return `<div class="text-muted small">${__("AI suhbatni matnga aylantirmoqda…")}</div>`;
		return "";
	}

	call_html(c, attach) {
		const esc = frappe.utils.escape_html;
		return `
			<div class="mp-sp__call">
				<div class="small"><b>${c.yonalish === "Kiruvchi" ? "📥 " + __("Kiruvchi") : "📤 " + __("Chiquvchi")}</b>
					<span class="text-muted">· ${esc(frappe.datetime.str_to_user(c.boshlandi))}${c.telefon ? ` · ${esc(c.telefon)}` : ""}</span></div>
				${c.yozuv ? mp.voice_note(c.yozuv, { who: c.menejer_ismi || "" }) : `<span class="text-muted small">${__("Yozuv yo‘q")}</span>`}
				${this.ai_html(c)}
				${attach ? `<button class="btn btn-xs btn-default" data-attach="${esc(c.name)}">🔗 ${__("Shu buyurtmaga biriktirish")}</button>` : ""}
			</div>`;
	}

	// Murojaat kartasi: kim, qaysi kitob bo'yicha, izohi; natija yozish; qo'ng'iroqlar; shu raqamdan saytdagi buyurtmalar
	lead_card(d) {
		const esc = frappe.utils.escape_html;
		const phone = esc(d.telefon || "");
		const item = d.item;
		const sms_text = item ? `${__("Assalomu alaykum! Siz so‘ragan kitob")}: ${item.item_name} — ${item.url}` : "";
		const orders = d.orders.length
			? d.orders.map((o) => `<div class="mp-sp__log small"><b>${esc(o.name)}</b> · ${this.money(o.grand_total)} ·
				${esc(o.docstatus === 2 ? __("Bekor qilingan") : o.payment_status)} · ${esc(frappe.datetime.str_to_user(o.creation))}</div>`).join("")
			: `<div class="text-muted small">${__("Bu raqamdan saytda hali buyurtma yo‘q")}</div>`;
		const logs = d.logs.length
			? d.logs.map((l) => `
				<div class="mp-sp__log">
					<span class="indicator-pill ${MP_RESULT_CLS[l.natija] || "gray"}">${esc(l.natija)}</span>
					<span class="small">${esc(l.kanal)} · ${esc(frappe.datetime.str_to_user(l.creation))} · ${esc(l.menejer_ismi || "")}${l.buyurtma ? ` · <span class="text-muted">${esc(l.buyurtma)}</span>` : ""}</span>
					${l.keyingi_qongiroq ? `<span class="small mp-sp__due">⏰ ${frappe.datetime.str_to_user(l.keyingi_qongiroq)}</span>` : ""}
					${l.izoh ? `<div class="small">${esc(l.izoh)}</div>` : ""}
				</div>`).join("")
			: `<div class="text-muted small">${__("Hali natija yozilmagan")}</div>`;
		const calls = d.calls.length
			? d.calls.map((c) => this.call_html(c, false)).join("")
			: `<div class="text-muted small">${__("Bu mijoz bilan hali qo‘ng‘iroq yozuvi yo‘q. Telefondagi ilova yozuvni o‘zi yuboradi.")}</div>`;
		return `
			<div class="mp-sp__head">
				<div>
					<div class="mp-sp__name">${esc(d.mijoz_ismi || "—")}</div>
					${d.shahar ? `<div class="small text-muted">📍 ${esc(d.shahar)}</div>` : ""}
					<div class="mp-sp__contacts">
						<a class="btn btn-xs btn-default" href="tel:${phone}">📞 ${phone}</a>
						<a class="btn btn-xs btn-default" href="sms:${phone}${sms_text ? `?body=${encodeURIComponent(sms_text)}` : ""}">✉️ SMS${item ? " + " + __("havola") : ""}</a>
					</div>
				</div>
				<div class="mp-sp__total">${mp_lead_pill(d.holat)}
					<div class="small text-muted">${esc(d.name)} · ${esc(d.manba || "")}${d.kampaniya ? ` · ${esc(d.kampaniya)}` : ""}</div>
					<div class="small text-muted">${esc(frappe.datetime.str_to_user(d.created))}</div></div>
			</div>
			<div class="mp-sp__sec">${__("Qaysi tovar bo‘yicha")}</div>
			${item ? `<div class="mp-sp__book-card">
					${item.image ? `<img src="${esc(item.image)}" alt="">` : ""}
					<div><b>${esc(item.item_name)}</b>
						<div class="mp-sp__tid">${__("Tovar ID")}: ${esc(item.name)}</div>
						${item.price ? `<div>${this.money(item.price)}</div>` : ""}
						<a class="small" href="${esc(item.url)}" target="_blank" rel="noopener">${__("Saytda ko‘rish")} ↗</a></div>
				</div>`
				: `<div class="small">${esc(d.tovar_nomi || __("Reklamada tovar ko‘rsatilmagan"))}</div>`}
			${d.izoh ? `<div class="mp-sp__pin"><div class="mp-sp__pin-head"><b>💬 ${__("Mijoz izohi")}</b></div><div class="mp-sp__pin-text">${esc(d.izoh)}</div></div>` : ""}
			${this.must_html(d.mandatory)}

			<div class="mp-sp__sec">${__("Natija yozish")}</div>
			<div class="mp-sp__form">
				<div class="mp-sp__seg" data-group="kanal">
					<button data-val="Qo‘ng‘iroq" class="is-active">📞 ${__("Qo‘ng‘iroq qilindi")}</button>
					<button data-val="SMS">✉️ ${__("SMS yozildi")}</button>
				</div>
				<div class="mp-sp__seg" data-group="natija">${MP_RESULTS.map((r) => `<button data-val="${r}" class="is-${MP_RESULT_CLS[r]}">${__(r)}</button>`).join("")}</div>
				<label class="small text-muted">${__("Qayta qo‘ng‘iroq sanasi (shu kuni eslatiladi)")}
					<input class="form-control input-sm" type="date" data-next min="${frappe.datetime.get_today()}">
				</label>
				<textarea class="form-control" rows="2" data-izoh placeholder="${__("Izoh: nima dedi, qachon oladi…")}"></textarea>
				<button class="btn btn-primary btn-sm" data-save>${__("Saqlash")}</button>
			</div>
			<div class="mp-sp__sec">${__("Izohlar va natijalar tarixi")} <span class="text-muted">${d.logs.length || ""}</span></div>
			<div class="mp-sp__logs">${logs}</div>
			<div class="mp-sp__sec">${__("Qo‘ng‘iroqlar")} <span class="text-muted">${d.calls.length || ""}</span></div>
			<div class="mp-sp__calls">${calls}</div>
			<div class="mp-sp__sec">${__("Saytdagi buyurtmalari")}</div>
			<div class="mp-sp__logs">${orders}</div>`;
	}

	bind_lead_card($card, d) {
		mp.voice_init($card);
		this.bind_must($card, d.telefon, () => this.open(d.name, false));
		const pick = { kanal: "Qo‘ng‘iroq", natija: null };
		$card.find(".mp-sp__seg button").on("click", (e) => {
			const $b = $(e.currentTarget);
			pick[$b.closest(".mp-sp__seg").data("group")] = $b.data("val");
			$b.addClass("is-active").siblings().removeClass("is-active");
		});
		$card.find("[data-save]").on("click", async (e) => {
			if (!pick.natija) return frappe.show_alert({ message: __("Natijani tanlang: Oladi, Olmaydi, Javob bermadi yoki Keyinroq"), indicator: "orange" });
			e.currentTarget.disabled = true;
			try {
				await frappe.xcall("marketplace.sotuv.murojaat.save_lead_result", {
					name: d.name, kanal: pick.kanal, natija: pick.natija,
					izoh: $card.find("[data-izoh]").val() || null,
					keyingi_qongiroq: $card.find("[data-next]").val() || null,
				});
				frappe.show_alert({ message: __("Saqlandi"), indicator: "green" });
				await this.load();
			} finally {
				e.currentTarget.disabled = false;
			}
		});
	}

	// Majburiy tovar (masalan, o'qiydigan ruchka): mijoz olganmi. Olmagan bo'lsa — call-center eski raqamni tekshiradi
	must_html(m) {
		if (!m) return "";
		const left = m.missing;
		return `<div class="mp-sp__must ${left ? "" : "is-ok"}">
			<b>${left ? `⚠️ ${__("Majburiy tovar: {0} tasi olinmagan", [left])}` : `✅ ${__("Majburiy tovarlar olingan")}`}</b>
			${this.must_list(m)}
			${left ? `<div class="small text-muted">${__("Mijoz boshqa raqamdan olgan bo‘lsa — eski raqamini so‘rang. Faqat eski raqamdan olingan tovar tasdiqlanadi.")}</div>
				<button class="btn btn-xs btn-default" data-must-check>🔎 ${__("Eski raqam bo‘yicha tekshirish")}</button>` : ""}
		</div>`;
	}

	must_list(m) {
		const esc = frappe.utils.escape_html;
		return `<ul class="mp-sp__must-list">${m.items.map((i) => i.basis
			? `<li>✅ ${esc(i.name)} <span class="text-muted small">(${esc(i.basis)})</span></li>`
			: `<li>❌ <b>${esc(i.name)}</b> <span class="text-muted small">— ${__("olinmagan")}</span></li>`).join("")}</ul>`;
	}

	bind_must($card, phone, reopen) {
		$card.find("[data-must-check]").on("click", () => this.must_dialog(phone, reopen));
	}

	// Call-center: raqam bo'yicha holat; raqamini almashtirgan bo'lsa — eski raqamdan olingan tovarlar yangi raqamga
	// tasdiqlanadi. Eski raqam ham olmagan tovarni tasdiqlab bo'lmaydi (server ham ruxsat bermaydi).
	must_dialog(phone, reopen) {
		const d = new frappe.ui.Dialog({
			title: __("Majburiy tovar: raqam tekshirish"),
			fields: [
				{ fieldname: "phone", fieldtype: "Data", label: __("Mijozning hozirgi raqami"), reqd: 1, default: phone || "",
					read_only: phone ? 1 : 0, description: __("Masalan: 90 123 45 67") },
				{ fieldname: "old", fieldtype: "Data", label: __("Eski raqami (raqamini almashtirgan bo‘lsa)"),
					description: __("Bo‘sh qoldirsangiz — faqat holatni ko‘rsatadi") },
				{ fieldname: "result", fieldtype: "HTML" },
			],
			primary_action_label: __("Tekshirish"),
			primary_action: async (v) => {
				let r;
				try {
					r = v.old
						? await frappe.xcall("marketplace.sotuv.api.confirm_old_phone", { phone: v.phone, old_phone: v.old })
						: await frappe.xcall("marketplace.sotuv.api.mandatory_check", { phone: v.phone });
				} catch (e) {
					return; // server xabari (masalan, "eski raqamdan xarid topilmadi") allaqachon ko'rsatilgan
				}
				const esc = frappe.utils.escape_html;
				const done = r.confirmed?.length
					? `<p class="text-success">${__("Tasdiqlandi")}: <b>${esc(r.confirmed.join(", "))}</b></p>`
					: v.old ? `<p class="text-muted">${__("Yangi tasdiq kerak bo‘lmadi: eski raqamdagi tovarlar bu raqamda allaqachon bor.")}</p>` : "";
				const next = r.missing
					? `<p>${__("Mijoz {0} raqami bilan buyurtma bera olmaydi: ❌ belgili tovarlarni savatga qo‘shishi kerak.", [esc(r.phone)])}</p>`
					: `<p class="text-success">${__("Mijoz {0} raqami bilan buyurtma bera oladi.", [esc(r.phone)])}</p>`;
				d.fields_dict.result.$wrapper.html(`<div class="mp-sp__must ${r.missing ? "" : "is-ok"}">${done}${this.must_list(r)}${next}</div>`);
				if (r.confirmed?.length) reopen?.();
			},
		});
		d.show();
	}

	money(x) {
		return `${format_number(x || 0, null, 0)} so‘m`;
	}

	duration(sec) {
		sec = cint(sec);
		return sec >= 60 ? `${Math.floor(sec / 60)} daq ${sec % 60} s` : `${sec} s`;
	}

	inject_style() {
		if (document.getElementById("mp-sp-style")) return;
		$(`<style id="mp-sp-style">
			.mp-sp { padding: 4px var(--padding-md, 15px) 40px; }
			.mp-sp__modes { display: inline-flex; gap: 4px; padding: 3px; margin-bottom: 10px; border-radius: 10px; background: var(--subtle-fg); }
			.mp-sp__modes button { border: 0; background: none; border-radius: 8px; padding: 6px 14px; font-weight: 600; color: var(--text-muted); }
			.mp-sp__modes button.is-active { background: var(--card-bg); color: var(--heading-color); box-shadow: var(--shadow-sm); }
			.mp-sp__modes button span { margin-left: 4px; padding: 0 6px; border-radius: 8px; background: var(--orange-500, #f97316); color: #fff; font-size: 11px; }
			.mp-sp__book { color: var(--heading-color); font-size: var(--text-sm); max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
			.mp-sp__tid { font-family: var(--font-stack-monospace, monospace); font-size: 11px; color: var(--text-muted); max-width: 220px; overflow: hidden; text-overflow: ellipsis; user-select: all; }
			.mp-sp__must { margin-top: 10px; padding: 8px 12px; border-radius: var(--border-radius-md); background: var(--bg-orange); display: grid; gap: 4px; }
			.mp-sp__must.is-ok { background: var(--bg-green); }
			.mp-sp__must .btn { justify-self: start; }
			.mp-sp__must-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 2px; }
			.mp-sp__must p { margin: 4px 0 0; }
			.mp-sp__book-card { display: flex; gap: 10px; align-items: center; padding: 8px; border: 1px solid var(--border-color); border-radius: var(--border-radius-md); }
			.mp-sp__book-card img { width: 52px; height: 52px; object-fit: cover; border-radius: 6px; }
			.mp-sp__top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 6px; }
			.mp-sp__tabs { display: flex; flex-wrap: wrap; gap: 6px; }
			.mp-sp__tabs button { border: 1px solid var(--border-color); background: var(--card-bg); border-radius: 16px; padding: 5px 12px; font-size: var(--text-sm); color: var(--text-muted); }
			.mp-sp__tabs button span { margin-left: 4px; font-weight: 600; }
			.mp-sp__tabs-sep { width: 1px; align-self: stretch; margin: 4px 2px; background: var(--border-color); }
			.mp-sp__dot { display: inline-block; width: 8px; height: 8px; margin-right: 6px; border-radius: 50%; background: var(--c); vertical-align: 1px; }
			.mp-sp__tabs button.is-active { background: var(--text-color); border-color: var(--text-color); color: var(--fg-color, var(--card-bg)); }
			.mp-sp__tabs button.is-due:not(.is-active) { border-color: var(--orange-500, #f97316); color: var(--orange-600, #ea580c); }
			.mp-sp__search { max-width: 300px; }
			.mp-sp__shop { margin-bottom: 10px; }
			.mp-sp__grid { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 6fr); gap: 14px; align-items: start; }
			.mp-sp__list, .mp-sp__card { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); background: var(--card-bg); }
			.mp-sp__list { max-height: calc(100vh - 220px); overflow: auto; }
			.mp-sp__card { padding: 14px 16px; position: sticky; top: 70px; max-height: calc(100vh - 90px); overflow: auto; }
			.mp-sp__empty { padding: 40px 10px; text-align: center; }
			.mp-sp__row { display: flex; gap: 10px; justify-content: space-between; padding: 10px 14px; border-top: 1px solid var(--border-color); cursor: pointer; }
			.mp-sp__row:first-child { border-top: 0; }
			.mp-sp__row:hover { background: var(--subtle-fg); }
			.mp-sp__row.is-open { background: var(--bg-blue); }
			.mp-sp__row { border-left: 4px solid transparent; }
			.mp-sp__row--purple { border-left-color: var(--purple-500, #8b5cf6); }
			.mp-sp__row--orange { border-left-color: var(--orange-500, #f97316); }
			.mp-sp__row--blue { border-left-color: var(--blue-500, #3b82f6); }
			.mp-sp__row--green { border-left-color: var(--green-500, #22c55e); }
			.mp-sp__row--red { border-left-color: var(--red-500, #ef4444); opacity: .75; }
			.mp-sp__row .indicator-pill { font-size: 11px; padding: 1px 6px; }
			.mp-sp__shop { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
			.mp-sp__legend { display: inline-flex; flex-wrap: wrap; gap: 4px; }
			.mp-sp__legend .indicator-pill { font-size: 11px; cursor: help; }
			.mp-sp__row-main { min-width: 0; display: grid; gap: 1px; }
			.mp-sp__row-main b { color: var(--heading-color); }
			.mp-sp__tel { font-size: var(--text-sm); justify-self: start; }
			.mp-sp__row-side { display: grid; justify-items: end; align-content: start; gap: 4px; white-space: nowrap; }
			.mp-sp__due { color: var(--orange-600, #ea580c); font-size: var(--text-xs); }
			.mp-sp__head { display: flex; gap: 10px; justify-content: space-between; align-items: flex-start; }
			.mp-sp__name { font-size: var(--text-xl); font-weight: 700; color: var(--heading-color); }
			.mp-sp__contacts { display: flex; gap: 6px; margin-top: 4px; }
			.mp-sp__total { text-align: right; } .mp-sp__total b { font-size: var(--text-lg); }
			.mp-sp__deliv { margin-top: 6px; }
			.mp-sp__conf { margin-top: 4px; color: var(--text-muted); }
			.mp-sp__conf.is-ok { color: var(--green-600, #16a34a); }
			.mp-sp__pin { margin-top: 12px; padding: 10px 12px; border-radius: var(--border-radius-md); background: var(--bg-yellow, #fef9c3);
				border-left: 4px solid var(--yellow-500, #eab308); display: grid; gap: 4px; }
			.mp-sp__pin-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
			.mp-sp__pin-text { white-space: pre-wrap; color: var(--heading-color); }
			.mp-sp__note-line { color: var(--text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
			.mp-sp__log > div { white-space: pre-wrap; }
			.mp-sp__sec { margin: 16px 0 6px; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; color: var(--text-muted); letter-spacing: .04em; }
			.mp-sp__items { width: 100%; font-size: var(--text-sm); border-collapse: collapse; }
			.mp-sp__items th { color: var(--text-muted); font-weight: 600; padding: 4px 6px; text-align: left; }
			.mp-sp__items td { padding: 6px; border-top: 1px solid var(--border-color); vertical-align: middle; }
			.mp-sp__items td:first-child { display: flex; gap: 8px; align-items: center; }
			.mp-sp__items img { width: 36px; height: 36px; object-fit: cover; border-radius: 6px; }
			.mp-sp__items .num { text-align: right; white-space: nowrap; }
			.mp-sp__form { display: grid; gap: 8px; padding: 10px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-sp__seg { display: flex; flex-wrap: wrap; gap: 6px; }
			.mp-sp__seg button { border: 1px solid var(--border-color); background: var(--card-bg); border-radius: 8px; padding: 6px 10px; font-size: var(--text-sm); }
			.mp-sp__seg button.is-active { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); font-weight: 600; }
			.mp-sp__seg button.is-green.is-active { background: var(--bg-green); } .mp-sp__seg button.is-red.is-active { background: var(--bg-red); }
			.mp-sp__seg button.is-orange.is-active { background: var(--bg-orange); } .mp-sp__seg button.is-blue.is-active { background: var(--bg-blue); }
			.mp-sp__cancel { display: flex; gap: 6px; align-items: center; font-size: var(--text-sm); color: var(--red-600, #dc2626); }
			.mp-sp__form input[type=date] { max-width: 200px; margin-top: 2px; }
			.mp-sp__call { padding: 6px 0; border-top: 1px solid var(--border-color); display: grid; gap: 4px; }
			.mp-sp__call:first-child { border-top: 0; }
			.mp-sp__call .btn { justify-self: start; }
			.mp-sp__ai { display: grid; gap: 4px; padding: 8px 10px; border-radius: var(--border-radius-md); background: var(--subtle-fg); font-size: var(--text-sm); }
			.mp-sp__ai-sum { line-height: 1.5; }
			.mp-sp__ai-tag { display: inline-block; margin-right: 6px; padding: 0 6px; border-radius: 4px; background: var(--blue-100, #dbeafe);
				color: var(--blue-700, #1d4ed8); font-size: var(--text-xs); font-weight: 600; }
			.mp-sp__ai summary { cursor: pointer; color: var(--text-muted); font-size: var(--text-xs); }
			.mp-sp__ai-text { margin-top: 4px; max-height: 260px; overflow-y: auto; white-space: normal; color: var(--text-color); }
			.mp-sp__log { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 6px 0; border-top: 1px solid var(--border-color); }
			.mp-sp__log:first-child { border-top: 0; } .mp-sp__log > div { flex-basis: 100%; }
			@media (max-width: 900px) {
				.mp-sp__grid { grid-template-columns: 1fr; }
				.mp-sp__list { max-height: 50vh; }
				.mp-sp__card { position: static; max-height: none; }
				.mp-sp__search { max-width: none; flex: 1 1 100%; }
			}
		</style>`).appendTo(document.head);
	}
}
