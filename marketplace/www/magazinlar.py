import frappe

from marketplace import storefront

no_cache = 1


def get_context(context):
	"""magazinlar.uz bosh sahifasi (hooks.home_page): faol do'konlar va platforma haqida. Admin panel — /admin."""
	shops = frappe.get_all(
		"Shop", filters={"status": "Active"}, fields=["name", "shop_name", "tagline", "city", "logo", "brand_color"],
		order_by="shop_name asc",
	)
	counts = {}
	if shops:
		counts = dict(
			frappe.db.sql(
				"""select shop, count(*) from `tabItem` where is_published = 1 and disabled = 0
				and ifnull(variant_of, '') = '' and shop in %(shops)s group by shop""",
				{"shops": [s.name for s in shops]},
			)
		)
	for s in shops:
		s.initials = "".join(w[0] for w in (s.shop_name or "?").split()[:2]).upper()
		s.item_count = counts.get(s.name, 0)
	context.shops = shops
	# Sozlamalar hali saqlanmagan bo'lsa — maydonning standart qiymati (Single'da default bazaga yozilmaydi)
	context.phone = frappe.db.get_single_value("Marketplace Settings", "aloqa_telefon") or (
		frappe.get_meta("Marketplace Settings").get_field("aloqa_telefon").default or ""
	)
	context.phone_href = "".join(ch for ch in context.phone if ch.isdigit() or ch == "+")
	context.is_staff = frappe.session.user != "Guest" and frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"
	context.asset_version = storefront.asset_version()
	context.year = frappe.utils.getdate().year
