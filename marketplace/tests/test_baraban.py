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
			patch("marketplace.baraban._base_config", return_value=self.cfg),
			patch("marketplace.storefront.get_shop", return_value=frappe._dict(name=self.shop)),
		]
		for p in self.patches:
			p.start()
		self._reset_limiter()

	def _reset_limiter(self):
		# @rate_limit hisoblagichi redis'da (IP bo'yicha, 1 soat) — testlar takror ishlaganda to'lib qolmasin
		frappe.cache.delete_keys("rl:")

	def tearDown(self):
		for p in self.patches:
			p.stop()
		self._reset_limiter()
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
		self.patches[3].stop()
		with patch("frappe.db.get_value", return_value=frappe._dict(
			baraban_yoqilgan=1, baraban_tovar="X", baraban_narx=5,
			baraban_variantlar="1,2", baraban_yutuq=9,
		)):
			self.assertIsNone(baraban.config(self.shop))
		self.patches[2].start()
		self.patches[3].start()
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
		with patch("marketplace.baraban._base_config", side_effect=RuntimeError("x")):
			self.assertIsNone(baraban.active(self.shop))

	def test_active_no_cookie_no_config_call(self):
		with patch("marketplace.baraban._base_config") as bc, patch("marketplace.baraban.config") as c:
			self.assertIsNone(baraban.active(self.shop))
			bc.assert_not_called()
			c.assert_not_called()

	def _full_config(self, old):
		self.patches[2].stop()
		self.patches[3].stop()
		try:
			with patch("marketplace.baraban._base_config", return_value=frappe._dict(
				tovar="I", narx=100, variantlar=[1], yutuq=1, tovar_nomi="n", rasm=None)), \
				patch("marketplace.storefront._get_prices", return_value={"I": old}):
				return baraban.config(self.shop)
		finally:
			self.patches[2].start()
			self.patches[3].start()

	def test_config_never_throws(self):
		self.patches[2].stop()
		self.patches[3].stop()
		try:
			with patch("marketplace.baraban._base_config", return_value=frappe._dict(
				tovar="I", narx=100, variantlar=[1], yutuq=1, tovar_nomi="n", rasm=None)), \
				patch("marketplace.storefront._get_prices", side_effect=RuntimeError("x")):
				self.assertIsNone(baraban.config(self.shop))
		finally:
			self.patches[2].start()
			self.patches[3].start()

	def test_eski_narx(self):
		self.assertEqual(self._full_config(150).eski_narx, 150)
		self.assertIsNone(self._full_config(100).eski_narx)
		self.assertIsNone(self._full_config(50).eski_narx)

	def test_cleanup(self):
		old = now_datetime() - timedelta(days=10)
		self._row(remaining=0, token="a" * 24)
		self._row(remaining=500, token="b" * 24)
		self._row(remaining=500, token="c" * 24)
		frappe.db.set_value("Baraban Chegirma", {"token": "a" * 24}, "modified", old, update_modified=False)
		frappe.db.set_value("Baraban Chegirma", {"token": "c" * 24}, "creation",
			now_datetime() - timedelta(days=61), update_modified=False)
		baraban.cleanup()
		self.assertFalse(frappe.db.exists("Baraban Chegirma", {"token": "a" * 24}))
		self.assertFalse(frappe.db.exists("Baraban Chegirma", {"token": "c" * 24}))
		self.assertTrue(frappe.db.exists("Baraban Chegirma", {"token": "b" * 24}))


class TestBarabanCart(UnitTestCase):
	"""get_cart_lines: chegirma narxi faqat faol taymerda (DB'siz, mock bilan)."""

	def _item(self, name, variant_of=None, old_price=0, ws=0):
		return frappe._dict(
			name=name, item_name=name, image=None, is_stock_item=0, wholesale_price=ws,
			wholesale_min_qty=2 if ws else 0, variant_of=variant_of, mp_tez_kunda=0, old_price=old_price,
		)

	def _lines(self, active, items, qty=1, tpl_old=0):
		from marketplace import storefront

		tpl = frappe._dict(
			name="TPL", item_name="TPL", image=None, wholesale_price=0, wholesale_min_qty=0,
			mp_tez_kunda=0, old_price=tpl_old,
		)
		rows = {"first": items}

		def get_all(doctype, **kw):
			return rows.pop("first", None) or [tpl]

		shop = frappe._dict(name="SHOP-A", warehouse="W")
		with patch("marketplace.baraban.active", return_value=active) as act, \
			patch("frappe.get_all", side_effect=get_all), \
			patch.object(storefront, "_get_prices", return_value={i.name: 500000 for i in items}), \
			patch.object(storefront, "_get_stock", return_value={}), \
			patch.object(storefront, "_get_thumbnails", return_value={}), \
			patch.object(storefront, "variant_labels", return_value={}), \
			patch.object(storefront, "_color_thumbs", return_value={}):
			out = storefront.get_cart_lines(shop, [{"code": i.name, "qty": qty} for i in items])
			self.assertEqual(act.call_count, 1)
			act.assert_called_with("SHOP-A")
		return {line["code"]: line for line in out}

	def test_cart_price_only_while_active(self):
		items = [self._item("V1", variant_of="TPL", old_price=0)]
		on = self._lines(("TPL", 360000), items, qty=2, tpl_old=600000)["V1"]
		self.assertEqual(on["price"], 360000)
		self.assertEqual(on["retail_price"], 500000)
		self.assertEqual(on["list_price"], 600000)
		self.assertFalse(on["is_wholesale"])
		self.assertEqual(on["amount"], 720000)
		self.assertTrue(on["baraban"])
		off = self._lines(None, [self._item("V1", variant_of="TPL")], qty=2)["V1"]
		self.assertEqual(off["price"], 500000)
		self.assertEqual(off["amount"], 1000000)
		self.assertFalse(off.get("baraban"))

	def test_cart_price_applies_to_variants_only(self):
		items = [self._item("V1", variant_of="TPL"), self._item("OTHER", variant_of="TPL2")]
		out = self._lines(("TPL", 360000), items)
		self.assertEqual(out["V1"]["price"], 360000)
		self.assertEqual(out["OTHER"]["price"], 500000)
		self.assertFalse(out["OTHER"].get("baraban"))

	def test_wheel_price_beats_wholesale(self):
		items = [self._item("SINGLE", ws=300000)]
		out = self._lines(("SINGLE", 360000), items, qty=5)["SINGLE"]
		self.assertEqual(out["price"], 360000)
		self.assertFalse(out["is_wholesale"])

	def test_promo_false_skips_baraban(self):
		items = [self._item("V1", variant_of="TPL")]
		from marketplace import storefront

		tpl = frappe._dict(name="TPL", item_name="TPL", image=None, wholesale_price=0, wholesale_min_qty=0,
			mp_tez_kunda=0, old_price=0)
		rows = {"first": items}
		shop = frappe._dict(name="SHOP-A", warehouse="W")
		with patch("marketplace.baraban.active", return_value=("TPL", 360000)) as act, \
			patch("frappe.get_all", side_effect=lambda *a, **k: rows.pop("first", None) or [tpl]), \
			patch.object(storefront, "_get_prices", return_value={"V1": 500000}), \
			patch.object(storefront, "_get_stock", return_value={}), \
			patch.object(storefront, "_get_thumbnails", return_value={}), \
			patch.object(storefront, "variant_labels", return_value={}), \
			patch.object(storefront, "_color_thumbs", return_value={}):
			out = storefront.get_cart_lines(shop, [{"code": "V1", "qty": 1}], promo=False)
		act.assert_not_called()
		self.assertEqual(out[0]["price"], 500000)
		self.assertFalse(out[0]["baraban"])

	def test_token_of_other_shop_ignored(self):
		row = frappe._dict(name="x", shop="SHOP-B", soat=3, qolgan_soniya=100, oxirgi_signal=None)
		with patch("frappe.request", MagicMock(cookies={baraban._cookie_name("SHOP-A"): "t" * 24})), \
			patch("frappe.db.get_value", return_value=row):
			self.assertIsNone(baraban._row("SHOP-A"))
			self.assertIsNone(baraban.active("SHOP-A"))
