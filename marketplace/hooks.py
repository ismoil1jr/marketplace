app_name = "marketplace"
app_title = "Marketplace"
app_publisher = "ismoil"
app_description = "Multi-shop catalog with Payme/Click"
app_email = "ismoilerkinov87@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Desk bosh ekranidagi ikonka: adminga "Marketplace", sotuvchiga o'z do'koni (seller_desk.boot_session)
add_to_apps_screen = [
	{
		"name": "marketplace",
		"logo": "/assets/marketplace/images/marketplace-logo.svg",
		"title": "Marketplace",
		"route": "/desk/marketplace",
		"has_permission": "marketplace.admin.has_app_permission",
	}
]

# The dock, the rail down the left of the desk, is a document rather than a hook. Author it in
# Manage Dock on a developer-mode site and press Export to App, and it is written to
# `marketplace/dock/marketplace/marketplace.json` for git to carry. An app that ships none has no
# rail: its sidebar gets a switcher in the header instead.
#
# A companion app, one that extends a host app rather than standing on its own, says so with
# `mount_on` on that same record, and its entries are appended to the host's rail. Mounting keeps
# the companion off the apps screen, so it takes precedence over any add_to_apps_screen above.

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/marketplace/css/marketplace.css"
# Desk'da yangi buyurtma signali (ovoz + ekrandagi xabar)
app_include_js = ["/assets/marketplace/js/seller_notify.js", "/assets/marketplace/js/stock_views.js", "/assets/marketplace/js/voice_note.js"]

# include js, css files in header of web template
# web_include_css = "/assets/marketplace/css/marketplace.css"
# web_include_js = "/assets/marketplace/js/marketplace.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "marketplace/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# Sotuvchi uchun soddalashtirilgan tovar formasi
doctype_js = {
	"Item": "public/js/item_seller.js",
	"Sales Order": "public/js/sales_order_seller.js",
	# Do'kon kategoriyasi: papka belgisi yashirin, daraxt oynasida MXIK va qadoq kodi
	"Item Group": "public/js/item_group_seller.js",
	# Admin: foydalanuvchini do'konga biriktirish; rollar ro'yxatida faqat marketplace rollari (ERPNext'niki yashirin)
	"User": "public/js/user_admin.js",
}
doctype_list_js = {"Sales Order": "public/js/sales_order_list.js", "Item": "public/js/item_list_seller.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_kanban_js = {"doctype" : "public/js/doctype_kanban.js"}
doctype_tree_js = {"Item Group": "public/js/item_group_seller.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "marketplace/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# magazinlar.uz/ — barcha do'konlar va platforma haqida (www/magazinlar.py); admin panel — /admin (/desk)
home_page = "magazinlar"
website_redirects = [{"source": "/admin", "target": "/desk"}]

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "marketplace.utils.jinja_methods",
# 	"filters": "marketplace.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "marketplace.install.before_install"

# Payme webhook'i Authorization sarlavhasi bilan keladi: Frappe'ning API-kalit tekshiruvidan oldin olib qo'yamiz
before_request = ["marketplace.payments.before_request"]

# Sotuvchiga Desktop'da faqat o'z do'koni ikonkasi
boot_session = "marketplace.seller_desk.boot_session"
# Adminning "Do'kon paneliga kirish" holati sessiyaga bog'liq: keshlanmaydigan qism
extend_bootinfo = "marketplace.seller_desk.extend_bootinfo"

after_install = "marketplace.setup.after_install"
after_migrate = "marketplace.setup.after_migrate"

jinja = {"methods": ["marketplace.storefront.fmt_sum"]}

# Mijoz sahifalari: shop.uz/s/<do'kon>, /s/<do'kon>/p/<tovar>, /s/<do'kon>/savat
website_route_rules = [
	{"from_route": "/s/<shop>", "to_route": "storefront/catalog"},
	{"from_route": "/s/<shop>/p/<item>", "to_route": "storefront/product"},
	{"from_route": "/s/<shop>/savat", "to_route": "storefront/cart"},
	{"from_route": "/s/<shop>/buyurtma/<order>", "to_route": "storefront/order"},
	{"from_route": "/s/<shop>/buyurtmalarim", "to_route": "storefront/orders"},
	# Meta (Instagram) lead-formasi uchun majburiy havola — har bir do'konning o'zi
	{"from_route": "/s/<shop>/maxfiylik", "to_route": "storefront/privacy"},
]

# Uninstallation
# ------------

# before_uninstall = "marketplace.uninstall.before_uninstall"
# after_uninstall = "marketplace.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "marketplace.utils.before_app_install"
# after_app_install = "marketplace.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "marketplace.utils.before_app_uninstall"
# after_app_uninstall = "marketplace.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "marketplace.build.after_build"

# To hook into the build process of other apps
# The list of apps being built is passed as an argument

# after_app_build = "marketplace.build.after_app_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "marketplace.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["marketplace.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# Sotuvchi faqat o'z buyurtmachilarini ko'radi
permission_query_conditions = {
	"Item": "marketplace.permissions.item_query",
	"Kontragent": "marketplace.permissions.kontragent_query",
	"Telegram Mijoz": "marketplace.permissions.telegram_mijoz_query",
	"Shop": "marketplace.permissions.shop_list_query",
	"Doimiy Mijoz": "marketplace.permissions.doimiy_mijoz_query",
	"Olcham": "marketplace.permissions.olcham_query",
	"Telefon Qongiroq": "marketplace.permissions.telefon_qongiroq_query",
	"Menejer Xulosasi": "marketplace.permissions.menejer_xulosasi_query",
	"Murojaat": "marketplace.permissions.murojaat_query",
	"Majburiy Tasdiq": "marketplace.permissions.majburiy_tasdiq_query",
	"Rang": "marketplace.permissions.rang_query",
	"Warehouse": "marketplace.permissions.warehouse_query",
	"Sales Order": "marketplace.permissions.sales_order_query",
	"Delivery Note": "marketplace.permissions.delivery_note_query",
	"Item Price": "marketplace.permissions.item_price_query",
	"Item Group": "marketplace.permissions.item_group_query",
	"Customer": "marketplace.permissions.customer_query",
	"Contact": "marketplace.permissions.contact_query",
	# Sotuvchi boshqa do'konlar a'zolarini va adminlarni ko'rmasin (Desk User'da standart "Select" bor)
	"User": "marketplace.permissions.user_query",
}
has_permission = {
	"Sales Order": "marketplace.permissions.sales_order_has_permission",
	# Do'konga tegishli yozuvlar: a'zo — faqat o'z do'koniniki, a'zo bo'lmagan (admin emas) — hech biri
	"Item": "marketplace.permissions.shop_doc_has_permission",
	"Item Price": "marketplace.permissions.shop_doc_has_permission",
	"Delivery Note": "marketplace.permissions.shop_doc_has_permission",
	"Kontragent": "marketplace.permissions.shop_doc_has_permission",
	"Doimiy Mijoz": "marketplace.permissions.shop_doc_has_permission",
	"Telegram Mijoz": "marketplace.permissions.shop_doc_has_permission",
	"Olcham": "marketplace.permissions.shop_doc_has_permission",
	"Telefon Qongiroq": "marketplace.permissions.telefon_qongiroq_has_permission",
	"Menejer Xulosasi": "marketplace.permissions.shop_doc_has_permission",
	"Rang": "marketplace.permissions.shop_doc_has_permission",
	"Payment Transaction": "marketplace.permissions.shop_doc_has_permission",
	"Shop": "marketplace.permissions.shop_has_permission",
	"Item Group": "marketplace.permissions.item_group_has_permission",
	"Customer": "marketplace.permissions.customer_has_permission",
	"Contact": "marketplace.permissions.contact_has_permission",
	"User": "marketplace.permissions.user_has_permission",
}
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	# Do'kon a'zosi User formasida o'z rolini yo'qotmasin va admin bo'lib qolmasin (shop.user_validate)
	"User": {"validate": "marketplace.marketplace.doctype.shop.shop.user_validate"},
	"Item": {
		"onload": "marketplace.seller_desk.item_onload",
		"before_insert": "marketplace.permissions.item_before_insert",
		"before_validate": [
			"marketplace.permissions.set_shop",
			"marketplace.seller_desk.item_default_attributes",
		],
		"validate": [
			"marketplace.seller_desk.item_template_price",
			"marketplace.permissions.item_validate",
			"marketplace.images.process_gallery",
			"marketplace.sotuv.murojaat.item_tovar_id",
		],
		"after_insert": "marketplace.seller_desk.item_after_insert",
		"on_update": [
			"marketplace.seller_desk.item_on_update",
			"marketplace.storefront.clear_catalog_cache",
		],
		"on_trash": "marketplace.storefront.clear_catalog_cache",
	},
	"Item Group": {
		"before_insert": "marketplace.permissions.item_group_before_insert",
		"validate": "marketplace.permissions.item_group_validate",
		"on_update": [
			"marketplace.permissions.item_group_on_update",
			# Saytdagi ustma-ust kategoriyalar (storefront._category_tree) keshdan yangilansin
			"marketplace.storefront.clear_catalog_cache",
		],
		"on_trash": "marketplace.storefront.clear_catalog_cache",
	},
	"Marketplace Settings": {"on_update": "marketplace.telegram_bot.on_settings_update"},
	"Item Price": {
		"before_validate": "marketplace.permissions.set_shop",
		"on_update": [
			"marketplace.storefront.clear_catalog_cache",
			# Ro'yxatdagi «Sotish narxi» (Item.standard_rate) Item Price bilan bir xil tursin
			"marketplace.seller_desk.item_price_on_update",
		],
		"on_trash": "marketplace.storefront.clear_catalog_cache",
	},
	"Sales Order": {
		"before_validate": "marketplace.permissions.set_shop",
		# Yangi buyurtma: sotuvchiga bildirishnoma (Desk) va Telegram xabari. Saytdagi buyurtma esa
		# mijoz naqdni tanlaganda yoki to'laganda (orders.confirm_order)
		"on_submit": [
			"marketplace.orders.sales_order_on_submit",
			# Buyurtma zaxiraga oladi: chegaraga tushgan tovar haqida egasiga Telegram xabari
			# (Desk buyurtmasi; saytdagisi — mijoz yakunlagach, orders.confirm_order)
			"marketplace.inventory.enqueue_low_stock_check",
		],
	},
	"Delivery Note": {"before_validate": "marketplace.permissions.set_shop"},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"hourly": [
		"marketplace.otp.cleanup_expired",
		"marketplace.orders.cancel_abandoned",
		# Sotuv paneli: qayta qo'ng'iroq sanasi kelgan buyurtmalar — menejerga eslatma
		"marketplace.sotuv.api.remind_callbacks",
		# Notanish raqamli qo'ng'iroqlar: 24 soatda murojaat bo'lmasa — yozuvi bilan o'chadi (sotuv/telefoniya.py)
		"marketplace.sotuv.telefoniya.purge_unknown_calls",
	],
	"cron": {
		# Har kuni 09:00 (sayt vaqt zonasi): do'kon egalariga kam qolgan / tugagan tovarlar ro'yxati
		"0 9 * * *": ["marketplace.inventory.daily_low_stock_digest"],
		# Qo'ng'iroq yozuvlari: o'tkazib yuborilgan transkripsiyalar (AI) va saqlash muddati o'tgan fayllar
		"*/15 * * * *": ["marketplace.sotuv.stt.process_queue"],
		# Instagram lead-formalari: webhook kelmay qolgan lidlar ham murojaat bo'lib tushadi (sotuv/meta.py)
		"*/10 * * * *": ["marketplace.sotuv.meta.poll_leads"],
		"30 3 * * *": ["marketplace.sotuv.stt.cleanup_old_recordings"],
	},
}

# scheduler_events = {
# 	"all": [
# 		"marketplace.tasks.all"
# 	],
# 	"daily": [
# 		"marketplace.tasks.daily"
# 	],
# 	"hourly": [
# 		"marketplace.tasks.hourly"
# 	],
# 	"weekly": [
# 		"marketplace.tasks.weekly"
# 	],
# 	"monthly": [
# 		"marketplace.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "marketplace.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "marketplace.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# ASMIZ Call Agent (sotuv menejeri telefonidagi ilova) manzilni o'zi qo'shadi — ikkalasi bizning telefoniyaga
override_whitelisted_methods = {
	"asmiz_call.api.ingest_call": "marketplace.sotuv.telefoniya.ingest_call",
	"target_zenit.telefoniya.api.ingest_call": "marketplace.sotuv.telefoniya.ingest_call",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "marketplace.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["marketplace.utils.before_request"]
# after_request = ["marketplace.utils.after_request"]

# Job Events
# ----------
# before_job = ["marketplace.utils.before_job"]
# after_job = ["marketplace.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"marketplace.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

