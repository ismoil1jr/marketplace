from datetime import timedelta
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import now_datetime

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


class TestBarabanApi(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")
		frappe.local.request_ip = "127.0.0.1"
		self.cookies = {}
		self.cm = MagicMock()
		self.cfg = frappe._dict(
			tovar="ITEM-1", narx=10000, variantlar=[1, 2, 3], yutuq=3,
			tovar_nomi="T", eski_narx=20000, rasm=None,
		)
		self.patches = [
			patch("frappe.request", MagicMock(cookies=self.cookies)),
			patch("frappe.local.cookie_manager", self.cm, create=True),
			patch("marketplace.baraban.config", return_value=self.cfg),
			patch("marketplace.storefront.get_shop", return_value=frappe._dict(name=self.shop)),
		]
		for p in self.patches:
			p.start()

	def tearDown(self):
		for p in self.patches:
			p.stop()
		frappe.db.rollback()

	def _row(self, secs_ago=0, remaining=3 * 3600, token="tok" * 8):
		frappe.get_doc({
			"doctype": "Baraban Chegirma", "shop": self.shop, "token": token, "soat": 3,
			"qolgan_soniya": remaining, "oxirgi_signal": now_datetime() - timedelta(seconds=secs_ago),
		}).insert(ignore_permissions=True)
		self.cookies[baraban._cookie_name(self.shop)] = token
		return token

	def test_state_disabled_on_bad_config(self):
		self.patches[2].stop()
		with patch("frappe.db.get_value", return_value=frappe._dict(
			baraban_yoqilgan=1, baraban_tovar="X", baraban_narx=5,
			baraban_variantlar="1,2", baraban_yutuq=9,
		)):
			self.assertIsNone(baraban.config(self.shop))
		self.patches[2].start()
		with patch("marketplace.baraban.config", return_value=None):
			self.assertEqual(baraban.state(self.shop), {"enabled": False})

	def test_spin_creates_row_and_cookie(self):
		res = baraban.spin(self.shop)
		self.assertTrue(res["spun"])
		args, kw = self.cm.set_cookie.call_args
		self.assertTrue(kw["httponly"])
		self.assertEqual(args[0], baraban._cookie_name(self.shop))
		self.assertEqual(frappe.db.get_value("Baraban Chegirma", {"token": args[1]}, "qolgan_soniya"), 3 * 3600)

	def test_spin_is_once_per_browser(self):
		self.test_spin_creates_row_and_cookie()
		token = self.cm.set_cookie.call_args[0][1]
		self.cookies[baraban._cookie_name(self.shop)] = token
		self.cm.reset_mock()
		res = baraban.spin(self.shop)
		self.cm.set_cookie.assert_not_called()
		self.assertEqual(res["remaining"], 3 * 3600)
		self.assertEqual(frappe.db.count("Baraban Chegirma", {"token": token}), 1)

	def test_tick_caps_gap(self):
		self._row(secs_ago=7200)
		res = baraban.tick(self.shop)
		self.assertGreaterEqual(res["remaining"], 3 * 3600 - baraban.MAX_STEP)

	def test_tick_normal(self):
		self._row(secs_ago=10)
		res = baraban.tick(self.shop)
		self.assertAlmostEqual(3 * 3600 - res["remaining"], 10, delta=2)

	def test_tick_no_row(self):
		self.assertEqual(baraban.tick(self.shop), {"remaining": 0})

	def test_active(self):
		self.assertIsNone(baraban.active(self.shop))
		self._row(remaining=100)
		self.assertEqual(baraban.active(self.shop), ("ITEM-1", 10000))

	def test_active_none_when_expired(self):
		self._row(remaining=0)
		self.assertIsNone(baraban.active(self.shop))

	def test_active_never_raises(self):
		with patch("marketplace.baraban.config", side_effect=RuntimeError("x")):
			self.assertIsNone(baraban.active(self.shop))
