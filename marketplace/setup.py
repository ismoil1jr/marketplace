"""App o'rnatilganda va har `bench migrate` da ishlaydi.

Standart ERPNext DocType'lariga qo'shiladigan maydonlar va sotuvchi roli shu yerda.
Kod orqali yaratilgani uchun har saytda bir xil bo'ladi va git'da saqlanadi.
"""

import frappe
from frappe.utils import cint
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property

from marketplace.admin import setup_admin_workspace
from marketplace.seller_desk import setup_seller_workspace

SELLER_ROLE = "Shop Seller"
# Do'kon kuryeri: yetkaziladigan buyurtmalar, naqd pulni olish va doimiy mijozlar anketasi
COURIER_ROLE = "Shop Courier"
# Platforma xodimi: barcha do'konlarni boshqaradi, lekin tizim sozlamalariga (System Manager) kirmaydi
MANAGER_ROLE = "Marketplace Manager"
# Do'konning sotuv menejeri: Sotuv paneli (to'lanmagan buyurtmalar, qo'ng'iroqlar, natija). Faqat o'z do'koni
SALES_ROLE = "Shop Sales Manager"

SHOP_FIELD = {
	"fieldname": "shop",
	"label": "Shop",
	"fieldtype": "Link",
	"options": "Shop",
	"search_index": 1,
	"in_standard_filter": 1,
}

CUSTOM_FIELDS = {
	"Item": [
		{**SHOP_FIELD, "insert_after": "item_group", "in_list_view": 1},
		{
			"fieldname": "is_published",
			"label": "Saytda ko'rsatish",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "shop",
		},
		{
			# Do'konda majburiy tovar bo'lsa: mijoz uni hech olmagan (va savatida ham yo'q) bo'lsa — boshqa buyurtma bera
			# olmaydi (orders.mandatory_status). Masalan: kitoblar faqat o'qiydigan ruchka bilan
			"fieldname": "mp_majburiy",
			"label": "Majburiy tovar",
			"fieldtype": "Check",
			"default": "0",
			"in_standard_filter": 1,
			"insert_after": "is_published",
			"description": "Belgilansa: bu tovarni bir marta ham olmagan mijoz do'kondan boshqa narsa buyurtma qila olmaydi (savatida shu tovar bo'lsa — mumkin). Majburiy tovarlar bir nechta bo'lsa — har birini olishi kerak",
		},
		{
			# Saytda ko'rinadi (rasm, tavsif, sevimlilar), lekin sotilmaydi: savat va buyurtma uni qabul qilmaydi
			"fieldname": "mp_tez_kunda",
			"label": "Tez kunda",
			"fieldtype": "Check",
			"default": "0",
			"in_standard_filter": 1,
			"insert_after": "mp_majburiy",
			"description": "Belgilansa: saytda och rangda «Tez kunda» bo'lib chiqadi, mijoz ko'radi va sevimlilarga qo'shadi, lekin sotib ololmaydi",
		},
		{
			# Instagram formasi (Google Sheets) murojaati qaysi tovar bo'yicha: SMM varaq/forma nomiga yoki tovar_id ustuniga
			# shu raqamni yozadi (murojaat._item). Do'kon ichida takrorlanmaydi, bo'sh bo'lsa — o'zi beriladi (item_tovar_id)
			"fieldname": "mp_tovar_id",
			"label": "Tovar ID (reklama)",
			"fieldtype": "Int",
			"insert_after": "mp_tez_kunda",
			"no_copy": 1,
			"search_index": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
			"bold": 1,
			"depends_on": "eval:!doc.variant_of",
			"description": "Instagram formasi uchun qisqa raqam: SMM jadvalda (varaq nomi yoki tovar_id) shu raqamni yozadi — murojaat shu tovar bo'yicha tushadi. Bo'sh qoldirilsa — o'zi beriladi",
		},
		{
			"fieldname": "variant_price",
			"label": "Sotish narxi (barcha variantlarga)",
			"fieldtype": "Currency",
			"insert_after": "standard_rate",
			"depends_on": "eval:doc.has_variants",
			"description": "Standart narx: alohida narx qo'yilmagan har bir rang/o'lchamga shu narx qo'yiladi",
		},
		{
			# Standart narx tagida: "Rang/o'lcham bo'yicha narx" tugmasi (item_seller.js, seller_desk.set_variant_prices)
			"fieldname": "mp_narxlar_html",
			"label": "Rang/o'lcham bo'yicha narx",
			"fieldtype": "HTML",
			"insert_after": "variant_price",
			"depends_on": "eval:doc.has_variants",
		},
		{
			# Variantda: narx standartdan farqli qo'yilgan — standart narx o'zgarsa ham o'z narxida qoladi
			"fieldname": "mp_own_price",
			"label": "Alohida narx (standartdan farqli)",
			"fieldtype": "Check",
			"insert_after": "mp_narxlar_html",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "ranglar",
			"label": "Ranglar",
			"fieldtype": "Table MultiSelect",
			"options": "Tovar Rangi",
			"insert_after": "mp_own_price",
			"depends_on": "eval:doc.has_variants",
			"description": "Rasmlarni rang bo'yicha belgilash uchun. \"Ombor\" tabidagi kirimda yangi rang yozilsa, bu yerga o'zi qo'shiladi",
		},
		{
			# Ichki: ranglar jadvalidan yig'iladi (seller_desk.item_default_attributes)
			"fieldname": "variant_colors",
			"label": "Ranglar (matn)",
			"fieldtype": "Small Text",
			"insert_after": "ranglar",
			"hidden": 1,
		},
		{
			# Ichki: o'lchamlar "Ombor" tabidagi kirim qatorlaridan yig'iladi (seller_desk._check_kirim)
			"fieldname": "variant_sizes",
			"label": "O'lchamlar",
			"fieldtype": "Small Text",
			"insert_after": "variant_colors",
			"hidden": 1,
		},
		{
			# Eski: hammasiga bir xil son. Endi formadagi rang × o'lcham kirim jadvali ishlatiladi
			"fieldname": "variant_qty",
			"label": "Har bir variantdan nechta (omborga)",
			"fieldtype": "Int",
			"insert_after": "variant_sizes",
			"hidden": 1,
			"description": "Yangi yaratilgan har bir rang/o'lcham uchun omborga shuncha yoziladi. Keyin Ombor sahifasida alohida o'zgartirsa bo'ladi",
		},
		{
			"fieldname": "in_carousel",
			"label": "Karuselga qo'shish",
			"fieldtype": "Check",
			"insert_after": "is_published",
			"description": "Belgilansa, tovar do'kon sahifasi tepasidagi aylanadigan karuselda chiqadi",
		},
		{
			"fieldname": "carousel_label",
			"label": "Karusel yozuvi",
			"fieldtype": "Data",
			"insert_after": "in_carousel",
			"depends_on": "in_carousel",
			"description": "Ixtiyoriy, masalan: Yangi kolleksiya yoki −20% chegirma",
		},
		{
			"fieldname": "old_price",
			"label": "Eski narx (chegirmadan oldin)",
			"fieldtype": "Currency",
			"insert_after": "is_published",
			"description": "To'ldirilsa, sahifada chizilgan narx va −% belgisi chiqadi",
		},
		{
			"fieldname": "spec_line",
			"label": "Qisqa xususiyat (ro'yxat uchun)",
			"fieldtype": "Data",
			"insert_after": "old_price",
			"description": "Masalan: Laminat, 120×60 sm",
		},
		{
			"fieldname": "wholesale_price",
			"label": "Ulgurji narx",
			"fieldtype": "Currency",
			"insert_after": "spec_line",
			"description": "Bo'sh bo'lsa ulgurji narx yo'q",
		},
		{
			"fieldname": "wholesale_min_qty",
			"label": "Ulgurji: kamida (dona)",
			"fieldtype": "Int",
			"default": "10",
			"insert_after": "wholesale_price",
			"depends_on": "wholesale_price",
		},
		{
			"fieldname": "sb_gallery",
			"label": "Rasmlar",
			"fieldtype": "Section Break",
			"insert_after": "description",
		},
		{
			"fieldname": "gallery",
			"label": "Galereya",
			"fieldtype": "Table",
			"options": "Item Gallery",
			"insert_after": "sb_gallery",
			"description": "Birinchi rasm — asosiy. Yuklangan rasmlar avtomatik WebP'ga siqiladi.",
		},
		{
			"fieldname": "sb_fiscal",
			"label": "Fiskal (Payme/Click cheki uchun)",
			"fieldtype": "Section Break",
			"insert_after": "gallery",
			"collapsible": 0,
		},
		{
			"fieldname": "mxik_code",
			"label": "MXIK kodi",
			"fieldtype": "Data",
			"insert_after": "sb_fiscal",
			"description": "Kategoriyadan avtomatik olinadi (permissions.item_validate)",
		},
		{
			"fieldname": "package_code",
			"label": "Qadoq kodi",
			"fieldtype": "Data",
			"insert_after": "mxik_code",
			"description": "Kategoriyadan avtomatik olinadi",
		},
		# "Ombor" tabi (Accounting'dan keyin): hozirgi qoldiq, yangi kirim (qaysi kontragentdan, nechta, necha puldan) va kirim tarixi.
		# Kirim qatorlari saqlashda omborga yoziladi va tozalanadi (seller_desk.item_on_update)
		{
			"fieldname": "mp_ombor_tab",
			"label": "Ombor",
			"fieldtype": "Tab Break",
			"insert_after": "no_of_months",
		},
		{
			"fieldname": "mp_ombor_html",
			"label": "Omborda hozir",
			"fieldtype": "HTML",
			"insert_after": "mp_ombor_tab",
		},
		{
			"fieldname": "mp_sb_kirim",
			"label": "Yangi kirim",
			"fieldtype": "Section Break",
			"insert_after": "mp_ombor_html",
		},
		{
			# Do'konning kontragentlari (item_seller.js set_query); ro'yxatda yo'q bo'lsa — shu yerdan yangisi
			"fieldname": "mp_kirim_kontragent",
			"label": "Kimdan olindi (kontragent)",
			"fieldtype": "Link",
			"options": "Kontragent",
			"insert_after": "mp_sb_kirim",
			"no_copy": 1,
			"description": "Kontragentlar ro'yxatidan tanlang. Yangi odam bo'lsa — ro'yxat oxiridagi «+ yangi» orqali shu yerning o'zida qo'shing",
		},
		{
			"fieldname": "mp_kirim",
			"label": "Qaysi rang, qaysi o'lcham, nechta keldi",
			"fieldtype": "Table",
			"options": "Tovar Kirimi",
			"insert_after": "mp_kirim_kontragent",
			"no_copy": 1,
			"description": "Har bir rang/o'lcham — alohida qator. Saqlaganda omborga qo'shiladi va pastdagi tarixga yoziladi",
		},
		{
			"fieldname": "mp_kirim_izoh",
			"label": "Izoh",
			"fieldtype": "Data",
			"insert_after": "mp_kirim",
			"no_copy": 1,
			"description": "Ixtiyoriy — bo'sh qoldirsa ham bo'ladi. Masalan: «qarzga olindi» yoki «2-partiya»",
		},
		{
			"fieldname": "mp_sb_log",
			"label": "Kirim tarixi",
			"fieldtype": "Section Break",
			"insert_after": "mp_kirim_izoh",
		},
		{
			"fieldname": "mp_ombor_log",
			"label": "Kirimlar",
			"fieldtype": "HTML",
			"insert_after": "mp_sb_log",
		},
	],
	"Item Price": [
		{**SHOP_FIELD, "insert_after": "item_code", "fetch_from": "item_code.shop", "read_only": 1},
	],
	"Warehouse": [
		{**SHOP_FIELD, "insert_after": "warehouse_name", "read_only": 1},
	],
	# Kirim hujjati (Material Receipt): tovar qaysi kontragentdan olingani. Narxi — qatorlarning basic_rate'ida
	# (inventory.receive). Kontragent formasidagi "Xaridlar" shu maydon bo'yicha yig'iladi
	"Stock Entry": [
		{
			"fieldname": "mp_kontragent",
			"label": "Kimdan olindi (kontragent)",
			"fieldtype": "Link",
			"options": "Kontragent",
			"insert_after": "stock_entry_type",
			"read_only": 1,
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
	],
	"Sales Order": [
		{**SHOP_FIELD, "insert_after": "customer", "in_list_view": 1},
		{
			"fieldname": "customer_phone",
			"label": "Mijoz telefoni",
			"fieldtype": "Data",
			"options": "Phone",
			"insert_after": "shop",
			"in_list_view": 1,
		},
		{
			"fieldname": "payment_method",
			"label": "To'lov turi",
			"fieldtype": "Select",
			"options": "\nPayme\nClick\nNaqd",
			"insert_after": "customer_phone",
		},
		{
			"fieldname": "payment_status",
			"label": "To'lov holati",
			"fieldtype": "Select",
			"options": "Kutilmoqda\nTo'langan\nBekor",
			"default": "Kutilmoqda",
			"insert_after": "payment_method",
			"in_list_view": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "order_source",
			"label": "Manba",
			"fieldtype": "Select",
			"options": "\nInstagram\nTelegram\nWeb",
			"insert_after": "payment_status",
		},
		{
			# Saytdagi buyurtma mijoz to'lov usulini tanlamaguncha (naqd) yoki to'lamaguncha (Payme/Click) 0:
			# sotuvchiga ko'rinmaydi va xabar bormaydi (orders.confirm_order). Qo'lda kiritilgan buyurtma — 1
			"fieldname": "mp_placed",
			"label": "Buyurtma berilgan",
			"fieldtype": "Check",
			"default": "1",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"insert_after": "order_source",
		},
		# Sotuv menejerining oxirgi natijasi (sotuv/api.save_result — Aloqa Yozuvi'dan), panel ro'yxati uchun
		{
			"fieldname": "mp_aloqa_natija",
			"label": "Menejer natijasi",
			"fieldtype": "Select",
			"options": "\nOladi\nOlmaydi\nJavob bermadi\nKeyinroq",
			"insert_after": "mp_placed",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "mp_aloqa_kanal",
			"label": "Aloqa kanali",
			"fieldtype": "Select",
			"options": "\nQo‘ng‘iroq\nSMS",
			"insert_after": "mp_aloqa_natija",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "mp_aloqa_vaqt",
			"label": "Oxirgi aloqa",
			"fieldtype": "Datetime",
			"insert_after": "mp_aloqa_kanal",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "mp_keyingi_qongiroq",
			"label": "Qayta qo'ng'iroq sanasi",
			"fieldtype": "Date",
			"insert_after": "mp_aloqa_vaqt",
			"read_only": 1,
			"allow_on_submit": 1,
			"no_copy": 1,
		},
	],
	"Delivery Note": [
		{**SHOP_FIELD, "insert_after": "customer"},
	],
	"Item Group": [
		{
			# Ko'rinadigan nom. ID (item_group_name) butun tizimda bitta va ERPNext uni nom bilan bir xil saqlaydi;
			# boshqa do'konda shu nom bo'lsa ID "Kiyimlar (clothes)" bo'ladi, bu yerda esa "Kiyimlar" (title_field)
			"fieldname": "mp_title",
			"label": "Nomi",
			"fieldtype": "Data",
			"insert_after": "item_group_name",
			"in_list_view": 1,
			"bold": 1,
		},
		{**SHOP_FIELD, "insert_after": "parent_item_group", "description": "Bo'sh bo'lsa, sotuvchilarga ko'rinmaydi"},
		{
			"fieldname": "mxik_code",
			"label": "MXIK kodi",
			"fieldtype": "Data",
			"insert_after": "shop",
			"allow_in_quick_entry": 1,
			"mandatory_depends_on": "eval:!doc.is_group && (doc.shop || frappe.boot.marketplace_shop)",
			"description": "tasnif.soliq.uz dagi 17 xonali kod. Shu kategoriyadagi barcha tovarlarga o'zi qo'yiladi (Payme/Click chekida soliqqa boradi)",
		},
		{
			"fieldname": "package_code",
			"label": "Qadoq kodi",
			"fieldtype": "Data",
			"insert_after": "mxik_code",
			"allow_in_quick_entry": 1,
			"mandatory_depends_on": "eval:!doc.is_group && (doc.shop || frappe.boot.marketplace_shop)",
			"description": "tasnif.soliq.uz da MXIK kodining ichida turadi (masalan \"dona\" uchun). Soliq chekida MXIK bilan birga majburiy",
		},
	],
	"Customer": [
		{
			"fieldname": "mp_phone",
			"label": "Telefon (tasdiqlangan)",
			"fieldtype": "Data",
			"options": "Phone",
			"unique": 1,
			"search_index": 1,
			"read_only": 1,
			"insert_after": "customer_name",
			"description": "+998XXXXXXXXX. Mijoz shu raqam bilan Telegram kodi orqali kiradi",
		},
	],
}

# Rang namunasi (sotuvchi panelida va mahsulot sahifasida doiracha rangi)
CUSTOM_FIELDS["Item Attribute Value"] = [
	{"fieldname": "color_hex", "label": "Rang (HEX)", "fieldtype": "Color", "insert_after": "abbr", "in_list_view": 1},
]

# ERPNext atributlari platformada umumiy (variantlar shu nomlar bilan yaratiladi). Do'konlar ro'yxati esa alohida:
# ranglar — Rang, o'lchamlar — Olcham (har biri shop maydoni bilan); yangi do'konga COLORS va SIZES qo'shiladi
COLOR_ATTR = "Rang"
SIZE_ATTR = "O'lcham"
COLORS = [
	("Oq", "OQ", "#F4F2EC"), ("Qora", "QOR", "#1F1F1F"), ("Bej", "BEJ", "#CDB89A"), ("Kulrang", "KUL", "#9A9A9A"),
	("Zaytun", "ZAY", "#7F9A86"), ("To'q ko'k", "TKK", "#2E3A55"), ("Ko'k", "KOK", "#4A7BD0"), ("Yashil", "YAS", "#3F8F5A"),
	("Qizil", "QIZ", "#C4372F"), ("Pushti", "PUS", "#E6A6B8"), ("Jigarrang", "JIG", "#7A4E33"), ("Sariq", "SAR", "#E8C547"),
]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]

CUSTOM_FIELDS["Sales Order"] += [
	{
		"fieldname": "delivery_method",
		"label": "Yetkazish usuli",
		"fieldtype": "Select",
		"options": "\nKuryer\nO'zim olaman",
		"insert_after": "order_source",
	},
	{
		"fieldname": "delivery_address",
		"label": "Manzil",
		"fieldtype": "Small Text",
		"insert_after": "delivery_method",
		"depends_on": "eval:doc.delivery_method=='Kuryer'",
	},
]

# Kuryer yetkazish va naqd pul yo'li: mijozdan oldi (Kuryerda) -> do'kon egasiga berdi (Do'konga topshirildi).
# Hammasini server yozadi (seller_desk.courier_delivered / cash_handed_over), formada faqat ko'rinadi
CUSTOM_FIELDS["Sales Order"] += [
	{
		"fieldname": "mp_courier",
		"label": "Kuryer",
		"fieldtype": "Link",
		"options": "User",
		"insert_after": "delivery_address",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
	},
	{
		# Kuryerda -> (kuryer "Topshirdim") Topshirilmoqda -> (do'konchi "Qabul qildim") Do'konga topshirildi (kassa.py)
		"fieldname": "mp_cash_status",
		"label": "Naqd pul qayerda",
		"fieldtype": "Select",
		"options": "\nKuryerda\nTopshirilmoqda\nDo'konga topshirildi",
		"insert_after": "mp_courier",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
		"in_standard_filter": 1,
	},
	{
		"fieldname": "mp_delivered_at",
		"label": "Mijozga topshirilgan vaqt",
		"fieldtype": "Datetime",
		"insert_after": "mp_cash_status",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
	},
	{
		# Naqd to'lovning noyob ID'si (Payme/Click'da — ularning tranzaksiya ID'si, Payment Transaction'da). kassa.py
		"fieldname": "mp_payment_id",
		"label": "To'lov ID",
		"fieldtype": "Data",
		"insert_after": "mp_delivered_at",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
		"search_index": 1,
	},
	{
		"fieldname": "mp_paid_at",
		"label": "To'langan vaqt",
		"fieldtype": "Datetime",
		"insert_after": "mp_payment_id",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "mp_cash_sent_at",
		"label": "Kuryer pulni topshirgan vaqt",
		"fieldtype": "Datetime",
		"insert_after": "mp_paid_at",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
	},
	{
		"fieldname": "mp_cash_handed_at",
		"label": "Pul do'konga topshirilgan vaqt",
		"fieldtype": "Datetime",
		"insert_after": "mp_cash_sent_at",
		"read_only": 1,
		"allow_on_submit": 1,
		"no_copy": 1,
	},
]

# Sotuvchi nima qila oladi. Qaysi do'kon ekanini User Permission cheklaydi.
SELLER_PERMISSIONS = {
	# O'z do'konini tahrirlaydi (logo, karusel, aloqa). Status, STIR, ombor — permlevel 1 (faqat ko'radi),
	# Payme/Click kalitlari — permlevel 2 (umuman ko'rmaydi)
	"Shop": ["read", "write"],
	# Faqat o'z do'konidan buyurtma qilgan mijozlar (permissions.customer_query)
	"Customer": ["read"],
	"Contact": ["read"],
	"Item": ["read", "write", "create"],
	"Item Price": ["read", "write", "create", "delete"],
	"Sales Order": ["read", "write"],
	# Ombor faqat kirim (inventory.receive) va sotuv (mark_delivered) bilan o'zgaradi — ikkalasi server'da.
	# Sotuvchi ERPNext formalari orqali qoldiqni kamaytira olmasin: bu hujjatlarni faqat ko'radi
	"Delivery Note": ["read"],
	"Warehouse": ["read"],
	"Stock Reconciliation": ["read"],
	"Stock Entry": ["read"],
	# Item va narx formalaridagi Link maydonlari uchun (faqat tanlash)
	"Price List": ["read"],
	"Brand": ["read"],
	"Item Attribute": ["read"],
	# O'z kategoriyalari: faqat o'z do'koninikini ko'radi (permissions.item_group_query)
	"Item Group": ["select", "read", "create", "write"],
	# O'z ranglari: faqat o'z do'koninikini ko'radi va o'chiradi (permissions.rang_query)
	"Rang": ["read", "write", "create", "delete"],
	"UOM": ["select"],
}


# Kuryer: o'z do'konining kuryer bilan yetkaziladigan buyurtmalari (permissions.sales_order_query) va mijozlar.
# Item/Shop/ombor unga kerak emas — Payme kalitlari va narxlarga umuman tegmaydi
COURIER_PERMISSIONS = {
	"Sales Order": ["read", "write"],
	"Customer": ["read"],
	"Contact": ["read"],
}

# Oldin berilgan, endi olib qo'yilgan huquqlar (migrate'da o'chiriladi)
SELLER_REVOKED = {
	"Delivery Note": ["write", "create", "submit", "cancel", "delete", "amend"],
	"Stock Reconciliation": ["write", "create", "submit", "cancel", "delete", "amend"],
	"Stock Entry": ["write", "create", "submit", "cancel", "delete", "amend"],
}

# permlevel > 0 dagi ruxsatlar: {doctype: {permlevel: [huquqlar]}}
SELLER_LEVEL_PERMISSIONS = {"Shop": {1: ["read"]}}
MANAGER_LEVEL_PERMISSIONS = {"Shop": {1: ["read", "write"], 2: ["read", "write"]}}


MANAGER_PERMISSIONS = {
	"Shop": ["read", "write", "create", "delete", "report", "export"],
	"Item": ["read", "write", "create", "report", "export"],
	"Item Price": ["read", "write", "create", "delete", "report"],
	"Item Group": ["read", "write", "create"],
	"Sales Order": ["read", "write", "create", "submit", "cancel", "report", "export"],
	"Delivery Note": ["read", "write", "create", "submit", "cancel", "report"],
	"Stock Reconciliation": ["read", "write", "create", "submit", "cancel"],
	"Warehouse": ["read", "report"],
	"Customer": ["read", "report"],
	"Price List": ["read"],
	"Brand": ["read", "write", "create"],
	"Item Attribute": ["read", "write", "create"],
	"UOM": ["read"],
	"User": ["read"],
}


def after_install():
	after_migrate()


def after_migrate():
	create_custom_fields(CUSTOM_FIELDS, update=True)
	setup_seller_role()
	setup_courier_role()
	setup_sales_role()
	setup_manager_role()
	# Strict: shop maydoni bo'sh yozuvlar ham sotuvchiga ko'rinmaydi
	frappe.db.set_single_value("System Settings", "apply_strict_user_permissions", 1)
	# Tovar videosi (Item Gallery.video) 50 MB gacha; standart 25 MB telefon videosiga yetmaydi
	if cint(frappe.db.get_single_value("System Settings", "max_file_size")) < 50:
		frappe.db.set_single_value("System Settings", "max_file_size", 50)
	disable_perpetual_inventory()
	setup_link_results_limit()
	setup_variant_attributes()
	setup_uzs_currency()
	setup_seller_workspace()
	setup_admin_workspace()
	migrate_single_banner()
	setup_variant_fields()
	seed_shop_sizes()
	assign_item_groups_to_shops()
	setup_sales_order_list()
	setup_admin_forms()
	from marketplace.sotuv.murojaat import fill_tovar_ids

	fill_tovar_ids()
	# Tovar qo'shishda kichik dialog emas, to'liq (soddalashtirilgan) forma ochilsin
	if not frappe.db.exists("Property Setter", {"doc_type": "Item", "property": "quick_entry"}):
		make_property_setter("Item", None, "quick_entry", "0", "Check", for_doctype=True, validate_fields_for_doctype=False)
	# ERPNext «Sotish narxi»ni (standard_rate) faqat yangi tovarda ko'rsatadi (depends_on __islocal) — sotuvchi narxni
	# keyin qo'ya/tushira olmas edi. Doim ko'rinsin; variantli tovarda narx variantlarda (variant_price, item_seller.js)
	if not frappe.db.exists("Property Setter", {"doc_type": "Item", "field_name": "standard_rate", "property": "depends_on"}):
		make_property_setter("Item", "standard_rate", "depends_on", "eval:!doc.has_variants && !doc.variant_of", "Code")


def setup_admin_forms():
	"""Kategoriya havolasida ID emas, nomi (mp_title): ID boshqa do'kon bilan to'qnashsa "Kiyimlar (clothes)" bo'ladi
	(permissions.item_group_before_insert), ko'rinishi esa "Kiyimlar"."""
	make_property_setter("Item Group", None, "title_field", "mp_title", "Data", for_doctype=True, validate_fields_for_doctype=False)
	make_property_setter("Item Group", None, "show_title_field_in_link", "1", "Check", for_doctype=True, validate_fields_for_doctype=False)
	# Eski kategoriyalar: ko'rinadigan nomi — ID'si (to'qnashuvsiz yaratilgan)
	frappe.db.sql("update `tabItem Group` set mp_title = item_group_name where ifnull(mp_title, '') = ''")


def setup_variant_attributes():
	if not frappe.db.exists("Item Attribute", COLOR_ATTR):
		attr = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": COLOR_ATTR})
		for name, abbr, hex_ in COLORS:
			attr.append("item_attribute_values", {"attribute_value": name, "abbr": abbr, "color_hex": hex_})
		attr.insert(ignore_permissions=True)
	if not frappe.db.exists("Item Attribute", SIZE_ATTR):
		attr = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": SIZE_ATTR})
		for size in SIZES:
			attr.append("item_attribute_values", {"attribute_value": size, "abbr": size})
		attr.insert(ignore_permissions=True)


def setup_uzs_currency():
	"""ERPNext'da UZS belgisi "лв" (bolgar levi) bo'lib keladi. So'm: 189 000 so‘m."""
	frappe.db.set_value(
		"Currency", "UZS",
		{"symbol": "so‘m", "symbol_on_right": 1, "number_format": "#,###", "smallest_currency_fraction_value": 1},
	)
	# So'mda tiyin amalda ishlatilmaydi: kasr qismini ko'rsatmaymiz
	frappe.db.set_single_value("System Settings", "currency_precision", "0")
	# Desk JS currency_precision=0 ni "berilmagan" deb oladi (0 || null) va .00 qo'shadi: 40,480,000.00.
	# Shuning uchun summa formati valyutaning o'zidan olinadi: 40,480,000 so‘m
	frappe.db.set_single_value("System Settings", "use_number_format_from_currency", 1)
	# set_single_value System Settings'ning on_update'ini chaqirmaydi, Desk esa qiymatni global default'dan o'qiydi
	frappe.db.set_default("currency_precision", "0")
	frappe.db.set_default("use_number_format_from_currency", "1")


def setup_link_results_limit():
	"""Havola ro'yxatlarida (rang, kategoriya, kontragent, o'lcham) 10 emas, 50 tagacha natija: aks holda alifboda
	11-o'rindan keyingilar (To'q ko'k, Yashil...) yozmaguncha ko'rinmaydi. 50 — Frappe ruxsat bergan eng ko'pi."""
	frappe.db.set_single_value("System Settings", "link_field_results_limit", 50)
	# set_single_value System Settings'ning on_update'ini chaqirmaydi, Desk esa qiymatni global default'dan o'qiydi
	frappe.db.set_default("link_field_results_limit", "50")


def disable_perpetual_inventory():
	"""Do'konlar savdosi platforma kitoblariga yozilmaydi: ombor faqat qoldiqni yuritadi, GL yozuvi yo'q.

	Ombor harakati boshlangan Company'ga tegilmaydi — u yerda o'zgartirish hisobni buzadi.
	"""
	for company in frappe.get_all("Company", filters={"enable_perpetual_inventory": 1}, pluck="name"):
		if not frappe.db.exists("Stock Ledger Entry", {"company": company}):
			frappe.db.set_value("Company", company, "enable_perpetual_inventory", 0)


def setup_manager_role():
	if not frappe.db.exists("Role", MANAGER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": MANAGER_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	for doctype, rights in MANAGER_PERMISSIONS.items():
		add_permission(doctype, MANAGER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, MANAGER_ROLE, 0, right, 1, validate=False)
	set_level_permissions(MANAGER_ROLE, MANAGER_LEVEL_PERMISSIONS)


def setup_seller_role():
	if not frappe.db.exists("Role", SELLER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": SELLER_ROLE, "desk_access": 1}).insert(
			ignore_permissions=True
		)

	for doctype, rights in SELLER_PERMISSIONS.items():
		add_permission(doctype, SELLER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, SELLER_ROLE, 0, right, 1, validate=False)
	for doctype, rights in SELLER_REVOKED.items():
		for right in rights:
			update_permission_property(doctype, SELLER_ROLE, 0, right, 0, validate=False)
	set_level_permissions(SELLER_ROLE, SELLER_LEVEL_PERMISSIONS)


# Sotuv menejeri: panel API'lari (sotuv/api.py) o'zi tekshiradi va do'kon bo'yicha cheklaydi; bu — ro'yxatlar uchun
SALES_PERMISSIONS = {
	"Telefon Qongiroq": ["read"],
	"Aloqa Yozuvi": ["read"],
	# Instagram murojaatlari (sotuv/murojaat.py) — menejer holat va qayta qo'ng'iroq sanasini yozadi
	"Murojaat": ["read", "write"],
}


def setup_sales_role():
	if not frappe.db.exists("Role", SALES_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": SALES_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	for doctype, rights in SALES_PERMISSIONS.items():
		add_permission(doctype, SALES_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, SALES_ROLE, 0, right, 1, validate=False)


def setup_courier_role():
	if not frappe.db.exists("Role", COURIER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": COURIER_ROLE, "desk_access": 1}).insert(ignore_permissions=True)
	for doctype, rights in COURIER_PERMISSIONS.items():
		add_permission(doctype, COURIER_ROLE, 0)
		for right in rights:
			update_permission_property(doctype, COURIER_ROLE, 0, right, 1, validate=False)


def set_level_permissions(role, levels):
	for doctype, by_level in levels.items():
		for level, rights in by_level.items():
			add_permission(doctype, role, level)
			for right in rights:
				update_permission_property(doctype, role, level, right, 1, validate=False)


def migrate_single_banner():
	"""Eski bitta banner (banner_title/banner_image) karuselning birinchi slaydiga ko'chadi."""
	for shop in frappe.get_all("Shop", filters={"banner_image": ["is", "set"]}, pluck="name"):
		if frappe.db.exists("Shop Banner", {"parent": shop, "parenttype": "Shop"}):
			continue
		doc = frappe.get_doc("Shop", shop)
		doc.append(
			"banners",
			{"image": doc.banner_image, "label": doc.banner_label, "title": doc.banner_title, "item_group": doc.banner_group},
		)
		doc.flags.ignore_permissions = True
		doc.save()


# Variant yaratilganda andozadan (template) ko'chiriladigan maydonlar (ERPNext: Item Variant Settings)
VARIANT_COPY_FIELDS = (
	"shop", "is_published", "item_group", "mxik_code", "package_code", "old_price", "spec_line",
	"wholesale_price", "wholesale_min_qty", "variant_price", "description", "mp_majburiy", "mp_tez_kunda",
)


def setup_variant_fields():
	settings = frappe.get_single("Item Variant Settings")
	have = {d.field_name for d in settings.fields}
	missing = [f for f in VARIANT_COPY_FIELDS if f not in have]
	if missing:
		for f in missing:
			settings.append("fields", {"field_name": f})
		settings.flags.ignore_permissions = True
		settings.save()


def assign_item_groups_to_shops():
	"""Hali do'konga bog'lanmagan kategoriyalar: faqat bitta do'kon tovarlari ishlatsa, o'sha do'konniki bo'ladi.
	Ota kategoriya (masalan Kiyim) — barcha bolalari bitta do'konniki bo'lsa, o'sha do'konga."""
	used = {}
	for r in frappe.get_all("Item", filters={"shop": ["is", "set"]}, fields=["item_group", "shop"]):
		used.setdefault(r.item_group, set()).add(r.shop)
	# Avval barglar (eng ichki kategoriyalar), keyin ularning otalari
	groups = sorted(
		frappe.get_all("Item Group", fields=["name", "lft", "rgt", "is_group", "shop"]), key=lambda g: g.rgt - g.lft
	)
	owner = {}
	for g in groups:
		shops = set(used.get(g.name, set()))
		if g.is_group:
			for child in groups:
				if g.lft < child.lft and child.rgt < g.rgt and owner.get(child.name):
					shops.add(owner[child.name])
		if len(shops) == 1 and g.lft != 1:
			owner[g.name] = shops.pop()
	for name, shop in owner.items():
		if not frappe.db.get_value("Item Group", name, "shop"):
			frappe.db.set_value("Item Group", name, "shop", shop, update_modified=False)


def seed_shop_sizes():
	"""Bir marta: O'lchamlar ro'yxati bo'sh do'konga uning tovarlarida ishlatilgan o'lchamlar yoziladi
	(va eski Shop.olchamlar matni, agar ustun hali bazada bo'lsa)."""
	from marketplace.seller_desk import _split, remember_shop_sizes

	has_old = frappe.db.has_column("Shop", "olchamlar")
	for shop in frappe.get_all("Shop", pluck="name"):
		if frappe.db.exists("Olcham", {"shop": shop}):
			continue
		sizes = _split(frappe.db.get_value("Shop", shop, "olchamlar")) if has_old else []
		sizes += frappe.db.sql(
			"""select distinct a.attribute_value from `tabItem Variant Attribute` a
			join `tabItem` i on i.name = a.parent
			where i.shop = %s and a.attribute = %s and ifnull(a.attribute_value, '') != ''""",
			(shop, SIZE_ATTR),
			pluck=True,
		)
		if sizes:
			from marketplace.storefront import _size_key

			rank = {v: i for i, v in enumerate(SIZES)}
			remember_shop_sizes(shop, sorted(dict.fromkeys(sizes), key=lambda z: _size_key(z, rank)))


def setup_sales_order_list():
	"""Buyurtmalar ro'yxati ustunlari: mijoz, telefoni, holat, do'kon, to'lov, summa.

	ERPNext'ning "% Amount Billed" (hisob-faktura — Sales Invoice) ustuni olinadi: do'konlarda buxgalteriya yo'q,
	u doim 0%. "% Delivered" o'rniga holat belgisi (Topshirilgan) bor."""
	import json

	for field in ("per_billed", "per_delivered"):
		make_property_setter("Sales Order", field, "in_list_view", "0", "Check", validate_fields_for_doctype=False)
	make_property_setter("Sales Order", "billing_status", "in_standard_filter", "0", "Check", validate_fields_for_doctype=False)
	columns = [
		("customer_name", "Mijoz"),
		("customer_phone", "Telefon"),
		("status_field", "Holati"),
		("shop", "Do'kon"),
		("payment_status", "To'lov holati"),
		("payment_method", "To'lov turi"),
		("grand_total", "Summa"),
		("name", "ID"),
	]
	# Toza saytda yozuv hali yo'q: lug'atdan yaratilgan hujjatda is_new() False — shuning uchun exists bo'yicha
	exists = frappe.db.exists("List View Settings", "Sales Order")
	settings = (
		frappe.get_doc("List View Settings", "Sales Order")
		if exists
		else frappe.get_doc({"doctype": "List View Settings", "name": "Sales Order"})
	)
	# Telefon to'liq sig'sin: +998 99 801 10 26
	widths = {"customer_phone": 170}
	settings.fields = json.dumps(
		[{"fieldname": f, "label": label, **({"width": widths[f]} if f in widths else {})} for f, label in columns]
	)
	settings.flags.ignore_permissions = True
	settings.save() if exists else settings.insert()
