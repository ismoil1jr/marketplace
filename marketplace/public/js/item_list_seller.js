// Sotuvchi uchun tovarlar ro'yxati: har qatorda birinchi rasm; variantlar emas — faqat asosiy tovarlar.
(() => {
	const is_seller =
		!!frappe.boot.marketplace_shop /* sotuvchi yoki do'kon panelidagi admin */;
	if (!is_seller) return;

	const settings = (frappe.listview_settings["Item"] ||= {});
	const prev_onload = settings.onload;
	settings.add_fields = [...(settings.add_fields || []), "image", "has_variants", "variant_of"];
	settings.filters = [["variant_of", "is", "not set"]];
	// ERPNext'ning "Template / Variant" o'rniga tushunarli holat
	settings.get_indicator = (doc) => {
		if (doc.disabled) return ["Sotuvda emas", "gray", "disabled,=,1"];
		if (doc.has_variants) return ["Rang/o'lchamli", "blue", "has_variants,=,1"];
		return ["Sotuvda", "green", "disabled,=,0"];
	};
	settings.onload = function (listview) {
		prev_onload?.call(this, listview);
		// Faqat kerakli ustunlar: nom (rasm bilan), holat, kategoriya
		listview.columns = listview.columns.filter((c) => c.type !== "Field" || c.df?.fieldname === "item_group");
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
