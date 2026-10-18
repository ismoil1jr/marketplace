// Sotuvchi uchun Item formasi: ERPNext'ning o'zi, faqat keraksiz maydonlar yashirilgan.
// Admin va Marketplace Manager to'liq formani ko'radi.
(() => {
	const is_seller = () =>
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;

	// Hamma shablonda ko'rinadigan maydonlar
	const COMMON = [
		"item_name", "item_group", "image", "standard_rate", "variant_price", "ranglar", "variant_sizes", "variant_qty",
		"opening_stock", "disabled", "description", "has_variants", "variant_of", "is_published",
		"gallery", "mxik_code", "package_code",
	];
	// Do'kon shabloniga qarab qo'shimcha maydonlar: sayt aynan shularni ko'rsatadi
	//   vitrina (A) — kiyim va oddiy chakana: chegirma, karusel
	//   story (B)   — Instagram uslubi, katta rasmlar: chegirma (karusel bu shablonda yo'q)
	//   katalog (C) — zavod va ulgurji: ulgurji narx, kamida nechta, qisqa xususiyat
	const BY_LAYOUT = {
		vitrina: ["old_price", "in_carousel", "carousel_label"],
		story: ["old_price"],
		katalog: ["wholesale_price", "wholesale_min_qty", "spec_line"],
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
			gallery: "Rasmlar (birinchisi — asosiy, kvadrat yoki vertikal rasm yaxshi chiqadi)",
		},
	};
	const LABELS = {
		item_name: "Tovar nomi",
		item_group: "Kategoriya",
		image: "Asosiy rasm",
		standard_rate: "Sotish narxi",
		opening_stock: "Omborda nechta bor",
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
			frm.set_df_property("opening_stock", "description", "Saqlaganingizda shu son do'kon omboriga yoziladi");
			// Kod nomdan avtomatik yasaladi (permissions.item_before_insert)
			frm.set_df_property("item_code", "reqd", 0);
			frm.set_df_property("item_code", "hidden", 1);
			// "Variant turlari" jadvalini server Ranglar/O'lchamlar maydonlaridan to'ldiradi
			// (seller_desk.item_default_attributes), brauzer uni majburiy deb to'xtatmasin
			frm.set_df_property("attributes", "mandatory_depends_on", "");
			frm.set_df_property("attributes", "reqd", 0);
			toggle_variant_fields(frm);
			name_media_tab(frm);

			// ERPNext'ning ombor/hisob tugmalari sotuvchiga kerak emas
			frm.remove_custom_button(__("Set Opening Stock"), __("Actions"));

			if (frm.doc.has_variants) {
				frm.add_custom_button("Rang / o'lcham tanlash", () => variants_dialog(frm));
				if (!frm.is_new()) frm.add_custom_button("Variantlar qoldig'i", () => variants_stock(frm));
				frm.dashboard.set_headline(
					frm.is_new()
						? "Ranglar va o'lchamlarni yozing (yoki <b>Rang / o'lcham tanlash</b>), keyin <b>Saqlash</b> — variantlar o'zi yaratiladi."
						: "Yangi rang/o'lcham qo'shsangiz, saqlaganda variantlari yaratiladi. Sonini <b>Variantlar qoldig'i</b>da kiriting."
				);
			}

			if (!frm.is_new() && !frm.doc.has_variants && frm.doc.is_stock_item) {
				frm.add_custom_button("Qoldiqni o'zgartirish", () => change_stock(frm));
				frappe
					.xcall("marketplace.seller_desk.get_item_stock", { item_code: frm.doc.name })
					.then((qty) => {
						frm.dashboard.clear_headline();
						frm.dashboard.set_headline(
							qty > 0
								? `Omborda: <b>${qty}</b> ta`
								: `<span class="text-danger">Omborda qolmagan</span> — "Qoldiqni o'zgartirish" tugmasi bilan qo'shing`
						);
					});
			}
		},
	});

	frappe.ui.form.on("Item", "has_variants", (frm) => is_seller() && (toggle_variant_fields(frm), frm.refresh()));

	// Variantli tovarda narx variant_price'ga yoziladi (ERPNext andozaga narx qo'ymaydi), qoldiq esa har variantda
	function toggle_variant_fields(frm) {
		const v = !!frm.doc.has_variants;
		frm.toggle_display("standard_rate", !v);
		frm.toggle_display("variant_price", v);
		if (v) frm.toggle_display("opening_stock", false);
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

	// Rang va o'lcham tanlash: ro'yxatdan belgilash yoki o'zi yozish (yangi nomlar avtomatik qo'shiladi)
	function variants_dialog(frm) {
		const split = (v) => (v || "").split(/[,\n]/).map((x) => x.trim()).filter(Boolean);
		frappe.xcall("marketplace.seller_desk.get_variant_options", { template: frm.is_new() ? null : frm.doc.name }).then((o) => {
			const have_c = (frm.doc.ranglar || []).map((r) => r.rang);
			const have_s = split(frm.doc.variant_sizes);
			const opts = (list, used) => list.map((v) => ({ label: v, value: v, checked: used.includes(v) }));
			const extra = (have, list) => have.filter((v) => !list.includes(v)).join(", ");
			const d = new frappe.ui.Dialog({
				title: "Rang va o'lcham",
				size: "large",
				fields: [
					{ fieldname: "colors", fieldtype: "MultiCheck", label: "Ranglar", columns: 4, options: opts(o.colors, have_c) },
					{ fieldname: "new_colors", fieldtype: "Data", label: "Yangi rang (vergul bilan)", placeholder: "Masalan: Bordo, Olcha" },
					{ fieldtype: "Section Break" },
					{ fieldname: "sizes", fieldtype: "MultiCheck", label: "O'lchamlar", columns: 6, options: opts(o.sizes, have_s) },
					{ fieldname: "new_sizes", fieldtype: "Data", label: "Boshqa o'lcham (vergul bilan)", default: extra(have_s, o.sizes), placeholder: "Masalan: 42, 44, 46 yoki 110 sm" },
				],
				primary_action_label: "Tayyor",
				async primary_action(v) {
					// Yangi ranglar Rang ro'yxatiga qo'shiladi, keyin jadvalga
					const fresh = split(v.new_colors).filter((c) => !o.colors.some((x) => x.toLowerCase() === c.toLowerCase()));
					for (const c of fresh) await frappe.db.insert({ doctype: "Rang", rang_nomi: c });
					const colors = [...new Set([...(v.colors || []), ...split(v.new_colors)])];
					frm.clear_table("ranglar");
					colors.forEach((c) => frm.add_child("ranglar", { rang: c }));
					frm.refresh_field("ranglar");
					frm.set_value("variant_sizes", [...(v.sizes || []), ...split(v.new_sizes)].join(", "));
					d.hide();
					frappe.show_alert({ message: "Endi Saqlash bosing — variantlar yaratiladi", indicator: "blue" });
				},
			});
			d.show();
		});
	}

	function variants_stock(frm) {
		frappe.xcall("marketplace.seller_desk.get_variants_stock", { template: frm.doc.name }).then((rows) => {
			if (!rows.length) {
				frappe.msgprint("Avval <b>Variantlar yaratish</b> tugmasi bilan rang/o'lchamlarni tanlang.");
				return;
			}
			const d = new frappe.ui.Dialog({
				title: "Variantlar qoldig'i",
				size: "large",
				fields: [
					{
						fieldname: "rows",
						fieldtype: "Table",
						cannot_add_rows: true,
						cannot_delete_rows: true,
						in_place_edit: true,
						data: rows,
						fields: [
							{ fieldname: "item_code", fieldtype: "Data", hidden: 1 },
							{ fieldname: "item_name", fieldtype: "Data", label: "Variant", in_list_view: 1, read_only: 1, columns: 6 },
							{ fieldname: "qty", fieldtype: "Float", label: "Omborda nechta", in_list_view: 1, columns: 4 },
						],
					},
				],
				primary_action_label: "Saqlash",
				primary_action(values) {
					frappe
						.xcall("marketplace.seller_desk.set_variants_stock", {
							rows: values.rows.map((r) => ({ item_code: r.item_code, qty: r.qty || 0 })),
						})
						.then((n) => {
							d.hide();
							frappe.show_alert({ message: `${n} ta variant qoldig'i yangilandi`, indicator: "green" });
						});
				},
			});
			d.show();
		});
	}

	function change_stock(frm) {
		frappe.xcall("marketplace.seller_desk.get_item_stock", { item_code: frm.doc.name }).then((qty) => {
			frappe.prompt(
				{
					fieldname: "qty",
					fieldtype: "Float",
					label: "Omborda hozir nechta bor",
					default: qty,
					reqd: 1,
					description: `Hozir hisobda: ${qty} ta. Yangi umumiy sonni yozing (qo'shiladigan farqni emas).`,
				},
				(v) =>
					frappe
						.xcall("marketplace.seller_desk.set_item_stock", { item_code: frm.doc.name, qty: v.qty })
						.then(() => {
							frappe.show_alert({ message: "Qoldiq yangilandi", indicator: "green" });
							frm.refresh();
						}),
				"Qoldiqni o'zgartirish",
				"Saqlash"
			);
		});
	}
})();
