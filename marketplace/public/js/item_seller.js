// Sotuvchi uchun Item formasi: ERPNext'ning o'zi, faqat keraksiz maydonlar yashirilgan.
// Admin va Marketplace Manager to'liq formani ko'radi.
(() => {
	const is_seller = () =>
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;

	// Rang tanlash ro'yxatida faqat nomi: Frappe ostiga ID'ni ham yozadi ("Oq (clothes)" — rang.py autoname).
	// Jadvallarda (kirim, galereya) ro'yxat katakda emas, jadvalning .grid-field'ida chiziladi
	if (!document.getElementById("mp-rang-option-style")) {
		$(`<style id="mp-rang-option-style">
			[data-fieldname="ranglar"] .awesomplete [role="option"] .small,
			[data-fieldname="mp_kirim"] .grid-field .awesomplete [role="option"] .small,
			[data-fieldname="gallery"] .grid-field .awesomplete [role="option"] .small { display: none; }
		</style>`).appendTo("head");
	}

	// Hamma shablonda ko'rinadigan maydonlar
	const COMMON = [
		"item_name", "item_group", "image", "standard_rate", "variant_price", "mp_narxlar_html", "ranglar",
		"disabled", "description", "has_variants", "variant_of", "is_published",
		// Majburiy tovar (avval shuni olishi shart) va "Tez kunda" (ko'rinadi, sotilmaydi)
		"mp_majburiy", "mp_tez_kunda",
		"gallery", "mxik_code", "package_code",
		// "Ombor" tabi: hozirgi qoldiq, kirim (kimdan, nechta, necha puldan), kirim tarixi
		"mp_ombor_html", "mp_kirim_kontragent", "mp_kirim", "mp_kirim_izoh", "mp_ombor_log",
	];
	// Do'kon shabloniga qarab qo'shimcha maydonlar: sayt aynan shularni ko'rsatadi
	//   vitrina (A) — kiyim va oddiy chakana: chegirma, karusel
	//   story (B)   — Instagram uslubi, katta rasmlar: chegirma (karusel bu shablonda yo'q)
	//   katalog (C) — zavod va ulgurji: ulgurji narx, kamida nechta, qisqa xususiyat, karusel
	const BY_LAYOUT = {
		vitrina: ["old_price", "in_carousel", "carousel_label"],
		story: ["old_price"],
		katalog: ["wholesale_price", "wholesale_min_qty", "spec_line", "in_carousel", "carousel_label"],
	};
	const layout = () => frappe.boot.marketplace_shop?.layout || "vitrina";
	const KEEP = new Set([...COMMON, ...(BY_LAYOUT[layout()] || BY_LAYOUT.vitrina)]);
	const LAYOUT_LABELS = {
		katalog: {
			standard_rate: "Chakana narx (1 dona)",
			variant_price: "Chakana narx (barcha variantlarga)",
			wholesale_price: "Ulgurji narx (1 dona)",
			wholesale_min_qty: "Ulgurji narx: kamida necha dona",
			spec_line: "Qisqa xususiyat (o'lcham, material)",
			has_variants: "O'lcham / rang variantlari bor",
		},
		story: {
			gallery: "Rasmlar va video (birinchi rasm — asosiy; video bo‘lsa «Video» ustuniga — saytda birinchi chiqadi)",
		},
	};
	const LABELS = {
		item_name: "Tovar nomi",
		item_group: "Kategoriya",
		image: "Asosiy rasm",
		standard_rate: "Sotish narxi",
		disabled: "Sotuvdan olingan",
		description: "Tavsif",
		has_variants: "Rang / o'lcham variantlari bor",
		attributes: "Variant turlari",
	};
	const LAYOUT = ["Section Break", "Column Break", "Tab Break"];

	frappe.ui.form.on("Item", {
		refresh(frm) {
			if (!is_seller()) return;
			for (const df of frm.meta.fields) {
				if (LAYOUT.includes(df.fieldtype)) continue;
				if (KEEP.has(df.fieldname)) {
					const label = (LAYOUT_LABELS[layout()] || {})[df.fieldname] || LABELS[df.fieldname];
					if (label) frm.set_df_property(df.fieldname, "label", label);
				} else {
					frm.set_df_property(df.fieldname, "hidden", 1);
				}
			}
			// Kod nomdan avtomatik yasaladi (permissions.item_before_insert)
			frm.set_df_property("item_code", "reqd", 0);
			frm.set_df_property("item_code", "hidden", 1);
			// "Variant turlari" jadvalini server Ranglar/O'lchamlar maydonlaridan to'ldiradi
			// (seller_desk.item_default_attributes), brauzer uni majburiy deb to'xtatmasin
			frm.set_df_property("attributes", "mandatory_depends_on", "");
			frm.set_df_property("attributes", "reqd", 0);
			toggle_variant_fields(frm);
			name_media_tab(frm);
			// MXIK va qadoq kodi kategoriyadan olinadi (permissions.item_validate) — faqat ko'rinadi
			for (const f of ["mxik_code", "package_code"]) {
				frm.set_df_property(f, "read_only", 1);
				frm.set_df_property(f, "description", "Kategoriyadan avtomatik olinadi. O'zgartirish — kategoriyaning o'zida");
			}

			// ERPNext'ning ombor/hisob tugmalari sotuvchiga kerak emas
			frm.remove_custom_button(__("Set Opening Stock"), __("Actions"));

			frm.add_custom_button("📦 Ombor / kirim", () => open_ombor_tab(frm));
		},
	});
	// Ombor tabi hamma uchun (sotuvchi ham, admin ham)
	frappe.ui.form.on("Item", {
		refresh(frm) {
			setup_kirim_grid(frm);
			setup_supplier(frm);
			render_ombor(frm);
			render_variant_prices(frm);
			// Instagram reklama formasi uchun havola (sotuv/murojaat.py): murojaat shu tovar bo'yicha tushadi
			if (!frm.is_new() && !frm.doc.variant_of && (frappe.user.has_role("Shop Seller") || frappe.user.has_role("System Manager") || frappe.user.has_role("Marketplace Manager"))) {
				frm.add_custom_button("📣 SMM havolasi", () => show_smm_link(frm));
			}
			// Ombor sahifasidan "Kirim qilish" bosilgan bo'lsa — to'g'ri Ombor tabiga
			if (window.mp?.open_ombor_of === frm.doc.name) {
				mp.open_ombor_of = null;
				setTimeout(() => open_ombor_tab(frm), 100);
			}
		},
		has_variants(frm) {
			if (is_seller()) {
				toggle_variant_fields(frm);
				frm.refresh();
			} else {
				setup_kirim_grid(frm);
			}
		},
		ranglar: (frm) => setup_kirim_grid(frm),
		// Kategoriya tanlanganda MXIK darhol ko'rinsin (saqlashda server baribir kategoriyadan qo'yadi)
		async item_group(frm) {
			if (!frm.doc.item_group) return;
			const { message: g } = await frappe.db.get_value("Item Group", frm.doc.item_group, ["mxik_code", "package_code"]);
			if (g?.mxik_code) {
				frm.set_value("mxik_code", g.mxik_code);
				frm.set_value("package_code", g.package_code || "");
			} else if (is_seller()) {
				frappe.show_alert({ message: `«${frm.doc.item_group}» kategoriyasida MXIK kodi yo'q — kategoriyani ochib kiriting`, indicator: "orange" });
			}
		},
		// Kirimni keyin o'zgartirib bo'lmaydi: saqlashdan oldin kimdan, sonlar va narxlarni tasdiqlatamiz
		before_save(frm) {
			const rows = (frm.doc.mp_kirim || []).filter((r) => r.soni > 0);
			if (!rows.length) return;
			const esc = frappe.utils.escape_html;
			const id = frm.doc.mp_kirim_kontragent;
			const supplier = id && (frappe.utils.get_link_title("Kontragent", id) || id);
			const missing = !supplier
				? "Tovar qaysi kontragentdan olinganini tanlang («Kimdan olindi»)"
				: rows.some((r) => !(r.narx > 0))
				? "Har bir qatorda 1 donasi necha puldan olinganini yozing"
				: "";
			if (missing) {
				frappe.validated = false;
				frappe.msgprint({ title: "Kirim", message: missing, indicator: "orange" });
				open_ombor_tab(frm);
				return;
			}
			const total = rows.reduce((a, r) => a + r.soni, 0);
			const sum = rows.reduce((a, r) => a + r.soni * r.narx, 0);
			const list = rows
				.map((r) => `<li>${esc([r.rang && (frappe.utils.get_link_title("Rang", r.rang) || r.rang), r.olcham].filter(Boolean).join(" · ") || frm.doc.item_name || "")}: <b>+${r.soni}</b> × ${money(r.narx)}</li>`)
				.join("");
			return new Promise((resolve) => {
				let done = false;
				frappe.confirm(
					`Kimdan: <b>${esc(supplier)}</b><br>Omborga jami <b>+${total}</b> dona, <b>${money(sum)}</b> kirim qilinadi:<ul style="margin:8px 0">${list}</ul>Kirimni keyin o'zgartirib yoki o'chirib bo'lmaydi — sonlar va narxlar to'g'rimi?`,
					() => { done = true; resolve(); },
					() => { if (!done) { done = true; frappe.validated = false; resolve(); } },
					"Ha, kirim qilinsin",
					"Yo'q, tekshiraman"
				);
			});
		},
	});

	// Kirim jadvali: odatda bir partiya bir xil narxda keladi — yangi qatorga oldingi qator narxi tushadi.
	// Jadval ostida: jami nechta dona va necha so'mlik kirim
	frappe.ui.form.on("Tovar Kirimi", {
		mp_kirim_add(frm, cdt, cdn) {
			const row = locals[cdt][cdn];
			const prev = (frm.doc.mp_kirim || []).find((r) => r.idx === row.idx - 1);
			if (prev?.narx && !row.narx) frappe.model.set_value(cdt, cdn, "narx", prev.narx);
			show_kirim_total(frm);
		},
		mp_kirim_remove: (frm) => show_kirim_total(frm),
		soni: (frm) => show_kirim_total(frm),
		narx: (frm) => show_kirim_total(frm),
	});

	const money = (x) => `${format_number(x || 0, null, 0)} so‘m`;

	function show_kirim_total(frm) {
		const $field = frm.fields_dict.mp_kirim?.$wrapper;
		if (!$field) return;
		let $total = $field.find(".mp-kirim-total");
		if (!$total.length) $total = $(`<div class="mp-kirim-total text-muted small" style="margin-top:6px"></div>`).appendTo($field);
		const rows = frm.doc.mp_kirim || [];
		const qty = rows.reduce((a, r) => a + (r.soni || 0), 0);
		const sum = rows.reduce((a, r) => a + (r.soni || 0) * (r.narx || 0), 0);
		$total.html(qty ? `Jami: <b>+${format_number(qty, null, 0)}</b> dona · <b>${money(sum)}</b>` : "");
	}

	// «Kimdan olindi»: faqat shu do'konning kontragentlari. Ro'yxatda yo'q bo'lsa — "+ yangi" kichik oynasi,
	// unda do'kon tovarnikidan olinadi (admin boshqa do'kon tovarini ochgan bo'lsa ham to'g'ri do'konga yoziladi)
	function setup_supplier(frm) {
		const control = frm.fields_dict.mp_kirim_kontragent;
		if (!control) return;
		frm.set_query("mp_kirim_kontragent", () => (frm.doc.shop ? { filters: { shop: frm.doc.shop } } : {}));
		control.get_route_options_for_new_doc = () => (frm.doc.shop ? { shop: frm.doc.shop } : {});
		show_kirim_total(frm);
	}

	// Standart narx tagida: "Rang/o'lcham bo'yicha narx" tugmasi va nechta variantda alohida narx borligi
	async function render_variant_prices(frm) {
		const $box = frm.fields_dict.mp_narxlar_html?.$wrapper;
		if (!$box) return;
		if (!frm.doc.has_variants) return $box.empty();
		if (frm.is_new()) {
			$box.html(`<div class="text-muted small">Saqlab, kirim qilganingizdan keyin har bir rang/o'lchamga alohida narx qo'ysa bo'ladi.</div>`);
			return;
		}
		const name = frm.doc.name;
		const own = await frappe.db.count("Item", { filters: { variant_of: name, mp_own_price: 1 } });
		if (frm.doc.name !== name) return;
		$box.html(`<div style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:-4px 0 8px">
			<button class="btn btn-default btn-xs" data-vprice>Rang/o'lcham bo'yicha narx</button>
			<span class="text-muted small">${own ? `${own} ta rang/o'lchamda alohida narx` : "Hamma rang/o'lcham standart narxda"}</span>
		</div>`);
		$box.find("[data-vprice]").on("click", () => open_variant_prices(frm));
	}

	// Oyna: har bir rang/o'lcham — omborda nechta, olish narxi (oxirgi kirimdan), sotish narxi.
	// Bo'sh katak — standart narx. "Olish narxiga + N" — olish narxi bor qatorlarga sotish narxini yozib beradi
	async function open_variant_prices(frm) {
		if (frm.is_dirty()) return frappe.msgprint("Avval tovarni saqlang, keyin narx qo'yasiz");
		const data = await frappe.xcall("marketplace.seller_desk.get_variant_prices", { template: frm.doc.name });
		if (!data.rows.length) {
			return frappe.msgprint("Hali rang/o'lcham yo'q: ular kirimdan paydo bo'ladi. Avval Ombor tabida kirim qiling.");
		}
		const esc = frappe.utils.escape_html;
		const n = (x) => format_number(x || 0, null, 0);
		const parse = (v) => +String(v || "").replace(/\D/g, "") || 0;
		const label = (r) => [r.color, r.size].filter(Boolean).join(" · ") || frm.doc.item_name;
		const row_html = (r) => `
			<tr>
				<td>${r.color ? `<i style="background:${esc(r.hex || "#ccc")}"></i>` : ""}${esc(label(r))}</td>
				<td class="num">${n(r.qty)}</td>
				<td class="num">${r.cost ? money(r.cost) : "—"}</td>
				<td><input class="form-control input-xs" inputmode="numeric" data-price="${esc(r.code)}"
					value="${r.own ? n(r.price) : ""}" placeholder="${n(r.price || data.standard)} (standart)"></td>
			</tr>`;
		const d = new frappe.ui.Dialog({
			title: `${frm.doc.item_name}: rang/o'lcham bo'yicha narx`,
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: "Saqlash",
			async primary_action() {
				const prices = {};
				d.$wrapper.find("[data-price]").each((_, el) => {
					const r = data.rows.find((x) => x.code === el.dataset.price);
					const value = parse(el.value);
					if (value !== (r.own ? r.price : 0)) prices[r.code] = value || null;
				});
				if (!Object.keys(prices).length) return d.hide();
				await frappe.xcall("marketplace.seller_desk.set_variant_prices", { template: frm.doc.name, prices });
				d.hide();
				frappe.show_alert({ message: "Narxlar saqlandi", indicator: "green" });
				render_variant_prices(frm);
			},
		});
		d.fields_dict.body.$wrapper.html(`
			<style>
				.mp-vp__tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; font-size: var(--text-sm); }
				.mp-vp__tools input { width: 110px; }
				.mp-vp__scroll { overflow-x: auto; }
				.mp-vp__table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
				.mp-vp__table th { color: var(--text-muted); font-weight: 600; text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
				.mp-vp__table td { padding: 6px 8px; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
				.mp-vp__table .num { text-align: right; }
				.mp-vp__table td i { display: inline-block; width: 12px; height: 12px; margin-right: 6px; border-radius: 50%; border: 1px solid var(--border-color); vertical-align: -1px; }
				.mp-vp__table input { min-width: 130px; text-align: right; }
			</style>
			<div class="mp-vp__tools">
				<span>Olish narxiga</span>
				<input class="form-control input-xs" inputmode="numeric" placeholder="10 000" data-markup>
				<span>so'm qo'shib</span>
				<button class="btn btn-default btn-xs" data-apply>hammasiga yozish</button>
			</div>
			<div class="mp-vp__scroll"><table class="mp-vp__table">
				<thead><tr><th>Rang · O'lcham</th><th class="num">Omborda</th><th class="num">Olish narxi</th><th>Sotish narxi</th></tr></thead>
				<tbody>${data.rows.map(row_html).join("")}</tbody>
			</table></div>
			<p class="text-muted small" style="margin-top:10px">Bo'sh qoldirilsa — standart narx (${money(data.standard)}). Standart narxni keyin o'zgartirsangiz, alohida qo'yilgan narxlar o'zgarmaydi.</p>
		`);
		const $body = d.fields_dict.body.$wrapper;
		// Pul katakchalari: "160000" -> "160 000"
		$body.on("input", "[data-price], [data-markup]", (e) => {
			const value = parse(e.target.value);
			e.target.value = value ? n(value) : "";
		});
		$body.find("[data-apply]").on("click", () => {
			const markup = parse($body.find("[data-markup]").val());
			if (!markup) return frappe.show_alert({ message: "Qancha qo'shishni yozing, masalan 10 000", indicator: "orange" });
			let filled = 0;
			for (const r of data.rows) {
				if (!r.cost) continue;
				$body.find(`[data-price="${CSS.escape(r.code)}"]`).val(n(r.cost + markup));
				filled++;
			}
			frappe.show_alert({
				message: filled ? `${filled} ta qatorga yozildi — tekshirib, Saqlash bosing` : "Olish narxi bor rang/o'lcham yo'q (narxsiz eski kirimlar)",
				indicator: filled ? "blue" : "orange",
			});
		});
		d.show();
	}

	// SMM: Instagram lead-formasi (Instant Form) → Make → murojaat.qabul. Dialog Make'dagi HTTP modul sozlamalarini
	// qatorma-qator beradi; kalit havolada emas, sarlavhada (murojaat.smm_link)
	async function show_smm_link(frm) {
		const r = await frappe.xcall("marketplace.sotuv.murojaat.smm_link", { item: frm.doc.name });
		const d = new frappe.ui.Dialog({
			title: `SMM havolasi: ${r.item_name || frm.doc.item_name}`,
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		render_smm(d, r, frm);
		d.show();
	}

	function render_smm(d, r, frm) {
		const esc = frappe.utils.escape_html;
		// Faqat ism va telefon (CEO): qaysi tovar — URL'da. Make'da qiymatlar 1-moduldan (Watch Leads) tanlab qo'yiladi
		const body = JSON.stringify({ ism: "{{Full name}}", telefon: "{{Phone number}}" }, null, 2);
		const local = /\/\/(localhost|127\.|10\.|192\.168\.)/.test(r.url);
		const curl = `curl -X POST '${r.url}' -H '${r.header}: ${r.kalit}' -H 'Content-Type: application/json' -d '{"ism":"Ali","telefon":"+998901234567"}'`;
		const row = (label, value, copy, extra = "") => `
			<tr><td class="text-muted" style="width:150px;vertical-align:middle">${label}</td>
				<td style="vertical-align:middle"><div style="display:flex;gap:6px;align-items:center">
					<code style="flex:1;word-break:break-all;font-size:12px" ${extra}>${esc(value)}</code>
					${copy ? `<button class="btn btn-default btn-xs" data-copy="${esc(copy)}">Nusxalash</button>` : ""}
				</div></td></tr>`;
		d.fields_dict.body.$wrapper.html(`
			<p>Instagram reklamasidagi forma (<b>Instant Form</b>) to'ldirilganda murojaat <b>shu tovar bo'yicha</b> Sotuv panelining
				«Murojaatlar» bo'limiga tushadi. Har bir tovar (reklama) — o'z havolasi.</p>
			${local ? `<div class="alert alert-warning small">Bu manzil hozir faqat shu kompyuterda ishlaydi — Instagram va Make unga yeta olmaydi.
				Serverdagi saytdan (domen bilan) qayta oching.</div>` : ""}
			<p class="small"><b>Make.com:</b> 1-modul — <b>Facebook Lead Ads → Watch Leads</b> (sahifa va formani tanlang),
				2-modul — <b>HTTP → Make a request</b>, sozlamalari:</p>
			<table class="table table-bordered table-sm small" style="margin-bottom:8px">
				${row("URL", r.url, r.url)}
				${row("Method", "POST")}
				${row("Header: Name", r.header, r.header)}
				${row("Header: Value", "•".repeat(12), r.kalit, "data-key")}
				${row("Body type", "Raw · JSON (application/json)")}
			</table>
			<div style="display:flex;justify-content:space-between;align-items:center">
				<span class="small"><b>Request content</b> — qiymatlarni 1-moduldan tanlab qo'ying:</span>
				<button class="btn btn-default btn-xs" data-copy="${esc(body)}">Nusxalash</button>
			</div>
			<pre style="font-size:12px;margin-top:4px">${esc(body)}</pre>
			<p class="text-muted small">Faqat 2 ta maydon: <code>ism</code> va <code>telefon</code> (majburiy faqat telefon). Qaysi tovar ekani URL'da —
				tanada shart emas. Bir xil mijoz 10 daqiqa ichida qayta yuborilsa, ikkinchi marta yozilmaydi.</p>
			<p class="text-muted small"><b>Tekshirish:</b> Meta'ning «Lead Ads Testing Tool»ida sinov lead yuboring — murojaat «Murojaatlar»da chiqadi,
				Make'dagi javobda esa <code>tovar_nomi</code> ko'rinadi.</p>
			<details class="small text-muted"><summary>Dasturchi uchun sinov (curl)</summary>
				<pre style="font-size:11px;white-space:pre-wrap;word-break:break-all;margin-top:6px">${esc(curl)}</pre></details>
			<div class="alert alert-warning small" style="margin-top:12px;display:flex;gap:10px;align-items:center;justify-content:space-between">
				<span>Kalit — do'kon paroli kabi: faqat Make'ga qo'ying, chat va hujjatlarga yozmang. Begona qo'lga o'tgan bo'lsa — yangilang.</span>
				<button class="btn btn-default btn-xs" data-reset>Kalitni yangilash</button>
			</div>`);
		const $w = d.fields_dict.body.$wrapper;
		$w.find("[data-copy]").on("click", (e) => frappe.utils.copy_to_clipboard($(e.currentTarget).attr("data-copy")));
		// Kalit ekranda ochiq turmasin: bosilsa ko'rinadi
		$w.find("[data-key]").css("cursor", "pointer").attr("title", "Ko'rsatish").one("click", (e) => $(e.currentTarget).text(r.kalit));
		$w.find("[data-reset]").on("click", () =>
			frappe.confirm("Eski kalit darhol ishlamay qoladi — Make'dagi Header: Value'ni yangisiga almashtirish kerak. Davom etilsinmi?", async () => {
				const fresh = await frappe.xcall("marketplace.sotuv.murojaat.reset_smm_key", { item: frm.doc.name });
				render_smm(d, fresh, frm);
				frappe.show_alert({ message: "Yangi kalit yaratildi — Make'ga qo'ying", indicator: "green" });
			})
		);
	}

	// Variantli tovarda narx variant_price'ga yoziladi (ERPNext andozaga narx qo'ymaydi), qoldiq esa har variantda
	function toggle_variant_fields(frm) {
		const v = !!frm.doc.has_variants;
		frm.toggle_display("standard_rate", !v);
		frm.toggle_display("variant_price", v);
		if (v && frm.doc.standard_rate && !frm.doc.variant_price) {
			frm.set_value("variant_price", frm.doc.standard_rate);
			frm.set_value("standard_rate", 0);
		}
	}

	// Rasmlar va MXIK custom maydonlari ERPNext'ning "Accounting" tabiga tushib qolgan: tabni nomlaymiz
	function name_media_tab(frm) {
		let tab = null;
		for (const df of frm.meta.fields) {
			if (df.fieldtype === "Tab Break") tab = df.fieldname;
			if (df.fieldname === "sb_gallery") break;
		}
		if (tab) frm.set_df_property(tab, "label", "Rasmlar va MXIK");
	}

	const split_list = (v) => (v || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);

	function open_ombor_tab(frm) {
		const tab = frm.layout?.tabs?.find((t) => t.df.fieldname === "mp_ombor_tab");
		if (tab) {
			tab.set_active();
			frm.fields_dict.mp_kirim?.$wrapper.get(0)?.scrollIntoView({ block: "center", behavior: "smooth" });
		}
	}

	// Kirim jadvali: variantli tovarda Rang / O'lcham / Nechta keldi / Narxi, oddiy tovarda — son va narx.
	// Galereyada "Rang" ustuni: rasm qaysi rangniki (saytda shu rang bosilganda chiqadi)
	async function setup_kirim_grid(frm) {
		const grid = frm.fields_dict.mp_kirim?.grid;
		if (!grid) return;
		const v = !!frm.doc.has_variants;
		const colors = (frm.doc.ranglar || []).map((r) => r.rang).filter(Boolean);
		frm.set_query("rang", "gallery", () => (colors.length ? { filters: { name: ["in", colors] } } : {}));
		if (frm._mp_grid_mode !== v) {
			frm._mp_grid_mode = v;
			for (const f of ["rang", "olcham"]) grid.update_docfield_property(f, "hidden", v ? 0 : 1);
			grid.reset_grid();
			const gallery = frm.fields_dict.gallery?.grid;
			if (gallery?.docfields.some((d) => d.fieldname === "rang")) {
				gallery.update_docfield_property("rang", "hidden", v ? 0 : 1);
				gallery.reset_grid();
			}
		}
		const label = v ? "Qaysi rang, qaysi o'lcham, nechta keldi, necha puldan" : "Nechta keldi, necha puldan";
		const help = v
			? "Har bir rang va o'lcham — alohida qator: masalan Qora · 42 · 15 ta · 120 000, keyin Oq · 43 · 10 ta. Narx — 1 donasini necha puldan olganingiz (yangi qatorga oldingi narx o'zi tushadi). O'lchamni ro'yxatdan tanlang yoki yangisini yozing (masalan 42) — tovarga o'zi qo'shiladi. Do'koningiz o'lchamlari ro'yxati: chapdagi menyu → O'lchamlar. Saqlaganda omborga qo'shiladi."
			: "Kelgan sonni va 1 donasini necha puldan olganingizni yozing, Saqlash bosing — omborga qo'shiladi va kirim tarixiga yoziladi.";
		frm.set_df_property("mp_kirim", "label", label);
		frm.set_df_property("mp_kirim", "description", help);
		// Jadval sarlavhasi va izohi bir marta chiziladi: df o'zgargani bilan ekrandagi matn yangilanmaydi
		const $field = frm.fields_dict.mp_kirim.$wrapper;
		$field.find(".control-label").first().text(label);
		$field.find(".grid-description").first().text(help);
		grid.wrapper.find(".grid-add-row").text("+ Qator qo'shish");
		if (v) {
			frm._mp_sizes = frm._mp_sizes || (await frappe.xcall("marketplace.seller_desk.get_variant_options", { template: null })).sizes;
			grid.update_docfield_property("olcham", "options", [...new Set([...split_list(frm.doc.variant_sizes), ...frm._mp_sizes])]);
			// Ro'yxatda yo'q o'lcham ham yozilsin (42, 128GB): Autocomplete aks holda uni jimgina o'chiradi
			grid.update_docfield_property("olcham", "ignore_validation", 1);
		}
	}

	// Ombor tabi: omborda hozir nechta (rang × o'lcham) va kirim tarixi — faqat ko'rish.
	// Sotuvlar tarixga yozilmaydi: ular qoldiqni o'zi kamaytiradi
	async function render_ombor(frm) {
		const $stock = frm.fields_dict.mp_ombor_html?.$wrapper;
		const $log = frm.fields_dict.mp_ombor_log?.$wrapper;
		if (!$stock || !$log) return;
		if (frm.is_new()) {
			$stock.html(`<div class="text-muted small" style="padding:6px 0">Qaysi kontragentdan olganingizni tanlang, pastdagi jadvalga ${frm.doc.has_variants ? "har bir rang va o'lchamdan " : ""}nechta kelganini va necha puldan olganingizni yozing, Saqlash bosing — omborga qo'shiladi.</div>`);
			$log.html("");
			return;
		}
		const name = frm.doc.name;
		const [stock, log] = await Promise.all([
			frm.doc.has_variants
				? frappe.xcall("marketplace.seller_desk.get_variant_matrix", { template: name })
				: frappe.xcall("marketplace.seller_desk.get_item_stock", { item_code: name }),
			frappe.xcall("marketplace.seller_desk.get_item_ledger", { item_code: name }),
		]);
		if (frm.doc.name !== name) return;
		let total;
		if (frm.doc.has_variants) {
			$stock.html(mp.stock_grid(stock));
			total = Object.values(stock.cells || {}).reduce((a, c) => a + Math.max(c.qty, 0), 0);
		} else {
			total = stock;
			$stock.html(`<div class="mp-sg__total" style="padding:6px 0">Omborda hozir: <b>${format_number(stock, null, 0)}</b> dona</div>`);
		}
		$log.html(mp.journal(log, { empty: "Hali kirim bo'lmagan" }));
		if (is_seller() && frm.doc.is_stock_item !== 0) {
			frm.dashboard.clear_headline();
			frm.dashboard.set_headline(
				total > 0
					? `Omborda: <b>${format_number(total, null, 0)}</b> dona. Yangi tovar kelsa — <b>Ombor</b> tabida kirim qiling.`
					: `<span class="text-danger">Omborda qolmagan.</span> Yangi tovar kelsa — <b>Ombor</b> tabida kirim qiling.`
			);
		}
	}
})();
