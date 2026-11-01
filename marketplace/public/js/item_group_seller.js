// Do'kon kategoriyalari (Item Group) — sotuvchi uchun. Daraxt oynasi (doctype_tree_js) va forma (doctype_js) bitta fayl.
// Ustma-ust: bosh kategoriya (MXIK + qadoq kodi shu yerda) › ichki kategoriya › yana ichki (3 qavatgacha),
// masalan Telefonlar › Xiaomi yoki Kiyim › Kurtka › Zara. Tovar oxirgi kategoriyaga biriktiriladi.
// Server: permissions.add_category / item_group_validate / item_group_tree.
(() => {
	const is_seller = () => !!frappe.boot.marketplace_shop;
	const MAX_DEPTH = 3;

	function add_dialog(tree, node) {
		const top = node.is_root || !node.data?.depth;
		const fields = [
			{ fieldtype: "Data", fieldname: "name", label: __("Kategoriya nomi"), reqd: 1,
				description: top ? __("Masalan: Telefonlar, Kiyim") : __("Masalan: Xiaomi, Apple yoki Kurtka") },
		];
		// Oxirgi kategoriyada tovar bo'lsa: papkaga aylanadi, tovarlari yangi (yoki tanlangan) kategoriyaga o'tadi
		const items = !top && !node.expandable ? node.data?.items || 0 : 0;
		if (items) {
			fields.push({
				fieldtype: "Link", fieldname: "items_to", options: "Item Group",
				label: __("«{0}» dagi {1} ta tovar qayerga o‘tsin?", [node.title || node.label, items]),
				description: __("Bo‘sh qoldirsangiz — shu yangi kategoriyaga o‘tadi"),
				get_query: () => ({ filters: { is_group: 0, name: ["!=", node.label] } }),
			});
		}
		if (top) {
			fields.push(
				{ fieldtype: "Data", fieldname: "mxik_code", label: __("MXIK kodi"), reqd: 1,
					description: __("17 ta raqam — tasnif.soliq.uz. Ichidagi kategoriyalar va tovarlar shu koddan foydalanadi") },
				{ fieldtype: "Data", fieldname: "package_code", label: __("Qadoq kodi"), reqd: 1, description: __("tasnif.soliq.uz da MXIK kodi ichida") }
			);
		}
		const d = new frappe.ui.Dialog({
			title: top ? __("Bosh kategoriya") : __("«{0}» ichiga kategoriya", [node.title || node.label]),
			fields,
			primary_action_label: __("Qo‘shish"),
			async primary_action(v) {
				const r = await frappe.xcall("marketplace.permissions.add_category", {
					parent: node.label, name: v.name, mxik_code: v.mxik_code || null, package_code: v.package_code || null,
					items_to: v.items_to || null,
				});
				d.hide();
				frappe.show_alert({
					message: r.moved ? __("Kategoriya qo‘shildi, {0} ta tovar «{1}» ga o‘tdi", [r.moved, r.moved_to]) : __("Kategoriya qo‘shildi"),
					indicator: "green",
				});
				// Oxirgi kategoriya papkaga aylangan bo'lishi mumkin — daraxtni qayta chizamiz
				tree.make_tree();
			},
		});
		d.show();
	}

	// Daraxt: ERPNext sozlamasini (item_group_tree.js) kengaytiramiz — u bizdan oldin yuklanadi.
	// Ildiz do'konchiga ko'rinmaydi (qat'iy ruxsat) — tugunlar permissions.item_group_tree'dan (qavati va tovar soni bilan).
	if (is_seller()) {
		const settings = (frappe.treeview_settings["Item Group"] = frappe.treeview_settings["Item Group"] || {});
		settings.get_tree_nodes = "marketplace.permissions.item_group_tree";
		settings.extend_toolbar = true;
		settings.toolbar = [
			{
				// Standart "Add Child" faqat papkada ishlaydi; bizda oxirgi kategoriya ichiga ham qo'shsa bo'ladi
				label: __("Add Child"),
				icon: "plus",
				condition: (node) => node.is_root || (node.data?.depth || 0) < MAX_DEPTH,
				click: (node) => add_dialog(frappe.views.trees["Item Group"], node),
			},
		];
		settings.get_label = (node) => {
			const esc = frappe.utils.escape_html;
			const items = node.data?.items ? ` <span class="text-muted small">· ${node.data.items} ${__("ta tovar")}</span>` : "";
			const top = node.data?.depth === 1 ? ` <span class="text-muted small">· ${__("bosh")}</span>` : "";
			return `${esc(node.title || node.label)}${top}${items}`;
		};
		// Frappe o'z "Add Item Group" tugmasini onload'dan keyin qo'yadi — shuning uchun daraxt chizilgandan keyin
		settings.post_render = (tree) => {
			tree.page.set_primary_action(__("Bosh kategoriya qo‘shish"), () => add_dialog(tree, { is_root: true, label: tree.root_value || "All Item Groups" }), "add");
		};
	}

	frappe.ui.form.on("Item Group", {
		async refresh(frm) {
			if (!is_seller()) return;
			frm.toggle_display("is_group", false);
			// ERPNext buxgalteriyasi uchun: kompaniya bo'yicha standart ombor/narx ro'yxati va soliq shabloni (Item Tax).
			// Do'konda ombor o'zi qo'yiladi, soliq Payme/Click chekida MXIK bilan ketadi — sotuvchiga kerak emas
			frm.toggle_display(["defaults", "sec_break_taxes"], false);
			// Do'konchi faqat nomini ko'radi va o'zgartiradi; ID (item_group_name) boshqa do'kon bilan to'qnashsa
			// "Kiyimlar (clothes)" bo'ladi — u ichki (permissions.item_group_before_insert)
			frm.toggle_display("item_group_name", false);
			frm.toggle_reqd("mp_title", true);
			// MXIK faqat bosh kategoriyada; ichkisida — qaysi koddan foydalanishi ko'rsatiladi
			const parent_shop = frm.doc.parent_item_group
				? (await frappe.db.get_value("Item Group", frm.doc.parent_item_group, "shop")).message?.shop
				: null;
			const top = !parent_shop;
			for (const f of ["mxik_code", "package_code"]) {
				frm.toggle_display(f, top);
				frm.toggle_reqd(f, top);
			}
			if (!top && !frm.is_new()) {
				const [mxik] = await frappe.xcall("marketplace.permissions.category_codes", { name: frm.doc.parent_item_group });
				frm.set_intro(
					mxik ? __("MXIK va qadoq kodi bosh kategoriyadan olinadi: {0}", [mxik]) : __("Bosh kategoriyada MXIK kodi yo‘q — uni bosh kategoriyaga yozing"),
					mxik ? "blue" : "orange"
				);
			}
		},
	});
})();
