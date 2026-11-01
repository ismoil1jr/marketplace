// Telefoniya sozlamalari: AI (Gemini) transkripsiya ishlayaptimi, ishlamasa NEGA — va eski yozuvlarni navbatga qo'yish.
// Ikkita o'chirgich bor (AI yoqilgan + API kalit), shuning uchun "yoqdim, lekin ishlamaydi" holatini panel aniq aytadi (sotuv/stt.py)
frappe.ui.form.on("Telefoniya Sozlamalari", {
	refresh(frm) {
		draw_status(frm);
		frm.add_custom_button(__("Eski yozuvlarni transkripsiya qilish"), () =>
			frappe.confirm(
				__("Transkripti yo‘q barcha yozuvlar navbatga qo‘yiladi. Har biri uchun Gemini API to‘lovi ketadi. Davom etamizmi?"),
				async () => {
					const r = await frappe.xcall("marketplace.sotuv.stt.transcribe_all");
					frappe.msgprint({
						title: __("Navbatga qo‘yildi"), indicator: "green",
						message: __("{0} ta yozuv navbatga qo‘yildi. Fonda ishlaydi — bir necha daqiqadan keyin qo‘ng‘iroqlar ro‘yxatini yangilang.", [r.navbatga_qoyildi]),
					});
					draw_status(frm);
				}
			), __("AI"));
	},
	after_save(frm) {
		draw_status(frm);
	},
});

async function draw_status(frm) {
	const field = frm.get_field("stt_holat_html");
	if (!field) return;
	const d = await frappe.xcall("marketplace.sotuv.stt.status");
	const esc = frappe.utils.escape_html;
	const head = d.ishlayapti
		? `<div style="color:var(--green-600);font-weight:600">${__("Avto transkripsiya yoqilgan")}</div>
			<div class="text-muted small">${__("Yangi yozuv kelishi bilan o‘zi matnga aylanadi va qisqa tahlil yoziladi — tugma bosish shart emas.")}</div>`
		: `<div style="color:var(--red-600);font-weight:600">${__("Avto transkripsiya o‘chiq")}</div>
			<ul class="small" style="margin:4px 0 0 18px">${d.sabablar.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
	field.$wrapper.html(`
		<div style="border:1px solid var(--border-color);border-radius:var(--border-radius-md);padding:10px 12px;margin-bottom:12px">
			${head}
			<div class="small" style="margin-top:8px;display:flex;gap:18px;flex-wrap:wrap">
				<span>${__("Yozuvli qo‘ng‘iroq")}: <b>${d.jami_yozuv}</b></span>
				<span style="color:var(--green-600)">${__("Transkript bor")}: <b>${d.transkript_bor}</b></span>
				<span style="color:var(--orange-600)">${__("Navbatda")}: <b>${d.navbatda}</b></span>
				<span style="color:var(--red-600)">${__("Xato")}: <b>${d.xato}</b></span>
			</div>
			<div class="text-muted small" style="margin-top:6px">
				${__("Model")}: ${esc(d.model || "—")}${d.zaxira ? ` · ${__("zaxira")}: ${esc(d.zaxira)}` : ""}
				· ${__("o‘tkazib yuborilganlar har 15 daqiqada qayta uriniladi")}
			</div>
			${d.pauza ? `<button class="btn btn-xs btn-default" style="margin-top:8px" data-clear-pause>${__("Kvota pauzasini olib tashlash")}</button>` : ""}
		</div>`);
	field.$wrapper.find("[data-clear-pause]").on("click", async () => {
		await frappe.xcall("marketplace.sotuv.stt.clear_pause");
		frappe.show_alert({ message: __("Pauza olib tashlandi"), indicator: "green" });
		draw_status(frm);
	});
}
