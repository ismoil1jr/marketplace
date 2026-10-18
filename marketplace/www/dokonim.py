"""/dokonim — kirgan sotuvchini o'z do'konining sahifasiga (/s/<slug>) yuboradi."""

import frappe

from marketplace.permissions import get_user_shop

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/dokonim"
		raise frappe.Redirect
	shop = get_user_shop()
	frappe.local.flags.redirect_location = f"/s/{shop}" if shop else "/desk"
	raise frappe.Redirect
