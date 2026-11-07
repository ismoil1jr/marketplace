// Sotuvchi uchun tovarlar ro'yxati: har qatorda birinchi rasm; variantlar emas — faqat asosiy tovarlar.
(() => {
	const is_seller =
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;
	if (!is_seller) return;

	const settings = (frappe.listview_settings["Item"] ||= {});
	const prev_onload = settings.onload;
	settings.add_fields = [...(settings.add_fields || []), "image", "has_variants", "variant_of", "mp_tez_kunda", "mp_majburiy", "standard_rate", "variant_price"];
	// Rang/o'lchamli tovarda narx andozada emas, variantlarda (variant_price → set_variant_prices) — ro'yxatda o'sha ko'rinsin
	settings.formatters = {
		...(settings.formatters || {}),
		standard_rate: (value, df, doc) => {
			const price = doc.has_variants ? doc.variant_price : value;
			return price ? `${format_number(price, null, 0)} so‘m` : `<span class="text-muted">${__("narx yo‘q")}</span>`;
		},
	};
	settings.filters = [["variant_of", "is", "not set"]];
	// ERPNext'ning "Template / Variant" o'rniga tushunarli holat
	settings.get_indicator = (doc) => {
		if (doc.disabled) return ["Sotuvda emas", "gray", "disabled,=,1"];
		// Saytdagi holat: bosilsa — ro'yxat shu belgi bo'yicha filtrlanadi
		if (doc.mp_tez_kunda) return ["Tez kunda", "orange", "mp_tez_kunda,=,1"];
		if (doc.mp_majburiy) return ["Majburiy", "purple", "mp_majburiy,=,1"];
		if (doc.has_variants) return ["Rang/o'lchamli", "blue", "has_variants,=,1"];
		return ["Sotuvda", "green", "disabled,=,0"];
	};
	settings.onload = function (listview) {
		prev_onload?.call(this, listview);
		// Faqat kerakli ustunlar: nom (rasm bilan), holat, kategoriya, sotish narxi (setup.py: standard_rate in_list_view)
		listview.columns = listview.columns.filter((c) => c.type !== "Field" || ["item_group", "standard_rate"].includes(c.df?.fieldname));
		listview.render_header?.(true);
		// Variantlar ro'yxatda chiqmaydi (oldingi saqlangan filtr bo'lsa ham)
		if (!listview.filters.some((f) => f[1] === "variant_of")) {
			listview.filter_area.add([["Item", "variant_of", "is", "not set"]]);
		}
		// Sarlavha matn sifatida chiziladi (textContent), shuning uchun rasmni qator elementiga qo'shamiz
		const original = listview.get_subject_element.bind(listview);
		listview.get_subject_element = (doc, title) => {
			const div = original(doc, title);
			const thumb = document.createElement(doc.image ? "img" : "span");
			if (doc.image) {
				thumb.src = doc.image;
				thumb.alt = "";
				thumb.loading = "lazy";
			}
			thumb.style.cssText =
				"width:36px;height:36px;flex:none;object-fit:cover;border-radius:8px;margin-right:10px;background:var(--subtle-fg)";
			const checkbox = div.firstElementChild;
			checkbox ? checkbox.after(thumb) : div.prepend(thumb);
			return div;
		};
	};
})();
