# Do'kon bilan hamkorlik shartnomasi. Saqlanganda to'liq PDF yaratiladi (Print Format «Hamkorlik shartnomasi»)
# va yopiq fayl sifatida biriktiriladi. Pasport ma'lumotlari bor — doctype faqat admin rollariga ochiq.

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, date_diff, flt, getdate

from marketplace.otp import normalize_phone

PRINT_FORMAT = "Hamkorlik shartnomasi"
TEMPLATE = "marketplace/marketplace/print_format/hamkorlik_shartnomasi/shartnoma.html"
# Shu maydonlardan biri o'zgarsa PDF qayta yaratiladi (holat, skan, izoh o'zgarsa — yo'q)
PDF_FIELDS = (
	"dokon_nomi", "telefon", "sana", "familiya", "ism", "otasining_ismi", "pasport", "tugilgan_sana",
	"huquqiy_shakl", "tashkilot_nomi", "stir", "manzil", "obuna_narxi", "komissiya_foizi",
)
PASSPORT_RE = re.compile(r"^[A-Z]{2}\d{7}$")


class Hamkorlik(Document):
	def before_insert(self):
		# Narx — Marketplace sozlamalaridan (50 000 so'm / 2%), admin formada o'zgartirishi mumkin
		if not self.obuna_narxi and not self.komissiya_foizi:
			s = company_settings()
			self.obuna_narxi = s.obuna
			self.komissiya_foizi = s.komissiya

	def validate(self):
		for field in ("dokon_nomi", "familiya", "ism", "otasining_ismi", "tashkilot_nomi", "stir"):
			if self.get(field):
				self.set(field, re.sub(r"\s+", " ", self.get(field)).strip())
		for field in ("familiya", "ism", "otasining_ismi"):  # «alisher» -> «Alisher» (qolgan harflar o'zgarmaydi)
			if self.get(field):
				self.set(field, " ".join(w[:1].upper() + w[1:] for w in self.get(field).split()))
		if self.tashkilot_nomi:  # «...» va MChJ/YaTT so'zini shablon o'zi qo'shadi
			self.tashkilot_nomi = re.sub(r"^(MChJ|YaTT|ООО|OOO)\s+|\s+(MChJ|YaTT|ООО|OOO)$", "", self.tashkilot_nomi, flags=re.I)
			self.tashkilot_nomi = self.tashkilot_nomi.strip(" «»\"'“”„")
		self.telefon = normalize_phone(self.telefon)
		self.pasport = re.sub(r"[\s-]", "", self.pasport or "").upper()
		if not PASSPORT_RE.match(self.pasport):
			frappe.throw(_("Pasport seriya va raqami noto‘g‘ri. Masalan: AA1234567"), title=_("Pasport"))
		if self.tugilgan_sana and date_diff(self.sana, self.tugilgan_sana) < 18 * 365:
			frappe.throw(_("Do‘kon egasi shartnoma sanasida 18 yoshdan katta bo‘lishi kerak"), title=_("Tug‘ilgan sana"))
		self.huquqiy_shakl = self.huquqiy_shakl or "Jismoniy shaxs"
		if self.huquqiy_shakl == "Jismoniy shaxs":
			self.tashkilot_nomi = self.stir = self.manzil = None
		else:
			self.stir = re.sub(r"\D", "", self.stir or "")
			if len(self.stir) not in (9, 14):
				frappe.throw(_("STIR 9 xonali bo‘lishi kerak (YaTT uchun JShShIR — 14 xonali)"), title=_("STIR"))
		self.egasi_qisqa = short_name(self.familiya, self.ism)
		self.bepul_gacha = add_days(add_months(self.sana, 1), -1)
		if self.imzolangan_nusxa and self.holat == "Yangi":
			self.holat = "Imzolangan"

	def on_update(self):
		if not self.pdf_fayl or any(self.has_value_changed(f) for f in PDF_FIELDS):
			attach_pdf(self)


def short_name(familiya, ism):
	"""«Karimov», «Alisher» -> «Karimov A.» — imzo joyi uchun."""
	familiya = (familiya or "").strip()
	ism = (ism or "").strip()
	return f"{familiya} {ism[0].upper()}." if familiya and ism else familiya


def company_settings():
	"""Platforma rekvizitlari va narxlari. Single'da default bazaga yozilmaydi — bo'sh bo'lsa maydon defaulti."""
	meta = frappe.get_meta("Marketplace Settings")
	values = frappe.db.get_singles_dict("Marketplace Settings")

	def get(field):
		value = values.get(field)
		if value in (None, "", "0", 0):  # sozlama saqlanmagan yoki 0 qolib ketgan — standart qiymat
			df = meta.get_field(field)
			value = df.default if df else None
		return value

	return frappe._dict(
		nomi=get("hamkor_kompaniya") or "«ORANGE TEAM» MChJ",
		rahbar=get("hamkor_rahbar") or "Uchqunov A.",
		stir=get("hamkor_stir"),
		manzil=get("hamkor_manzil"),
		bank=get("hamkor_bank"),
		hisob=get("hamkor_hisob"),
		mfo=get("hamkor_mfo"),
		telefon=get("aloqa_telefon"),
		obuna=int(flt(get("hamkor_obuna"))),
		komissiya=flt(get("hamkor_komissiya")),
	)


MONTHS = ("yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr")


def hamkorlik_konteksti(doc):
	"""Print Format uchun tayyor matnlar (hooks.jinja orqali shablonda: {% set k = hamkorlik_konteksti(doc) %})."""
	d = getdate(doc.sana)
	nxt = add_days(doc.bepul_gacha, 1) if doc.bepul_gacha else None
	fmt = lambda v: getdate(v).strftime("%d.%m.%Y") if v else ""  # noqa: E731
	return frappe._dict(
		kompaniya=company_settings(),
		sana_matn=f"«{d.day:02d}» {MONTHS[d.month - 1]} {d.year} y.",
		sana=fmt(doc.sana),
		bepul_gacha=fmt(doc.bepul_gacha),
		pullik_dan=fmt(nxt),
		tugilgan=fmt(doc.tugilgan_sana),
		obuna=f"{int(flt(doc.obuna_narxi)):,}".replace(",", " "),
		komissiya=f"{flt(doc.komissiya_foizi):g}",
		egasi_fio=" ".join(x for x in (doc.familiya, doc.ism, doc.otasining_ismi) if x),
		yuridik=doc.huquqiy_shakl in ("YaTT", "MChJ"),
		tashkilot=org_title(doc.huquqiy_shakl, doc.tashkilot_nomi),
		telefon=phone_text(doc.telefon),
	)


def org_title(shakl, nomi):
	"""MChJ: «Sinov Kitoblari» MChJ; YaTT: YaTT Karimov Alisher (odam ismi qo'shtirnoqsiz)."""
	nomi = (nomi or "").strip()
	if shakl == "MChJ":
		return f"«{nomi}» MChJ"
	if shakl == "YaTT":
		return f"YaTT {nomi}"
	return nomi


def phone_text(phone):
	"""+998901234567 -> +998 90 123 45 67"""
	p = phone or ""
	return f"{p[:4]} {p[4:6]} {p[6:9]} {p[9:11]} {p[11:13]}" if re.fullmatch(r"\+998\d{9}", p) else p


def render_pdf(doc):
	"""Frappe'ning o'z PDF'i (Print Format, Chrome). Chrome serverda hali o'rnatilmagan bo'lsa — WeasyPrint.
	Chrome yo'q paytda Frappe uni so'rov ichida yuklab olishga urinadi (150 MB) — shuning uchun avval tekshiramiz."""
	if chrome_ready():
		try:
			return frappe.get_print(
				doc.doctype, doc.name, PRINT_FORMAT, doc=doc, as_pdf=True, no_letterhead=1, pdf_generator="chrome"
			)
		except Exception:
			frappe.log_error(title="Hamkorlik PDF (Chrome)")
	from weasyprint import HTML

	body = frappe.render_template(TEMPLATE, {"doc": doc})
	page = "@page { size: A4; margin: 12mm 12mm 12mm 15mm; }"  # Print Format chetlari bilan bir xil, 1 varaq
	html = f'<!doctype html><html lang="uz"><head><meta charset="utf-8"><style>{page}</style></head><body>{body}</body></html>'
	return HTML(string=html, base_url=frappe.utils.get_url()).write_pdf()


def chrome_ready():
	import os
	import platform
	import shutil

	from frappe.utils.print_utils import EXECUTABLE_PATHS

	if shutil.which(frappe.get_common_site_config().get("chromium_path") or ""):
		return True
	parts = EXECUTABLE_PATHS.get(platform.system().lower())
	return bool(parts) and os.path.exists(os.path.join(frappe.utils.get_bench_path(), "chromium", *parts))


def attach_pdf(doc):
	"""PDF'ni yopiq fayl qilib biriktiradi (eskisi o'chadi) va pdf_fayl maydoniga yozadi."""
	content = render_pdf(doc)
	old = frappe.get_all(
		"File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "attached_to_field": "pdf_fayl"},
		pluck="name",
	)
	for name in old:
		frappe.delete_doc("File", name, ignore_permissions=True, force=True)
	f = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{doc.name}-shartnoma.pdf",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"attached_to_field": "pdf_fayl",
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)
	doc.db_set("pdf_fayl", f.file_url, update_modified=False)
	return f.file_url


@frappe.whitelist()
def standart_narx():
	"""Yangi shartnoma formasi uchun sozlamalardagi narx (admin sozlamalarni o'qiy olmasligi mumkin)."""
	frappe.has_permission("Hamkorlik", "create", throw=True)
	s = company_settings()
	return {"obuna_narxi": s.obuna, "komissiya_foizi": s.komissiya}
