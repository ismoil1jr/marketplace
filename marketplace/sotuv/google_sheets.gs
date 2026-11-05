/**
 * magazinlar.uz — Instagram formasi murojaatlari: Google Sheets → Sotuv paneli («Murojaatlar»).
 * Do'kon: __DOKON__
 *
 * O'rnatish (bir marta):
 *   1. Shu jadvalda: Kengaytmalar (Extensions / Расширения) → Apps Script.
 *   2. Ochilgan oynadagi hamma narsani o'chirib, shu kodni qo'ying → Saqlash (💾).
 *   3. Yuqoridagi ro'yxatdan «sozlash» funksiyasini tanlang → Run (Выполнить) → Google ruxsat so'raydi → ruxsat bering.
 *   4. Tayyor: har daqiqada yangi qatorlar yuboriladi. Natija — jadvaldagi «magazinlar.uz» varag'ida.
 *
 * Qaysi tovar: qatordagi «tovar_id» ustuni; bo'lmasa — varaq nomi yoki forma nomi boshidagi Tovar ID
 * («1», «1 Audio kitob») yoki tovar nomi. Tovar ID'lar — magazinlar.uz'da do'kon formasi → «Google Sheets».
 */
const MANZIL = __MANZIL__;
const KALIT = __KALIT__; // do'kon kaliti: jadvalni faqat ishonchli odamlar bilan bo'lishing
const JURNAL = "magazinlar.uz"; // yuborilgan qatorlar shu varaqqa yoziladi (o'chirmang)
const ESKI_KUN = 3; // shundan eski murojaatlar yuborilmaydi (Meta eski lidlarni ham qo'shganda)
const TELEFON = /phone|telefon|raqam|номер|телефон/;

function sozlash() {
  for (const t of ScriptApp.getProjectTriggers()) ScriptApp.deleteTrigger(t);
  ScriptApp.newTrigger("yuborish").timeBased().everyMinutes(1).create();
  const n = yuborish();
  SpreadsheetApp.getActive().toast("Ulandi. Hozir yuborildi: " + n + ". Keyingilari — har daqiqada.", "magazinlar.uz", 15);
}

function yuborish() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) return 0; // oldingi yuborish hali tugamagan
  try {
    const ss = SpreadsheetApp.getActive();
    const jurnal = ss.getSheetByName(JURNAL) || yangiJurnal(ss);
    const last = jurnal.getLastRow();
    const sent = new Set(last > 1 ? jurnal.getRange(2, 5, last - 1, 1).getValues().map((r) => String(r[0])) : []);
    const chegara = Date.now() - ESKI_KUN * 864e5;
    let count = 0;
    for (const sh of ss.getSheets()) {
      if (sh.getName() === JURNAL || sh.getLastRow() < 2) continue;
      const rows = sh.getDataRange().getValues();
      const head = rows[0].map((h) => String(h).trim().toLowerCase().replace(/\s+/g, "_"));
      if (!head.some((h) => TELEFON.test(h))) continue; // telefon ustuni yo'q varaq — murojaat emas
      for (let r = 1; r < rows.length; r++) {
        const row = {};
        head.forEach((h, i) => {
          const v = rows[r][i];
          if (h && v !== "" && v !== null) row[h] = v instanceof Date ? v.toISOString() : String(v).trim();
        });
        if (!Object.keys(row).some((h) => TELEFON.test(h))) continue; // telefoni hali yozilmagan qator
        const id = sh.getSheetId() + ":" + (row.id || row.lead_id || hash(row));
        if (sent.has(id)) continue;
        const vaqt = sana(row.created_time);
        if (vaqt && vaqt < chegara) {
          yoz(jurnal, sh, r, "eski — yuborilmadi", id);
          sent.add(id);
          continue;
        }
        row.varaq = sh.getName();
        const res = UrlFetchApp.fetch(MANZIL, {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify(row),
          headers: { "X-Murojaat-Kalit": KALIT },
          muteHttpExceptions: true,
        });
        const code = res.getResponseCode();
        if (code === 403) throw new Error("Kalit noto'g'ri — magazinlar.uz'dan yangi kodni olib qo'ying");
        if (code === 429 || code >= 500) return count; // sayt band — keyingi daqiqada qayta urinadi
        if (code !== 200 && code !== 417) throw new Error("magazinlar.uz javobi: HTTP " + code);
        let note;
        if (code === 200) {
          const m = JSON.parse(res.getContentText()).message || {};
          note = (m.duplicate ? "oldin yozilgan: " : "yuborildi: ") + m.name + " — " + (m.tovar_nomi || "tovar aniqlanmadi");
          count++;
        } else {
          note = "o'tkazildi: " + xato(res); // sinov lid yoki telefon noto'g'ri
        }
        yoz(jurnal, sh, r, note, id);
        sent.add(id);
      }
    }
    return count;
  } finally {
    lock.releaseLock();
  }
}

function yangiJurnal(ss) {
  const sh = ss.insertSheet(JURNAL, ss.getSheets().length);
  sh.appendRow(["Vaqt", "Varaq", "Qator", "Natija", "Kalit"]);
  sh.setFrozenRows(1);
  sh.setColumnWidth(4, 420);
  return sh;
}

function yoz(jurnal, sh, r, note, id) {
  jurnal.appendRow([new Date(), sh.getName(), r + 1, note, id]);
}

function hash(row) {
  return Utilities.base64Encode(Utilities.computeDigest(Utilities.DigestAlgorithm.MD5, JSON.stringify(row)));
}

// Meta: "2026-11-05T12:16:00+0500" — Date.parse "+05:00" ko'rinishini kutadi
function sana(v) {
  if (!v) return null;
  const t = Date.parse(String(v).replace(/([+-]\d\d)(\d\d)$/, "$1:$2"));
  return isNaN(t) ? null : t;
}

function xato(res) {
  try {
    const msgs = JSON.parse(JSON.parse(res.getContentText())._server_messages);
    return JSON.parse(msgs[0]).message;
  } catch (e) {
    return "HTTP " + res.getResponseCode();
  }
}
