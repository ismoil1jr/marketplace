import frappe
from frappe.utils import get_url

no_cache = 1

LANGS = ("uz", "ru")
COOKIE = "mh_til"

# Bosh sahifa matnlari: o'zbekcha va ruscha (faqat shu sahifa — do'kon saytlari o'zbekcha qoladi).
# Qisqa: sahifa tushuntirmaydi, ko'rsatadi (chek-sxema) va qo'ng'iroqqa chaqiradi.
T = {
	"uz": {
		"title": "magazinlar.uz — do‘koningiz uchun onlayn savdo",
		"description": "Instagramdagi savdoni onlayn do‘konga aylantiring: o‘z sayti, Payme va Click to‘lovi do‘kon kassasiga, Instagram murojaatlari, sotuv menejeri va kuryer — bitta panelda.",
		"call": "Qo‘ng‘iroq qilish",
		"h1": "Direktdagi savdoni tartibli onlayn do‘konga aylantiring",
		"lead": "O‘z saytingiz, Payme va Click to‘lovi do‘kon kassasiga, Instagram murojaatlari va kuryer — bitta panelda. Do‘konni biz ochib beramiz.",
		"see_shops": "Do‘konlarni ko‘rish",
		"shops": "Do‘konlar",
		"search": "Do‘kon nomi yoki shahar",
		"search_label": "Do‘konlarni qidirish",
		"not_found": "Bunday do‘kon topilmadi",
		"no_shops": "Do‘konlar tez orada qo‘shiladi",
		"soon": "Tez kunda",
		"shown": "{0} ta",
		"how": "Do‘kon qanday ochiladi",
		"steps": [
			"Qo‘ng‘iroq qilasiz yoki Telegramda yozasiz",
			"Do‘koningizni ochamiz: sayt, kassa va Instagramni ulaymiz",
			"Tovarlarni qo‘shasiz — buyurtmalar kela boshlaydi",
		],
		"cta": "Do‘koningizni ochaylik",
		"cta_lead": "Qo‘ng‘iroq qiling yoki Telegramda yozing.",
		"telegram": "Telegramda yozish",
		"company": "«ORANGE TEAM» MChJ",
	},
	"ru": {
		"title": "magazinlar.uz — онлайн-магазин для вашего бизнеса",
		"description": "Превратите продажи в Instagram в онлайн-магазин: свой сайт, оплата Payme и Click прямо в кассу магазина, заявки из Instagram, менеджер продаж и курьер — в одной панели.",
		"call": "Позвонить",
		"h1": "Превратите продажи в директе в онлайн-магазин",
		"lead": "Свой сайт, оплата Payme и Click в кассу магазина, заявки из Instagram и курьер — в одной панели. Магазин откроем мы.",
		"see_shops": "Смотреть магазины",
		"shops": "Магазины",
		"search": "Название магазина или город",
		"search_label": "Поиск магазинов",
		"not_found": "Такой магазин не найден",
		"no_shops": "Магазины скоро появятся",
		"soon": "Скоро",
		"shown": "{0}",
		"how": "Как открыть магазин",
		"steps": [
			"Вы звоните или пишете нам в Telegram",
			"Мы открываем магазин: подключаем сайт, кассу и Instagram",
			"Вы добавляете товары — начинают приходить заказы",
		],
		"cta": "Давайте откроем ваш магазин",
		"cta_lead": "Позвоните или напишите в Telegram.",
		"telegram": "Написать в Telegram",
		"company": "ООО «ORANGE TEAM»",
	},
}


def _lang():
	"""?til=ru|uz (eslab qolinadi), keyin cookie, aks holda o'zbekcha."""
	asked = (frappe.form_dict.get("til") or "").lower()
	if asked in LANGS:
		if getattr(frappe.local, "cookie_manager", None):
			frappe.local.cookie_manager.set_cookie(COOKIE, asked, max_age=365 * 86400)
		return asked
	saved = frappe.request.cookies.get(COOKIE) if getattr(frappe, "request", None) else None
	return saved if saved in LANGS else "uz"


def _count(n, lang):
	if lang == "uz":
		return f"{n} ta tovar"
	form = "товар" if n % 10 == 1 and n % 100 != 11 else "товара" if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else "товаров"
	return f"{n} {form}"


def get_context(context):
	"""magazinlar.uz bosh sahifasi (hooks.home_page): do'kon egalariga platforma va faol do'konlar ro'yxati.
	Admin panel — /admin (sahifada unga havola yo'q). UZ/RU — faqat shu sahifa."""
	from marketplace import storefront

	lang = _lang()
	t = frappe._dict(T[lang])
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
		s.count_label = _count(s.item_count, lang) if s.item_count else t.soon
	context.shops = shops
	context.lang = lang
	context.t = t
	# Sozlamalar hali saqlanmagan bo'lsa — maydonning standart qiymati (Single'da default bazaga yozilmaydi)
	context.phone = frappe.db.get_single_value("Marketplace Settings", "aloqa_telefon") or (
		frappe.get_meta("Marketplace Settings").get_field("aloqa_telefon").default or ""
	)
	context.phone_href = "".join(ch for ch in context.phone if ch.isdigit() or ch == "+")
	context.asset_version = storefront.asset_version()
	context.og_image = get_url(f"/assets/marketplace/images/og.png?v={context.asset_version}")
	context.year = frappe.utils.getdate().year
