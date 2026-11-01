// Qo'ng'iroq formasi: yozuv — Telegram'dagi ovozli xabar kabi (mp.voice_note, public/js/voice_note.js);
// AI: transkript va qisqa tahlil (sotuv/stt.py) — yozuv kelganda o'zi, kerak bo'lsa shu yerdan qo'lda
frappe.ui.form.on("Telefon Qongiroq", {
	refresh(frm) {
		frm.toggle_display("yozuv", !frm.doc.yozuv);
		const $box = frm.fields_dict.yozuv_html?.$wrapper;
		if ($box) {
			if (!frm.doc.yozuv) {
				$box.html(`<div class="text-muted small">${frm.doc.yozuv_ochirildi ? __("Yozuv saqlash muddati tugab o‘chirilgan") : __("Yozuv yo‘q")}</div>`);
			} else {
				$box.html(mp.voice_note(frm.doc.yozuv, { date: frappe.datetime.str_to_user(frm.doc.boshlandi) }));
				mp.voice_init($box);
			}
		}
		if (frm.is_new() || !frm.doc.yozuv) return;
		const has = !!frm.doc.transkript;
		frm.add_custom_button(has ? __("Transkriptni yangilash") : __("Transkripsiya qilish"), () => {
			const run = () =>
				frappe.call({
					method: "marketplace.sotuv.stt.transcribe_now",
					args: { qongiroq: frm.doc.name },
					freeze: true,
					freeze_message: __("Nutq matnga aylantirilmoqda…"),
				}).then(({ message: m }) => {
					if (m.holat === "tayyor") frappe.show_alert({ message: __("Transkript tayyor: {0} so‘z ({1})", [m.sozlar, m.model]), indicator: "green" }, 7);
					else frappe.show_alert({ message: __("Transkripsiya bo‘lmadi: {0}", [m.sabab]), indicator: "orange" }, 10);
					frm.reload_doc();
				});
			has ? frappe.confirm(__("Mavjud transkript ustiga yoziladi. Davom etamizmi?"), run) : run();
		}, __("AI"));
	},
});
