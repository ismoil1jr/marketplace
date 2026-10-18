// Copyright (c) 2026, ismoil and contributors
// For license information, please see license.txt

frappe.query_reports["Marketplace Savdo Hisoboti"] = {
	filters: [
		{ fieldname: "from_date", label: __("Dan"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("Gacha"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "shop", label: __("Do'kon"), fieldtype: "Link", options: "Shop" },
	],
};
