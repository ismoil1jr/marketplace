import frappe

no_cache = 1

LANGS = ("uz", "ru")
COOKIE = "mh_til"

# Bosh sahifa matnlari: o'zbekcha va ruscha (faqat shu sahifa — do'kon saytlari o'zbekcha qoladi)
T = {
	"uz": {
		"title": "magazinlar.uz — do‘koningiz uchun onlayn savdo",
		"description": "Instagramdagi savdoni tartibli onlayn do‘konga aylantiring: o‘z sayti, Payme va Click to‘lovi do‘kon kassasiga, Instagram murojaatlari, sotuv menejeri paneli va kuryer.",
		"cabinet": "Kabinet",
		"open": "Do‘kon ochish",
		"h1": "Direktdagi savdoni tartibli onlayn do‘konga aylantiring",
		"lead": "O‘z saytingiz, Payme va Click to‘lovi to‘g‘ridan-to‘g‘ri do‘kon kassasiga, Instagram reklamadan kelgan murojaatlar va kuryer — bitta panelda. Do‘konni biz ochib, sozlab beramiz.",
		"see_shops": "Do‘konlarni ko‘rish",
		"r_form": "Instagram reklama formasi",
		"r_name": "Dilnoza R.",
		"r_item": "Ertaklar kitobi",
		"r_call": "Menejer qo‘ng‘iroq qildi",
		"r_yes": "Oladi",
		"r_order": "Buyurtma №1043",
		"r_paid": "Payme orqali to‘landi",
		"r_sum": "189 000 so‘m",
		"r_courier": "Kuryer yo‘lda",
		"r_addr": "Chilonzor, 9-kvartal",
		"r_caption": "Murojaatdan yetkazishgacha — bitta panelda",
		"shops": "Do‘konlar",
		"shops_lead": "Xarid to‘g‘ridan-to‘g‘ri do‘kondan: to‘lov Payme, Click yoki naqd, yetkazish kuryer orqali.",
		"search": "Do‘kon nomi yoki shahar",
		"search_label": "Do‘konlarni qidirish",
		"not_found": "Bunday do‘kon topilmadi",
		"no_shops": "Do‘konlar tez orada qo‘shiladi",
		"soon": "Tez kunda",
		"shown": "{0} ta",
		"owner_h": "Do‘kon egasi nima oladi",
		"features": [
			("site", "O‘z sayti", "magazinlar.uz/s/do‘koningiz: tovarlar, rang va o‘lchamlar, qoldiq — mijoz o‘zi tanlab buyurtma beradi."),
			("cash", "Pul — o‘z kassangizga", "Payme va Click to‘lovi to‘g‘ridan-to‘g‘ri do‘koningiz hisobiga tushadi. Naqd to‘lov ham bor."),
			("insta", "Instagram murojaatlari", "Reklamadagi formani to‘ldirgan mijoz darhol panelga tushadi — qaysi tovar bo‘yicha yozgani bilan."),
			("call", "Sotuv menejeri paneli", "Qo‘ng‘iroq yozuvlari, natija va qayta qo‘ng‘iroq eslatmasi — birorta mijoz unutilmaydi."),
			("truck", "Kuryer va naqd hisobi", "Kuryer faqat tasdiqlangan buyurtmani ko‘radi, yetkazganini va olgan pulini belgilaydi."),
			("box", "Ombor nazorati", "Kirim, qoldiq va tugayotgan tovarlar haqida har kuni xabar."),
			("bell", "Telegram xabarlari", "Yangi buyurtma tushishi bilan Telegramga xabar keladi."),
			("people", "Doimiy mijozlar", "Buyurtmasi yetkazilgan mijoz o‘zi doimiy mijozlar ro‘yxatiga qo‘shiladi."),
		],
		"how": "Do‘kon qanday ochiladi",
		"steps": [
			"Qo‘ng‘iroq qilasiz yoki Telegramda yozasiz",
			"Do‘koningizni ochamiz: sayt, kassa va Instagramni ulaymiz",
			"Tovarlarni qo‘shasiz — buyurtmalar kela boshlaydi",
		],
		"faq": "Ko‘p so‘raladigan savollar",
		"faqs": [
			("Pul kimga tushadi?", "To‘g‘ridan-to‘g‘ri do‘koningiz kassasiga. Payme va Click bilan shartnoma do‘konning o‘z nomidan tuziladi."),
			("Dasturchi kerakmi?", "Yo‘q. Do‘konni biz ochib, sozlab beramiz. Tovar, narx va rasmlarni o‘zingiz qo‘shasiz."),
			("Instagram reklamasi bilan qanday ishlaydi?", "Reklamadagi forma do‘koningizga ulanadi. Mijoz ismi va telefonini qoldiradi — murojaat qaysi tovar bo‘yicha ekani bilan sotuv paneliga tushadi. Menejer qo‘ng‘iroq qiladi va buyurtma kuryerga o‘tadi."),
			("Qaysi do‘konlar uchun?", "Kiyim, kitob, mebel, tekstil va boshqalar. Har bir do‘konning o‘z ranglari, o‘lchamlari, ombori va xodimlari bo‘ladi."),
			("Narxi qancha?", "Do‘kon hajmi va kerakli xizmatlarga bog‘liq. Qo‘ng‘iroq qiling — aniq aytamiz."),
		],
		"cta": "Do‘koningizni ochaylik",
		"cta_lead": "Qo‘ng‘iroq qiling yoki Telegramda yozing — savollarga javob beramiz va do‘konni sozlab beramiz.",
		"call": "Qo‘ng‘iroq qilish",
		"telegram": "Telegramda yozish",
		"company": "«ORANGE TEAM» MChJ",
	},
	"ru": {
		"title": "magazinlar.uz — онлайн-магазин для вашего бизнеса",
		"description": "Превратите продажи в Instagram в настоящий онлайн-магазин: свой сайт, оплата Payme и Click прямо в кассу магазина, заявки из Instagram, панель менеджера продаж и курьер.",
		"cabinet": "Кабинет",
		"open": "Открыть магазин",
		"h1": "Превратите продажи в директе в настоящий онлайн-магазин",
		"lead": "Свой сайт, оплата Payme и Click прямо в кассу магазина, заявки из рекламы в Instagram и курьер — в одной панели. Мы откроем и настроим магазин за вас.",
		"see_shops": "Смотреть магазины",
		"r_form": "Форма рекламы в Instagram",
		"r_name": "Дилноза Р.",
		"r_item": "Книга сказок",
		"r_call": "Менеджер позвонил",
		"r_yes": "Купит",
		"r_order": "Заказ №1043",
		"r_paid": "Оплачено через Payme",
		"r_sum": "189 000 сум",
		"r_courier": "Курьер в пути",
		"r_addr": "Чиланзар, 9-квартал",
		"r_caption": "От заявки до доставки — в одной панели",
		"shops": "Магазины",
		"shops_lead": "Покупайте напрямую у магазина: оплата Payme, Click или наличными, доставка курьером.",
		"search": "Название магазина или город",
		"search_label": "Поиск магазинов",
		"not_found": "Такой магазин не найден",
		"no_shops": "Магазины скоро появятся",
		"soon": "Скоро",
		"shown": "{0}",
		"owner_h": "Что получает владелец магазина",
		"features": [
			("site", "Свой сайт", "magazinlar.uz/s/ваш-магазин: товары, цвета и размеры, остатки — клиент сам выбирает и оформляет заказ."),
			("cash", "Деньги — в вашу кассу", "Оплата Payme и Click поступает прямо на счёт вашего магазина. Есть и оплата наличными."),
			("insta", "Заявки из Instagram", "Клиент, заполнивший форму в рекламе, сразу попадает в панель — вместе с товаром, о котором спрашивал."),
			("call", "Панель менеджера продаж", "Записи звонков, итог разговора и напоминание перезвонить — ни один клиент не потеряется."),
			("truck", "Курьер и учёт наличных", "Курьер видит только подтверждённые заказы и отмечает доставку и полученные деньги."),
			("box", "Контроль склада", "Приход, остатки и ежедневное уведомление о заканчивающихся товарах."),
			("bell", "Уведомления в Telegram", "О каждом новом заказе сразу приходит сообщение в Telegram."),
			("people", "Постоянные клиенты", "После доставки клиент сам попадает в список постоянных покупателей."),
		],
		"how": "Как открыть магазин",
		"steps": [
			"Вы звоните или пишете нам в Telegram",
			"Мы открываем магазин: подключаем сайт, кассу и Instagram",
			"Вы добавляете товары — начинают приходить заказы",
		],
		"faq": "Частые вопросы",
		"faqs": [
			("Кому поступают деньги?", "Напрямую в кассу вашего магазина. Договор с Payme и Click заключается на ваш магазин."),
			("Нужен ли программист?", "Нет. Мы откроем и настроим магазин. Товары, цены и фото вы добавляете сами."),
			("Как это работает с рекламой в Instagram?", "Форма из рекламы подключается к вашему магазину. Клиент оставляет имя и телефон — заявка попадает в панель продаж вместе с товаром. Менеджер звонит, и заказ уходит курьеру."),
			("Для каких магазинов?", "Одежда, книги, мебель, текстиль и другое. У каждого магазина свои цвета, размеры, склад и сотрудники."),
			("Сколько стоит?", "Зависит от размера магазина и нужных функций. Позвоните — назовём точную цену."),
		],
		"cta": "Давайте откроем ваш магазин",
		"cta_lead": "Позвоните или напишите в Telegram — ответим на вопросы и настроим магазин.",
		"call": "Позвонить",
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
	Admin panel — /admin. UZ/RU — faqat shu sahifa."""
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
	context.is_staff = frappe.session.user != "Guest" and frappe.get_cached_value("User", frappe.session.user, "user_type") == "System User"
	context.asset_version = storefront.asset_version()
	context.year = frappe.utils.getdate().year
