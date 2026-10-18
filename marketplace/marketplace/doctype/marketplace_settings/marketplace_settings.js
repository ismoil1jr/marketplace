// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.ui.form.on("Marketplace Settings", {
	refresh(frm) {
		if (frm.doc.telegram_bot_username) {
			frm.set_intro(
				`Bot: <a href="https://t.me/${frm.doc.telegram_bot_username}" target="_blank">@${frm.doc.telegram_bot_username}</a> · ${frappe.utils.escape_html(frm.doc.telegram_mode || "hali ishga tushmagan")}<br>` +
					`Lokal kompyuterda botni ishga tushirish: <code>bench --site ${frappe.boot.sitename} execute marketplace.telegram_bot.poll</code>`,
				"blue"
			);
			frm.add_custom_button("Webhook'ni o'rnatish (server)", () =>
				frappe.xcall("marketplace.telegram_bot.set_webhook").then((url) => {
					frappe.msgprint(`Webhook o'rnatildi:<br><code>${url}</code>`);
					frm.reload_doc();
				}),
				"Telegram bot"
			);
			if (frm.doc.telegram_admin_id) {
				frm.add_custom_button("Sinov xabari (admin)", () =>
					frappe
						.xcall("marketplace.telegram_bot.send_test", { chat_id: frm.doc.telegram_admin_id.split(",")[0].trim() })
						.then(() => frappe.show_alert({ message: "Yuborildi — Telegram'ni tekshiring", indicator: "green" })),
					"Telegram bot"
				);
			}
		}
	},
});
