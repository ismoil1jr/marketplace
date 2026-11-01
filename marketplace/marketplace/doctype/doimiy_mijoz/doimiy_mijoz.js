// Doimiy mijoz anketasi: pastda shu do'kondagi barcha xaridlari (buyurtmalardan avtomatik)
// "901234567", "+998901234567", "90 123 45 67" -> "+998 90 123 45 67" (bazada +998901234567 bo'lib saqlanadi)
function format_phone(value) {
	const v = (value || "").trim();
	let d;
	if (v.startsWith("+998")) d = v.slice(4).replace(/\D/g, "");
	else {
		d = v.replace(/\D/g, "");
		// "998901234567" yoki "+998 90..." nusxalab qo'yilsa — kod takrorlanmasin
		if (d.length > 9 && d.startsWith("998")) d = d.slice(3);
		// "+9", "+99" — mijoz +998 ni o'zi yozyapti
		if (v.startsWith("+") && "998".startsWith(d)) d = "";
	}
	d = d.slice(0, 9);
	const parts = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
	return "+998 " + parts.join(" ");
}

function setup_phone_input(frm) {
	const $input = frm.fields_dict.phone.$input;
	if (!$input) return;
	$input.attr({ placeholder: "+998 90 123 45 67", inputmode: "tel", maxlength: 17 });
	if (!$input.data("mp-phone")) {
		$input.data("mp-phone", 1);
		$input.on("focus", () => { if (!$input.val()) $input.val("+998 "); });
		$input.on("input", () => $input.val(format_phone($input.val())));
		$input.on("blur", () => { if ($input.val().replace(/\D/g, "").length <= 3) $input.val(""); });
	}
	if (frm.doc.phone) $input.val(format_phone(frm.doc.phone));
}

// Toshkent shahri tumanlari — ro'yxatdan tanlanadi; boshqa viloyatlarda tuman/shahar qo'lda yoziladi
const MP_TUMANLAR = {
	"Toshkent shahri": ["Bektemir", "Chilonzor", "Mirobod", "Mirzo Ulug‘bek", "Olmazor", "Sergeli", "Shayxontohur", "Uchtepa",
		"Yakkasaroy", "Yangihayot", "Yashnobod", "Yunusobod"],
};

function setup_tuman(frm) {
	const options = MP_TUMANLAR[frm.doc.viloyat] || [];
	frm.set_df_property("tuman", "options", options);
	frm.set_df_property("tuman", "ignore_validation", 1);
	frm.fields_dict.tuman?.set_data?.(options);
}

// Xaritadagi birinchi nuqta (GeoJSON) -> {lat, lng}
function map_point(value) {
	try {
		const f = (JSON.parse(value || "{}").features || []).find((x) => x.geometry?.type === "Point");
		return f ? { lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] } : null;
	} catch (e) {
		return null;
	}
}

function render_map_links(frm) {
	const $w = frm.fields_dict.xarita_html?.$wrapper;
	if (!$w) return;
	const p = map_point(frm.doc.joylashuv);
	const locate = `<button class="btn btn-sm btn-default" data-locate>📍 ${__("Hozirgi joylashuvim")}</button>`;
	const links = p
		? `<a class="btn btn-sm btn-default" target="_blank" rel="noopener" href="https://yandex.uz/maps/?pt=${p.lng},${p.lat}&z=17&l=map">${__("Yandex xaritada ochish")}</a>
			<a class="btn btn-sm btn-default" target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${p.lat},${p.lng}">${__("Google xaritada ochish")}</a>
			<span class="text-muted small">${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}</span>`
		: `<span class="text-muted small">${__("Hali joy belgilanmagan")}</span>`;
	$w.html(`<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:-6px">${locate}${links}</div>`);
	$w.find("[data-locate]").on("click", () => locate_me(frm));
}

// Kuryer mijoz uyida bo'lsa: telefon/planshet GPS'i bilan joyni o'zi qo'yadi (brauzer https yoki localhost'da ruxsat beradi)
function locate_me(frm) {
	if (!navigator.geolocation || !window.isSecureContext) {
		frappe.msgprint(__("Bu brauzer joylashuvni bermaydi: sayt https orqali ochilishi kerak. Hozircha xaritada qo‘lda nuqta qo‘ying."));
		return;
	}
	frappe.show_alert({ message: __("Joylashuv aniqlanmoqda…"), indicator: "blue" });
	navigator.geolocation.getCurrentPosition(
		(pos) => {
			const { latitude: lat, longitude: lng } = pos.coords;
			frm.set_value("joylashuv", JSON.stringify({
				type: "FeatureCollection",
				features: [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [lng, lat] } }],
			}));
			frappe.show_alert({ message: __("Joy belgilandi"), indicator: "green" });
		},
		(err) => frappe.msgprint(__("Joylashuvni olib bo‘lmadi: {0}. Telefonda joylashuv (GPS) yoqilganini va brauzerga ruxsat berilganini tekshiring.", [err.message])),
		{ enableHighAccuracy: true, timeout: 15000 }
	);
}

function child_age(birth) {
	if (!birth) return null;
	const b = frappe.datetime.str_to_obj(birth), t = new Date();
	return t.getFullYear() - b.getFullYear() - (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate()) ? 1 : 0);
}

// Farzand yoshi — sana kiritilishi bilan (saqlashni kutmasdan)
frappe.ui.form.on("Mijoz Farzandi", {
	birth_date(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const age = child_age(row.birth_date);
		frappe.model.set_value(cdt, cdn, "age", age !== null && age >= 0 ? age : null);
	},
	children_remove(frm) {
		frm.set_value("children_count", (frm.doc.children || []).length);
	},
	children_add(frm) {
		frm.set_value("children_count", (frm.doc.children || []).length);
	},
});

frappe.ui.form.on("Doimiy Mijoz", {
	viloyat(frm) {
		setup_tuman(frm);
		if (frm.doc.tuman && !(MP_TUMANLAR[frm.doc.viloyat] || []).includes(frm.doc.tuman) && MP_TUMANLAR[frm.doc.viloyat]) frm.set_value("tuman", "");
	},
	joylashuv(frm) {
		render_map_links(frm);
	},
	refresh(frm) {
		setup_phone_input(frm);
		setup_tuman(frm);
		render_map_links(frm);
		frm.fields_dict.children.grid.wrapper.find(".grid-add-row").text("+ Farzand qo'shish");
		render_purchases(frm);
		if (frm.is_new()) {
			frm.fields_dict.purchases_html.$wrapper.html(
				`<div class="text-muted small">Saqlagandan keyin shu yerda mijozning xaridlari chiqadi.</div>`
			);
		}
	},
});

const PAY_COLORS = { Naqd: "orange", Payme: "blue", Click: "cyan" };
const STATE_COLORS = { delivered: "green", paid: "green", cod: "orange", waiting: "orange", cancelled: "red", closed: "gray" };

async function render_purchases(frm) {
	if (frm.is_new()) return;
	const $w = frm.fields_dict.purchases_html.$wrapper;
	$w.html(`<div class="text-muted small">Yuklanmoqda…</div>`);
	const r = await frappe.xcall("marketplace.marketplace.doctype.doimiy_mijoz.doimiy_mijoz.get_purchases", { name: frm.doc.name });
	const esc = frappe.utils.escape_html;
	const money = (v) => format_currency(v, "UZS", 0);
	if (!r.orders.length) {
		$w.html(`<div class="text-muted">Bu do'konda hali xarid qilmagan.</div>`);
		return;
	}
	const rows = r.orders
		.map(
			(o) => `<tr>
				<td style="white-space:nowrap"><a href="/desk/sales-order/${encodeURIComponent(o.name)}">${esc(o.name)}</a><div class="text-muted small">${esc(o.date)}</div></td>
				<td>${o.items.map((i) => `${esc(i.name)} <b>× ${i.qty}</b>`).join("<br>")}</td>
				<td class="text-right">${o.qty}</td>
				<td class="text-right"><b>${money(o.total)}</b></td>
				<td>${o.payment_method ? `<span class="indicator-pill ${PAY_COLORS[o.payment_method] || "gray"}">${esc(o.payment_method)}</span>` : ""}</td>
				<td style="white-space:nowrap"><span class="indicator-pill ${STATE_COLORS[o.state] || "gray"}">${esc(o.state_label)}</span></td>
			</tr>`
		)
		.join("");
	$w.html(`
		<div class="d-flex flex-wrap" style="gap:24px;margin-bottom:12px">
			<div><div class="text-muted small">Xaridlar soni</div><div class="h4" style="margin:0">${r.count}</div></div>
			<div><div class="text-muted small">Jami summa</div><div class="h4" style="margin:0">${money(r.total)}</div></div>
			<div><div class="text-muted small">Oxirgi buyurtma</div><div class="h4" style="margin:0">${esc(r.last || "—")}</div></div>
		</div>
		<div class="table-responsive"><table class="table table-bordered table-sm" style="margin:0">
			<thead><tr><th>Buyurtma</th><th>Nima oldi</th><th class="text-right">Soni</th><th class="text-right">Summa</th><th>To'lov</th><th>Holati</th></tr></thead>
			<tbody>${rows}</tbody>
		</table></div>`);
}
