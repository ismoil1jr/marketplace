// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.ui.form.on("Instagram Xabar", {
	refresh(frm) {
		if (frm.is_new()) return;
		const call = (method) =>
			frappe.call({ method: `marketplace.sotuv.instagram.${method}`, args: { name: frm.doc.name }, freeze: true })
				.then(() => frm.reload_doc());
		if (["Qoralama", "Xato"].includes(frm.doc.holat) && frm.doc.ai_javob) {
			frm.add_custom_button(__("Yuborish"), () => call("send")).addClass("btn-primary");
		}
		if (frm.doc.holat !== "Yuborildi") {
			frm.add_custom_button(__("AI javobini qayta yozish"), () => call("regenerate"));
		}
	},
});
