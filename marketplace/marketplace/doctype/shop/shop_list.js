frappe.listview_settings["Shop"] = {
	add_fields: ["status", "brand_color"],
	get_indicator(doc) {
		const color = { Active: "green", Draft: "orange", Suspended: "red" }[doc.status] || "gray";
		return [__(doc.status), color, `status,=,${doc.status}`];
	},
	button: {
		show: (doc) => doc.status === "Active",
		get_label: () => __("Sayt"),
		get_description: (doc) => __("{0} saytini ochish", [doc.shop_name || doc.name]),
		action: (doc) => window.open(`/s/${encodeURIComponent(doc.name)}`, "_blank"),
	},
	onload(listview) {
		const is_admin = frappe.user.has_role("System Manager") || frappe.user.has_role("Marketplace Manager");
		if (is_admin) {
			listview.page.add_inner_button(__("Do'konlar paneli"), () => frappe.set_route("shops-overview"));
			return;
		}
		// Sotuvchida bitta do'kon: ro'yxat o'rniga o'sha do'kon sozlamalari ochiladi
		frappe.db.get_list("Shop", { fields: ["name"], limit: 2 }).then((rows) => {
			if (rows.length === 1) frappe.set_route("Form", "Shop", rows[0].name);
		});
	},
};
