// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.ui.form.on("Instagram Xabar", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method) =>
			frappe.call({ method: `marketplace.sotuv.instagram.${method}`, args: { name: frm.doc.name }, freeze: true })
				.then(() => frm.reload_doc());
		if (["Qoralama", "Xato"].includes(frm.doc.holat) && frm.doc.ai_javob) {
			frm.add_custom_button(__("Yuborish"), async () => {
				// Operator tahrir qilgan matn yuborilsin: server saqlangan matnni yuboradi, shuning uchun avval saqlaymiz
				if (frm.is_dirty()) await frm.save();
				// frm.save() xatoni yutib yuboradi: saqlanmagan bo'lsa (forma hali ham o'zgargan) — eski matn ketmasin
				if (frm.is_dirty()) return;
				const text = (frm.doc.ai_javob || "").trim();
				if (!text) return;
				const question = frm.doc.turi === "DM"
					? __("Javob mijozga Direct'da yuboriladi. Yuborilsinmi?")
					: __("Javob Instagram'da hammaga ko'rinadi. Yuborilsinmi?");
				frappe.confirm(`${question}<br><br><i>${frappe.utils.escape_html(text)}</i>`, () => call("send"));
			}).addClass("btn-primary");
		}
		if (frm.doc.holat !== "Yuborildi") {
			frm.add_custom_button(__("AI javobini qayta yozish"), () => call("regenerate"));
		}
	},
});
