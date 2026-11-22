from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from marketplace.marketplace.doctype.hamkorlik import hamkorlik as hk


def make(**kw):
	data = {
		"doctype": "Hamkorlik", "dokon_nomi": "Sinov Kitoblari", "telefon": "90 123 45 67",
		"familiya": "Karimov", "ism": "alisher", "otasining_ismi": "Bahodirovich",
		"pasport": "aa 1234567", "tugilgan_sana": "1990-05-14", "sana": "2026-11-22",
	}
	data.update(kw)
	return frappe.get_doc(data)


class TestHamkorlikHelpers(UnitTestCase):
	def test_short_name(self):
		self.assertEqual(hk.short_name("Karimov", "alisher"), "Karimov A.")
		self.assertEqual(hk.short_name("Karimov", ""), "Karimov")

	def test_org_title(self):
		self.assertEqual(hk.org_title("MChJ", "Sinov Kitoblari"), "«Sinov Kitoblari» MChJ")
		self.assertEqual(hk.org_title("YaTT", "Karimov Alisher"), "YaTT Karimov Alisher")

	def test_phone_text(self):
		self.assertEqual(hk.phone_text("+998901234567"), "+998 90 123 45 67")
		self.assertEqual(hk.phone_text(""), "")


class TestHamkorlik(IntegrationTestCase):
	"""Saqlash: tekshiruvlar, narx sozlamadan, PDF yopiq fayl. PDF — WeasyPrint (testda Chrome chaqirilmaydi)."""

	def setUp(self):
		frappe.set_user("Administrator")
		p = patch.object(hk, "chrome_ready", return_value=False)
		p.start()
		self.addCleanup(p.stop)

	def test_insert_normalizes_and_makes_pdf(self):
		d = make(huquqiy_shakl="MChJ", tashkilot_nomi="«Sinov Kitoblari» MChJ", stir="305 123 456").insert()
		self.assertTrue(d.name.startswith("HMK-2026-"))
		self.assertEqual(d.telefon, "+998901234567")
		self.assertEqual(d.pasport, "AA1234567")
		self.assertEqual(d.stir, "305123456")
		self.assertEqual(d.tashkilot_nomi, "Sinov Kitoblari")
		self.assertEqual(d.egasi_qisqa, "Karimov A.")
		self.assertEqual(str(d.bepul_gacha), "2026-12-21")
		self.assertEqual((d.obuna_narxi, d.komissiya_foizi), (50000, 2))
		d.reload()
		self.assertTrue(d.pdf_fayl.startswith("/private/files/"))
		f = frappe.get_doc("File", {"attached_to_name": d.name, "attached_to_field": "pdf_fayl"})
		self.assertTrue(f.is_private)
		self.assertTrue(f.get_content().startswith(b"%PDF"))

	def test_pdf_text_has_terms_and_signatures(self):
		d = make()
		d.name = "HMK-TEST-1"
		d.validate()
		d.obuna_narxi, d.komissiya_foizi = 50000, 2
		html = frappe.render_template(hk.TEMPLATE, {"doc": d})
		for text in ("HMK-TEST-1", "Karimov Alisher Bahodirovich", "AA1234567", "14.05.1990", "+998 90 123 45 67",
			"«Sinov Kitoblari»", "50 000 so‘m", "2%", "22.11.2026", "21.12.2026", "22.12.2026",
			"Uchqunov A.", "Karimov A.", "(imzo)"):
			self.assertIn(text, html)

	def test_fits_one_page_with_everything_filled(self):
		"""Eng uzun holat: MChJ, uzun manzil, platformaning barcha rekvizitlari — baribir bitta A4 varaq."""
		import io

		from pypdf import PdfReader

		full = hk.company_settings()
		full.update(stir="305123456", manzil="Toshkent sh., Yunusobod t., Amir Temur ko‘chasi, 108-uy, 4-ofis",
			bank="«Kapitalbank» ATB Toshkent sh. filiali", hisob="20208000900123456001", mfo="01088")
		d = make(huquqiy_shakl="MChJ", tashkilot_nomi="Bolalar Rivojlantiruvchi Kitoblari Savdo Uyi", stir="305123456",
			manzil="Toshkent viloyati, Qibray tumani, Bobur MFY, Navro‘z ko‘chasi, 15-uy")
		d.name = "HMK-2026-9999"
		d.validate()
		d.obuna_narxi, d.komissiya_foizi = 50000, 2
		with patch.object(hk, "company_settings", return_value=full):
			pdf = hk.render_pdf(d)
			html = frappe.render_template(hk.TEMPLATE, {"doc": d})
		self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages), 1)
		# har bir rekvizit — o'z qatorida (Bank bilan MFO, pasport bilan tug'ilgan sana bir qatorga tiqilmaydi)
		for label in ("STIR:", "Manzil:", "Bank:", "MFO:", "H/r:", "Pasport:", "Tug‘ilgan sana:", "Tashkilot:"):
			self.assertIn(f"<tr><th>{label}</th>", html)

	def test_validation_errors(self):
		with self.assertRaises(frappe.ValidationError):
			make(pasport="12345").insert()
		with self.assertRaises(frappe.ValidationError):
			make(telefon="123").insert()
		with self.assertRaises(frappe.ValidationError):
			make(tugilgan_sana="2015-01-01").insert()
		with self.assertRaises(frappe.ValidationError):
			make(huquqiy_shakl="MChJ", tashkilot_nomi="X", stir="12").insert()

	def test_person_clears_org_fields_and_scan_marks_signed(self):
		d = make(huquqiy_shakl="Jismoniy shaxs", tashkilot_nomi="X", stir="305123456").insert()
		self.assertIsNone(d.tashkilot_nomi)
		pdf = d.pdf_fayl
		with patch.object(hk, "attach_pdf") as again:
			d.imzolangan_nusxa = "/private/files/skan.pdf"
			d.save()
		self.assertEqual(d.holat, "Imzolangan")
		again.assert_not_called()  # faqat skan qo'shildi — PDF qayta yasalmaydi
		self.assertEqual(d.pdf_fayl, pdf)

	def test_refresh_pdfs_updates_only_unsigned(self):
		"""Rekvizit sozlamaga keyin kiritilsa — imzolanmagan shartnoma PDF'i yangi rekvizit bilan qayta yasaladi."""
		import io

		from pypdf import PdfReader

		yangi = make().insert()
		imzolangan = make(dokon_nomi="Imzoli Do‘kon", imzolangan_nusxa="/private/files/skan.pdf").insert()
		self.assertEqual(imzolangan.holat, "Imzolangan")

		full = hk.company_settings()
		full.update(stir="309584422", mfo="01145")

		def pdf_text(doc):
			f = frappe.get_doc("File", {"attached_to_name": doc.name, "attached_to_field": "pdf_fayl"})
			return "".join(p.extract_text() for p in PdfReader(io.BytesIO(f.get_content())).pages)

		self.assertNotIn("309584422", pdf_text(yangi))
		with patch.object(hk, "company_settings", return_value=full):
			hk.refresh_pdfs()
		self.assertIn("309584422", pdf_text(yangi))
		self.assertNotIn("309584422", pdf_text(imzolangan))

	def test_settings_save_queues_refresh_only_for_requisites(self):
		p = patch("marketplace.telegram_bot.on_settings_update")  # Telegram getMe'ga chiqmasin
		p.start()
		self.addCleanup(p.stop)
		s = frappe.get_single("Marketplace Settings")
		with patch("frappe.enqueue") as enqueue:
			s.hamkor_stir = "309584422"
			s.save()
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.args[0], "marketplace.marketplace.doctype.hamkorlik.hamkorlik.refresh_pdfs")
		with patch("frappe.enqueue") as enqueue:
			s.hamkor_obuna = 70000  # narx faqat yangi shartnomaga ta'sir qiladi — eski PDF'lar o'zgarmaydi
			s.save()
		enqueue.assert_not_called()

	def test_manual_refresh_button(self):
		d = make().insert()
		with patch.object(hk, "attach_pdf", return_value="/private/files/x.pdf") as attach:
			self.assertEqual(hk.pdf_yangilash(d.name), "/private/files/x.pdf")
		attach.assert_called_once()

	def test_only_admin_roles_can_read(self):
		perms = {p.role for p in frappe.get_meta("Hamkorlik").permissions if p.read}
		self.assertEqual(perms, {"System Manager", "Marketplace Manager"})
