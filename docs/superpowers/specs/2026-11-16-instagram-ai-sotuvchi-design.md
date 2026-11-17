# Instagram AI sotuvchi — dizayn

Sana: 2026-11-16, yangilandi 2026-11-17 · Holat: ko‘rib chiqishda

## Maqsad

Panda Books (do‘kon: Pandoo) Instagramida AI mijozlarga darhol javob beradi. U uchta joyni kuzatadi:
1. barcha post va reellar ostidagi **izohlar**;
2. reklama (target) videolari ostidagi **izohlar**;
3. **Direct** (DM) xabarlari.

AI do‘kon nomidan, mijoz yozgan tilda (o‘zbek lotin/kirill yoki rus) javob beradi. Javob avval salom bilan boshlanadi, keyin savolga aniq javob beradi. Misollar:

- «Narxi qancha?» → «Assalomu alaykum! «Panda Books» kitobining narxi — <saytdagi narx> so‘m.»
- «Bormi?» → «Assalomu alaykum! Ha, albatta bor.»
  - Ombordagi aniq son hech qachon aytilmaydi.
  - Qoldiq 0 bo‘lsa: «Hozircha tugagan, menejerimiz aniqlab beradi».

ManyChat ishlatilmaydi. AI — Gemini API. Kalit saytdagi **Telefoniya Sozlamalari → Gemini API kalit** maydonida turadi; qo‘ng‘iroq tahlili ham shu kalit bilan ishlaydi.

**Bunga kirmaydi:** AI qo‘ng‘iroq qilmaydi (Kamoliddin aka, 2026-11-16), buyurtmani o‘zi rasmiylashtirmaydi, Telegram va Facebook Messenger’ga javob bermaydi.

## Bosqichlar

1. **Izohlar** (birinchi navbatda): oddiy postlar, reellar va reklama videolari.
2. **Direct:** shu kod ustiga qo‘shiladi.

Kod har bir do‘kon uchun ishlaydi. Boshqa do‘kon yoki sinov akkaunti ham Shop formasidan ulanadi.

## Meta’dan ma’lumot olish

App Review talab qilinmasligi uchun sayt har daqiqada Instagram’ni o‘zi tekshiradi (poll). Izohlar webhooki faqat Advanced Access bilan ishlaydi (App Review + biznesni tasdiqlash), shuning uchun u ishlatilmaydi.

- **Post va reel izohlari:**
  - `GET /{ig-user-id}/media` — oxirgi ~25 post;
  - `GET /{media-id}/comments` — oxirgi 15 daqiqadagi yangilari.
- **Reklama izohlari:**
  - `GET /act_{ad-account}/ads?effective_status=["ACTIVE"]&fields=creative{effective_instagram_media_id}` — faol reklamalarning Instagram media ID’lari;
  - keyin ular xuddi postlar kabi tekshiriladi.
  - Buning uchun Ismoilga reklama kabinetiga (ad account) kirish huquqi va tokenda `ads_read` ruxsati kerak.
- **Izohga javob:** `POST /{comment-id}/replies` (`instagram_manage_comments`).
- **Direct (2-bosqich):**
  - olish: `GET /{page-id}/conversations?platform=instagram`;
  - javob: `POST /{page-id}/messages`.
- **Takrorlanmaslik:** har bir izoh yoki xabar ID’si bazada saqlanadi. Bitta izohga faqat bitta javob yoziladi. Do‘konning o‘z izohlari va javoblariga javob yozilmaydi.
- **Ruxsat darajasi:** Panda Books akkauntini Ismoil boshqaradi («Полный контроль»), shuning uchun Standard Access yetarli. Meta «разработка» rejimida yuborishni rad etsa, ilovaga ikonka qo‘yilib, «рабочий режим»ga o‘tkaziladi (App Review kerak emas).
- **Limit:** Meta limit xatosi kelsa (kod 4/17/32/613), do‘kon tekshiruvi 15 daqiqaga to‘xtatiladi.

**Token ruxsatlari** (Pandoo qayta ulanadi, jami 10 ta):
- `pages_show_list`
- `pages_read_engagement`
- `pages_manage_metadata`
- `pages_manage_ads`
- `leads_retrieval`
- `business_management`
- `instagram_basic`
- `instagram_manage_comments`
- `instagram_manage_messages`
- `ads_read`

## AI qoidalari

- Javob faqat quyidagi ma’lumotdan tuziladi:
  - **do‘kon katalogi:** nom, narx (Item Price), qoldiq bor/yo‘q, magazinlar.uz havolasi;
  - **«AI uchun ma’lumot»** matni (Shop maydoni): yetkazib berish, to‘lov, ish vaqti, buyurtma qanday beriladi.
- **Izohga javob:** 1–2 gap. **DM javobi:** 1–3 gap.
- Narx, chegirma yoki muddat o‘ylab topilmaydi. Ma’lumot yo‘q bo‘lsa: «Menejerimiz Direct’da aniqlab beradi».
- Javob berilmaydigan izohlar: spam, faqat emoji, «rahmat», haqorat, raqib reklamasi. Bularni AI `javob_kerak=false` deb belgilaydi.
- Mijoz telefon raqam qoldirsa (izohda yoki DM’da), `murojaat.save_lead()` orqali **Murojaat** yoziladi:
  - `manba="Instagram"`;
  - `tashqi_id="ig:<user_id>:<sana>"`.
- **Gemini so‘rovi:**
  - `responseMimeType: application/json`;
  - javob shakli: `{javob_kerak, javob, til, telefon, ism, tovar_kodi}`;
  - temperature 0.3;
  - model va zaxira model mavjud `stt` sozlamalaridan olinadi.
  - JSON buzilsa, hech narsa yuborilmaydi va xato yoziladi.
- **Xarajat:** Flash modelda bitta javob taxminan $0.001–0.002 turadi. $5 kredit taxminan 3–5 ming javobga yetadi.

## Rejimlar (Shop → «Instagram AI»)

- **O‘chiq**
- **Sinov:** AI javobni yozadi, lekin Instagram’ga yubormaydi; javob saytda «Qoralama» bo‘lib turadi.
- **Yoqilgan:** javoblar avtomatik yuboriladi.

Qoralama yoki yuborilgan javobni operator saytda ko‘radi. Qoralamani **«Yuborish»** tugmasi bilan qo‘lda yuborsa ham bo‘ladi.

## Ma’lumotlar

**Shop**ga yangi maydonlar:
- `ig_ai_rejim` (O‘chiq / Sinov / Yoqilgan);
- `ig_ai_malumot` (Text);
- `ig_user_id`: ulanganda o‘zi to‘ladi;
- `meta_ad_account`: reklama kabineti ID’si; ulanganda ro‘yxatdan tanlanadi.

**Instagram Xabar** (yangi doctype, ro‘yxat ko‘rinishi):
- `shop`;
- `turi` (Izoh / DM);
- `tashqi_id` (comment yoki message id, unikal);
- `media_id`, `media_havola`;
- `mijoz_id`, `username`;
- `matn`;
- `ai_javob`;
- `holat` (Yangi / Qoralama / Yuborildi / Javobsiz / Xato);
- `xato`, `vaqt`, `murojaat`.

Ko‘rish huquqi Murojaat bilan bir xil (`shop_query`): admin hammasini ko‘radi; do‘kon egasi va sotuv menejerlari faqat o‘z do‘konini ko‘radi.

## Kod tuzilishi

- `sotuv/meta.py`:
  - `connect()` qo‘shimcha ravishda `instagram_business_account` va reklama kabinetini saqlaydi;
  - `_graph()` qayta ishlatiladi.
- Yangi `sotuv/instagram.py`:
  - `poll()` — har daqiqada, hooks orqali;
  - izoh va reklama izohlarini yig‘ish;
  - Instagram Xabar yozish;
  - javobni yuborish.
- Yangi `sotuv/ig_ai.py`:
  - prompt tuzish;
  - Gemini chaqiruvi;
  - JSON tekshiruvi;
  - telefonni ajratish.
  - Graph API’ga tegmaydi, shuning uchun alohida test qilinadi.
- AI va yuborish fon ishida bajariladi (`frappe.enqueue`, `job_id=tashqi_id`).

## Xatolar

- **Gemini xatosi yoki kvota tugashi:** hech narsa yuborilmaydi, holat «Xato» bo‘ladi, do‘kon «Oxirgi holat» maydoniga yoziladi.
- **Meta rad etsa:** holat «Xato» va sababi yoziladi. Qayta urinishni operator tugma bilan qiladi.
- **Bitta mijozga** soatiga 10 tadan ortiq AI javob yuborilmaydi.

## Test

- Unit testlar quyidagilar uchun yoziladi:
  - izoh va reklama media ro‘yxatini yig‘ish;
  - dublikat;
  - o‘z izohini o‘tkazib yuborish;
  - AI JSON tekshiruvi;
  - qoldiq so‘zi («ha, bor»; son aytilmaydi);
  - telefon ajratish;
  - rejimlar (Sinov yubormaydi).
- Graph va Gemini mock qilinadi.
- Prod’da Panda Books avval «Sinov» rejimida ishlaydi; javoblar ko‘rib chiqilgach, «Yoqilgan»ga o‘tkaziladi.

## Foydalanuvchi qiladigan ishlar

1. SMM’chi Ismoilga reklama kabinetiga kirish huquqini beradi: Business Suite → Настройки → Рекламные аккаунты → Добавить людей → «Просмотр эффективности» yetarli.
2. Pandoo’ni 10 ta ruxsat bilan qayta ulash. Ulash oynasida Panda Books Instagrami va reklama kabineti ham belgilanadi.
3. «AI uchun ma’lumot» matnini tasdiqlash (qoralamani Claude yozadi).
4. Gemini kaliti Telefoniya Sozlamalarida turganini tekshirish.
