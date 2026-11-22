// Hamkorlik shartnomasi: saqlanganda PDF o'zi yaratiladi (server), bu yerda — yuklab olish tugmalari
// va saytdagi do'kon tanlansa nomi/STIR to'ldiriladi.
frappe.ui.form.on("Hamkorlik", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.obuna_narxi && !frm.doc.komissiya_foizi) {
			frappe.call("marketplace.marketplace.doctype.hamkorlik.hamkorlik.standart_narx").then((r) => {
				if (r.message) frm.set_value(r.message);
			});
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.pdf_fayl) {
			frm.add_custom_button(__("PDF yuklab olish"), () => window.open(frm.doc.pdf_fayl, "_blank")).addClass("btn-primary");
		}
		// Frappe'ning o'z PDF'i (Print Format «Hamkorlik shartnomasi», Chrome)
		frm.add_custom_button(__("Frappe PDF"), () => {
			const q = new URLSearchParams({
				doctype: frm.doc.doctype, name: frm.doc.name, format: "Hamkorlik shartnomasi",
				no_letterhead: 1, pdf_generator: "chrome",
			});
			window.open(`/api/method/frappe.utils.print_format.download_pdf?${q}`, "_blank");
		});
		if (frm.doc.holat !== "Bekor qilingan") {
			frm.add_custom_button(__("Bekor qilish"), () => {
				frappe.confirm(__("Shartnoma bekor qilinsinmi?"), () => frm.set_value("holat", "Bekor qilingan").then(() => frm.save()));
			}, __("Amallar"));
		}
	},

	async shop(frm) {
		if (!frm.doc.shop) return;
		const { message: s } = await frappe.db.get_value("Shop", frm.doc.shop, ["shop_name", "legal_name", "stir"]);
		if (!s) return;
		if (!frm.doc.dokon_nomi) frm.set_value("dokon_nomi", s.shop_name);
		if (s.stir && !frm.doc.stir) {
			if (frm.doc.huquqiy_shakl === "Jismoniy shaxs") frm.set_value("huquqiy_shakl", s.stir.length === 9 ? "MChJ" : "YaTT");
			frm.set_value("stir", s.stir);
		}
		if (s.legal_name && !frm.doc.tashkilot_nomi) frm.set_value("tashkilot_nomi", s.legal_name);
	},
});
