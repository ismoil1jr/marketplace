import frappe

from marketplace import panel, storefront

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/panel"
		raise frappe.Redirect
	try:
		context.shop = panel.panel_shop(frappe.form_dict.get("shop"))
	except frappe.PermissionError as e:
		context.error = str(e) or "Ruxsat yo'q"
		context.shop = None
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.asset_version = storefront.asset_version()
	context.user_name = frappe.utils.get_fullname(frappe.session.user)
