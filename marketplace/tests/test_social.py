from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.storefront import social_links, social_url


class TestSocialLinks(UnitTestCase):
	"""Footer: do'kon egasi yozgan havola/@username -> xavfsiz https havola."""

	def test_handles_become_links(self):
		self.assertEqual(social_url("telegram", "@pandoo_books"), "https://t.me/pandoo_books")
		self.assertEqual(social_url("telegram", "t.me/pandoo_books"), "https://t.me/pandoo_books")
		self.assertEqual(social_url("instagram", "pandoo_books"), "https://instagram.com/pandoo_books")
		self.assertEqual(social_url("youtube", "@PandaBooks"), "https://youtube.com/@PandaBooks")
		self.assertEqual(social_url("x", "@pandoo"), "https://x.com/pandoo")
		self.assertEqual(social_url("facebook", "pandoobooks"), "https://facebook.com/pandoobooks")

	def test_full_links_kept(self):
		url = "https://www.instagram.com/pandoo_books/"
		self.assertEqual(social_url("instagram", url), url)

	def test_whatsapp_numbers(self):
		self.assertEqual(social_url("whatsapp", "+998 90 123 45 67"), "https://wa.me/998901234567")
		self.assertEqual(social_url("whatsapp", "90 123 45 67"), "https://wa.me/998901234567")
		self.assertIsNone(social_url("whatsapp", "abc"))

	def test_unsafe_rejected(self):
		self.assertIsNone(social_url("telegram", "javascript:alert(1)"))
		self.assertIsNone(social_url("instagram", "<script>"))
		self.assertIsNone(social_url("x", 'http://x.com/a"onmouseover=1'))
		self.assertIsNone(social_url("youtube", ""))
		self.assertIsNone(social_url("youtube", None))

	def test_social_links_order_and_skip_empty(self):
		shop = frappe._dict(instagram="@a", telegram_kanal="@b", youtube="", whatsapp="901234567")
		self.assertEqual([s["kind"] for s in social_links(shop)], ["telegram", "instagram", "whatsapp"])


class TestAutoCart(UnitTestCase):
	"""«Savatda tayyor tursin»: qaysi tovar har bir mijoz savatiga tushadi."""

	def _build(self, rows, variants=None, stock=None, prices=None):
		from marketplace import storefront

		shop = frappe._dict(name="SHOP-A", warehouse="W")
		calls = {"n": 0}

		def get_all(doctype, **kw):
			calls["n"] += 1
			return rows if calls["n"] == 1 else (variants or [])

		with patch("frappe.get_all", side_effect=get_all), \
			patch.object(storefront, "_get_stock", return_value=stock or {}), \
			patch.object(storefront, "_get_prices", side_effect=lambda codes: {c: (prices or {}).get(c, 0) for c in codes}), \
			patch.object(storefront, "_get_thumbnails", return_value={}), \
			patch.object(storefront, "variant_labels", side_effect=lambda codes: {c: "Ko'k" for c in codes}):
			return storefront._build_auto_cart(shop)

	def test_simple_item(self):
		rows = [frappe._dict(name="PEN", item_name="Ruchka", image="/p.png", has_variants=0, is_stock_item=0)]
		out = self._build(rows, prices={"PEN": 50000})
		self.assertEqual(out, [{"code": "PEN", "family": ["PEN"], "name": "Ruchka", "variant": None, "thumb": "/p.png", "price": 50000}])

	def test_variant_item_first_in_stock(self):
		rows = [frappe._dict(name="BOOK", item_name="Panda books", image=None, has_variants=1, is_stock_item=1)]
		vs = [frappe._dict(name="BOOK-A", is_stock_item=1), frappe._dict(name="BOOK-B", is_stock_item=1)]
		out = self._build(rows, vs, stock={"BOOK-A": 0, "BOOK-B": 3}, prices={"BOOK-B": 500000})
		self.assertEqual(out[0]["code"], "BOOK-B")
		self.assertEqual(out[0]["family"], ["BOOK", "BOOK-A", "BOOK-B"])
		self.assertEqual(out[0]["variant"], "Ko'k")

	def test_skips_out_of_stock_and_no_price(self):
		rows = [
			frappe._dict(name="OUT", item_name="Out", image=None, has_variants=0, is_stock_item=1),
			frappe._dict(name="FREE", item_name="Free", image=None, has_variants=0, is_stock_item=0),
		]
		self.assertEqual(self._build(rows, stock={"OUT": 0}, prices={"OUT": 1000}), [])

	def test_auto_cart_never_raises(self):
		from marketplace import storefront

		shop = frappe._dict(name="SHOP-ERR", warehouse="W")
		frappe.cache.delete_value(storefront._auto_cart_key(shop.name))
		with patch.object(storefront, "_build_auto_cart", side_effect=RuntimeError("x")), patch("frappe.log_error"):
			self.assertEqual(storefront.auto_cart(shop), [])
