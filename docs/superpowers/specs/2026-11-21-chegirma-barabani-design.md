# Chegirma barabani — dizayn

Sana: 2026-11-21 · Holat: tasdiqlangan (Ismoil, SMM Ruslan so'rovi)

## Maqsad

Narx tushirilgach savdo bo'lmayapti. Saytga kirgan har bir mijozga «chegirma barabani» ko'rsatiladi. Baraban mijozga vaqtli chegirma beradi va kitobni savatga qo'yadi. Shu tariqa mijoz shoshilib, sotib olishga undaladi.

## Mijoz tomoni (do'kon sayti `/s/<do'kon>/...`)

**1. Baraban.** Baraban yoqilgan do'konga birinchi marta kirganda butun ekranni egallagan baraban chiqadi.
- Uni yopib bo'lmaydi: yopish tugmasi yo'q, Esc ham ishlamaydi.
- Bo'limlar admin yozgan soatlar bilan: «1 soat», «2 soat», ….
- O'rtadagi «Aylantirish» tugmasi bosilgach, baraban 4–5 soniya aylanadi va har doim admin tanlagan variantda (masalan, 3 soat) to'xtaydi.
- «Tasodifiy» so'zi hech qayerda yozilmaydi.

**2. Natija.** Mijozga shunday xabar chiqadi: «🎉 Tabriklaymiz! Sizga 3 soatlik chegirma: «Panda books» 360 000 so'm (500 000 o'rniga)». Ostida «Savatga o'tish» tugmasi bo'ladi. Tovar savatga o'zi qo'shiladi; agar u savatda allaqachon bo'lsa, qayta qo'shilmaydi.

**3. Taymer.** Har bir do'kon sahifasining (katalog, tovar, savat) tepasida «⏳ Chegirma tugashiga: 02:59:41» yozuvi turadi.
- U soniyama-soniya kamayadi, lekin faqat sahifa ochiq va ko'rinib turganda.
- Mijoz brauzerdan chiqsa yoki ilovani almashtirsa, taymer to'xtaydi; qaytib kirganda o'sha joydan davom etadi.

**4. Narx.** Chegirma davomida savatda va buyurtmada shu tovar (variantlari bilan) chegirma narxida turadi. Katalog va tovar sahifasidagi narx ham shunday ko'rinadi.
- Vaqt tugagach, o'sha mijoz uchun oddiy narx (Item Price, 500 000) qaytadi.
- Tepada «Chegirma muddati tugadi» yozuvi chiqadi.

**5. Qayta kirish.** Baraban qayta chiqmaydi: brauzer cookie orqali eslab qoladi. Telegram tasdiqlash hozirgidek faqat buyurtmada bo'ladi.
- Ma'lum cheklov: brauzer xotirasini tozalagan yoki boshqa brauzerdan kirgan odam barabanni qayta aylantira oladi. Bu qabul qilingan.

## Admin tomoni (Shop formasi → «Chegirma barabani» bo'limi)

| Maydon | Tur | Izoh |
|---|---|---|
| `baraban_yoqilgan` | Check | Yoqilgan / o'chiq |
| `baraban_tovar` | Link Item | Beriladigan tovar. Shu do'konniki bo'lishi shart |
| `baraban_narx` | Currency | Chegirma narxi (masalan, 360 000) |
| `baraban_variantlar` | Data | Barabandagi soatlar, vergul bilan. Standart qiymati «1,2,3,4,5» |
| `baraban_yutuq` | Int | Har doim tushadigan variant (soat). Variantlar ichida bo'lishi shart |

Saqlashda tekshiriladi:
- tovar shu do'konniki;
- narx 0 dan katta;
- variantlar musbat butun sonlar;
- yutuq variantlar ichida.

## Server

**Doctype «Baraban Chegirma»** (modul Marketplace). Har bir brauzer uchun bitta yozuv. Maydonlari:
- `shop`
- `token` — unikal; brauzerda `mp_baraban` cookie'da saqlanadi (HttpOnly, SameSite=Lax, 30 kun)
- `soat`
- `qolgan_soniya`
- `oxirgi_signal` — Datetime

**`marketplace/baraban.py`** — mehmonlar uchun ochiq API, cheklov bilan (rate limit):
- `state(shop)` — baraban sozlamasi va shu brauzer holati: aylantirilganmi, qolgan soniya, narxlar, tovar.
- `spin(shop)` — token bo'lmasa yozuv yaratadi: `qolgan_soniya = yutuq × 3600`. Token bo'lsa, borini qaytaradi (qayta aylantirish yo'q).
- `tick(shop)` — sahifa ko'rinib turganda brauzer uni har ~15 soniyada chaqiradi. Server `min(hozir − oxirgi_signal, 20 s)` ni ayiradi. Mijoz yo'q paytdagi vaqt hisoblanmaydi, shuning uchun taymer to'xtaydi.
- `active(shop_doc)` — cookie'dagi tokenning chegirmasi hali faol bo'lsa `(tovar, narx)` qaytaradi, aks holda `None`.

**Narx.** `storefront.get_cart_lines` (savat va `place_order` shu funksiyani ishlatadi) chegirma faol bo'lsa shu tovar va uning variantlari uchun `price = baraban_narx` qiladi. Brauzerdagi narxga ishonilmaydi.

## Hisobot va xatolar

- Baraban o'chiq bo'lsa yoki sozlama noto'g'ri bo'lsa, sayt odatdagidek ishlaydi.
- API xato bersa ham sayt ishlayveradi: baraban va taymer chiqmaydi.

## Test

Unit testlar:
- spin bir martalik;
- tick 20 soniyadan ortiq ayirmaydi;
- muddati tugagan chegirma narx bermaydi;
- `get_cart_lines` chegirma narxini faqat faol tokenda va faqat shu tovarga qo'yadi;
- Shop tekshiruvi.

JS qo'lda sinaladi (lokal sayt).
