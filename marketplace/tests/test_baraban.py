from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace import baraban


class TestBaraban(UnitTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_variants_parse(self):
		self.assertEqual(baraban.variants("1, 2,x,0,2,5"), [1, 2, 5])
		self.assertEqual(baraban.variants(None), [])

	def _doc(self, **kw):
		d = dict(
			name="Test Shop", baraban_yoqilgan=1, baraban_tovar="ITEM-1",
			baraban_narx=10000, baraban_variantlar="1, 2,3", baraban_yutuq=3,
		)
		d.update(kw)
		return frappe._dict(d)

	def test_validate_shop(self):
		with patch("frappe.db.get_value", return_value="Test Shop"):
			for bad in (
				{"baraban_tovar": ""},
				{"baraban_narx": 0},
				{"baraban_variantlar": "x,0"},
				{"baraban_yutuq": 9},
			):
				with self.assertRaises(frappe.ValidationError):
					baraban.validate_shop(self._doc(**bad))
			doc = self._doc()
			baraban.validate_shop(doc)
			self.assertEqual(doc.baraban_variantlar, "1,2,3")
			# boshqa do'kon tovari
		with patch("frappe.db.get_value", return_value="Other"):
			with self.assertRaises(frappe.ValidationError):
				baraban.validate_shop(self._doc())
		# o'chiq bo'lsa tekshirilmaydi
		baraban.validate_shop(self._doc(baraban_yoqilgan=0, baraban_narx=0))

	def test_doctype_exists(self):
		self.assertTrue(frappe.get_meta("Baraban Chegirma").has_field("qolgan_soniya"))
		self.assertTrue(frappe.get_meta("Shop").has_field("baraban_yutuq"))
