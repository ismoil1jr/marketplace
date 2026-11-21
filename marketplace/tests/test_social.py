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


class TestBarabanPicker(UnitTestCase):
	def test_picker_requires_shop_permission(self):
		from marketplace import baraban

		with patch("frappe.has_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				baraban.tovarlar("SHOP-X")

	def test_link_query_needs_shop(self):
		from marketplace import baraban

		self.assertEqual(baraban.tovar_query("Item", "", "name", 0, 10, {}), [])
