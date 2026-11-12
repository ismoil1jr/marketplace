# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from marketplace.sotuv.telefoniya import normalize_phone, pretty_phone


class Murojaat(Document):
	"""Reklamadan (Instagram lead-forma) kelgan mijoz murojaati: ism, telefon, izoh va qaysi tovar (kitob) bo'yicha.
	Sotuv menejeri Sotuv panelidagi "Murojaatlar" bo'limida qo'ng'iroq qiladi va natija yozadi (sotuv/murojaat.py)."""

	def validate(self):
		# Raqam normal shaklda (998XXXXXXXXX) ham saqlanadi — majburiy tovar tarixi, murojaatdan buyurtma yaratish va
		# saytdagi buyurtmani murojaatga ulash shu maydon bo'yicha. Avval faqat API (save_lead) to'ldirar edi: Desk
		# formasida qo'lda yaratilgan murojaatda bo'sh qolib, menejer buyurtma bera olmas edi
		self.normal_telefon = lead_phone(self.telefon)
		if self.telefon and not self.normal_telefon:
			frappe.throw(_("Telefon raqami noto'g'ri: {0}. Masalan: +998 90 123 45 67").format(self.telefon), title=_("Telefon"))
		if self.normal_telefon:
			self.telefon = pretty_phone(self.telefon)
		if not self.mijoz_ismi:
			self.mijoz_ismi = " ".join(x for x in (self.ism, self.familiya) if x).strip() or self.telefon
		if self.tovar and not self.tovar_nomi:
			self.tovar_nomi = frappe.db.get_value("Item", self.tovar, "item_name")

	def on_trash(self):
		"""Murojaat o'chirilsa (masalan, test lidlar): uning menejer xulosalari ham o'chadi, qo'ng'iroqlardan esa faqat
		bog'lanish olinadi — yozuvlar qoladi (kerak bo'lmasa Qo'ng'iroqlar ro'yxatidan alohida o'chiriladi).
		Frappe bog'lanishni on_trash'dan keyin tekshiradi, shuning uchun ro'yxatdan ko'plab o'chirish ham ishlaydi."""
		for name in frappe.get_all("Menejer Xulosasi", filters={"murojaat": self.name}, pluck="name"):
			frappe.delete_doc("Menejer Xulosasi", name, ignore_permissions=True, force=True)
		frappe.db.set_value("Telefon Qongiroq", {"murojaat": self.name}, "murojaat", None, update_modified=False)


def lead_phone(raw):
	"""'+998 90 123-45-67' / '901234567' -> '998901234567'; 9 raqamdan kam bo'lsa — None (API bilan bir xil qoida)."""
	digits = normalize_phone(raw)
	return digits if digits and len(digits) >= 9 else None
