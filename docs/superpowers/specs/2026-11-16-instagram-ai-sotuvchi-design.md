# Instagram AI sotuvchi — dizayn

Sana: 2026-11-16 · Holat: ko‘rib chiqishda

## Maqsad

Pandoo’ning Instagramidagi DM va izohlarga AI darhol javob beradi. Hozir mijozlar soatlab javob kutib qolmoqda.

AI quyidagilarni qiladi:
- tovar, narx va bor-yo‘qligi haqida javob beradi;
- sotib olmoqchi bo‘lgan mijozdan ism va telefon oladi;
- olgan ma’lumotdan saytda **Murojaat** yaratadi, keyin operatorlar mijozga qo‘ng‘iroq qiladi.

**Bunga kirmaydi** (Kamoliddin aka, 2026-11-16):
- AI qo‘ng‘iroq qilmaydi;
- Telegram va Facebook Messenger’ga javob bermaydi;
- buyurtmani o‘zi rasmiylashtirmaydi.

Dastlab faqat Pandoo’da ishlaydi, lekin sozlamalar har bir do‘kon uchun alohida. Boshqa do‘konlar o‘z sahifasini ulab, AI’ni yoqsa, ularda ham ishlaydi.

## Meta cheklovlari

Meta hujjatlaridan (Instagram API, Facebook Login orqali):

1. **Webhook faqat ilova «рабочий режим»da (Live) bo‘lganda keladi.** Live qilish uchun App Review shart emas. Ilovaga belgi (ikonka), maxfiylik va ma’lumot o‘chirish havolasi va kategoriya kerak. Havolalar va kategoriya allaqachon to‘ldirilgan.
2. **Izohlar (`comments`) webhooki Advanced Access talab qiladi.** Buning uchun App Review va biznes tasdiqlash kerak, bu bir necha hafta oladi.

Shuning uchun xabarlar ikki yo‘l bilan olinadi:
- **Webhook:** DM’lar shu zahoti keladi (Live’dan keyin).
- **Har daqiqada tortib olish (poll):** DM’lar `/{page-id}/conversations?platform=instagram` dan, izohlar so‘nggi postlarning `comments` ro‘yxatidan olinadi. Bu App Review’siz, faqat o‘z akkauntimizda ishlaydi.

Ikkalasi ham bir xil xabar ID’si bo‘yicha dublikatni o‘tkazib yuboradi. Ilova Live bo‘lmaguncha ham, App Review bo‘lmaguncha ham bot poll orqali 1 daqiqa kechikish bilan ishlayveradi.

## Ishlash tartibi

**DM**
1. Yangi xabar keladi.
2. Suhbat yoziladi.
3. AI o‘chiq yoki suhbat menejerga o‘tgan bo‘lsa, shu yerda to‘xtaydi. Aks holda Gemini javob tuzadi va javob Send API orqali yuboriladi.

**Izoh**
1. Yangi izoh keladi.
2. AI izohga javob kerakmi yoki yo‘qligini o‘zi baholaydi. Spam, faqat emoji yoki rahmat bo‘lsa, javob bermaydi.
3. Javob kerak bo‘lsa, izohga qisqa ochiq javob yozadi («Batafsil Direct’ga yozdik») va shu izoh egasiga bitta private reply DM yuboradi.
4. Mijoz DM’da javob qaytarsa, suhbat oddiy DM kabi davom etadi.

**Lid**
1. AI suhbatdan telefon raqamini ajratib olsa (zaxira sifatida regex ham tekshiradi), `murojaat.save_lead()` chaqiriladi. Unga quyidagilar beriladi:
   - `manba="Instagram"`;
   - ism;
   - tovar;
   - izoh: suhbat qisqacha mazmuni;
   - `tashqi_id = "ig:<mijoz_id>:<sana>"` (bir kunda bitta murojaat).
2. Operatorlarga mavjud `_notify` orqali saytda bildirishnoma boradi.

**Menejerga o‘tish.** AI quyidagi hollarda jim bo‘ladi va suhbat «Menejerda» holatiga o‘tadi:
- mijoz operator yoki odam so‘rasa;
- AI javobga ishonchi yo‘qligini bildirsa;
- shikoyat bo‘lsa;
- menejer Instagram ilovasining o‘zidan javob yozsa. Bunda bizning yuborgan ro‘yxatimizda yo‘q bo‘lgan sahifa xabari (echo) kelgani aniqlanadi.

Suhbat 24 soat davomida yangi xabar bo‘lmasa, yoki menejer tugma bilan qaytarsa, yana AI’ga qaytadi.

## AI qoidalari

- Javoblar faqat berilgan ma’lumotdan tuziladi:
  - do‘kon katalogi: nom, narx (Item Price), qoldiq bor/yo‘q, magazinlar.uz’dagi havola;
  - do‘kon yozib qo‘ygan **«AI uchun ma’lumot»** matni: yetkazib berish, to‘lov, ish vaqti, uslub.
- Narx, chegirma yoki muddatni o‘zidan o‘ylab topmaydi. Ma’lumot yo‘q bo‘lsa, «menejer aniqlab beradi» deydi va telefon so‘raydi.
- Mijoz qaysi tilda yozsa (o‘zbek lotin/kirill yoki rus), o‘sha tilda javob beradi. Javoblar qisqa, 1–3 gap.
- Javob qat’iy JSON ko‘rinishida bo‘ladi: `{javob, ism, telefon, tovar_kodi, menejerga, izohga_javob_kerak}`. JSON buzilsa, mijozga hech narsa yuborilmaydi va xato yoziladi.
- Gemini kaliti va modeli mavjud **Telefoniya Sozlamalari**dan olinadi (`stt.api_key()` va model zaxirasi). Yangi kalit kerak emas.
- Xarajat taxminan: Flash modelda 1000 ta suhbat uchun $5–10.

## Ma’lumotlar

**Shop**ga yangi maydonlar («Instagram AI» bo‘limi):
- `ig_ai_rejim`: **O‘chiq / Sinov / Yoqilgan**. «Sinov» rejimida AI javobni faqat qoralama sifatida yozadi va mijozga yubormaydi. Operatorlar AI qanday javob berishini 1–2 kun ko‘rib, keyin yoqadi.
- `ig_ai_malumot`: «AI uchun ma’lumot» matni.
- `ig_user_id`: ulangan Instagram akkaunt ID’si. Sahifani ulaganda o‘zi to‘ladi.

**Yangi doctype’lar:**
- **Instagram Suhbat:**
  - `shop`, `mijoz_id` (IGSID), `username`;
  - `holat`: AI / Menejerda;
  - `oxirgi_xabar` (vaqt), `murojaat` (havola);
  - `xabarlar`: ichki jadval **Instagram Xabar**.
- **Instagram Xabar:**
  - `kimdan`: Mijoz / AI / Menejer / Qoralama;
  - `turi`: DM / Izoh;
  - `matn`, `tashqi_id` (mid yoki comment id), `vaqt`.

Ko‘rish huquqi Murojaat bilan bir xil (`shop_query`):
- platforma admini hammasini ko‘radi;
- do‘kon egasi va sotuv menejerlari faqat o‘z do‘konini ko‘radi.

Suhbat formasida yozishma tarixi ko‘rinadi. Unda **«AI’ni to‘xtatish / qaytarish»** tugmasi bo‘ladi.

## Kod tuzilishi

- `sotuv/meta.py`:
  - `connect()` sahifa tokeni bilan birga `instagram_business_account` ID’sini ham saqlaydi;
  - `_subscribe_app()` `page` obunasiga qo‘shimcha ravishda `instagram` (messages) obunasini ham qiladi;
  - `webhook()` `object == "instagram"` bo‘lgan xabarlarni yangi modulga uzatadi.
- Yangi `sotuv/instagram.py`: xabar va izohlarni qabul qilish, poll, yuborish (Send API, private reply, izohga javob), echo’ni aniqlash, Suhbat yozish.
- Yangi `sotuv/ig_ai.py`: Gemini promptini tuzish (katalog, «AI uchun ma’lumot», tarix), javob JSON’ini tekshirish, lid yaratish. Graph API’ga tegmaydi, shuning uchun alohida test qilinadi.
- `hooks.py`: har daqiqada `instagram.poll` ishga tushadi. Ulangan va AI’si o‘chiq bo‘lmagan do‘konlar tekshiriladi. Meta limit xatosi (kod 4/17/32/613) kelsa, 15 daqiqa pauza qilinadi.
- AI javobi fon ishida (`frappe.enqueue`) tuziladi. Webhook Meta’ga darhol 200 qaytaradi.

## Xatolar

- Gemini xatosi yoki kvota tugashi: mijozga hech narsa yuborilmaydi va suhbat «Menejerda» holatiga o‘tadi. Shu xatoni Error Log va do‘kon **«Oxirgi holat»** maydoni ko‘rsatadi.
- 24 soatlik oyna tugagan bo‘lsa, Meta yuborishni rad etadi: suhbatga belgi qo‘yiladi va qayta urinilmaydi.
- Bitta suhbatda AI bir soatda 20 tadan ortiq javob bermaydi (sikl yoki spamdan himoya).

## Test

- Unit testlar quyidagilar uchun yoziladi:
  - webhook tahlili: DM, echo, izoh, dublikat;
  - AI JSON’ini tekshirish va telefon ajratib olish;
  - menejerga o‘tish qoidalari;
  - lid dublikati.
- Graph va Gemini mock qilinadi.
- Lokalda Meta’ning namuna payloadlari bilan sinab ko‘riladi.
- Prod’da Pandoo’da avval 1–2 kun «Sinov» rejimi, keyin «Yoqilgan».

## Foydalanuvchi qiladigan ishlar (koddan tashqari)

1. Kamoliddin aka Ismoilni Pandoo sahifasiga «Полный контроль» bilan qo‘shadi. Pandoo Instagram shu sahifaga ulangan bo‘lishi kerak.
2. Pandoo’ni Graph API Explorer tokeni bilan ulash. Token 9 ta ruxsat bilan olinadi.
3. Ilovaga ikonka qo‘yib, uni Live’ga o‘tkazish (DM’lar shu zahoti kelishi uchun).
4. Ixtiyoriy, keyinroq: izohlar uchun App Review va biznes tasdiqlash. Poll ishlab turgani uchun shoshilinch emas.
