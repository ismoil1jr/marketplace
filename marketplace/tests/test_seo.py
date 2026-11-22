import datetime
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace import seo

BASE = "https://magazinlar.uz"


def fake_get_url(path=None, *a, **kw):
	return BASE + (path or "/")


class TestSeoHelpers(UnitTestCase):
	def setUp(self):
		p = patch.object(seo, "get_url", side_effect=fake_get_url)
		p.start()
		self.addCleanup(p.stop)

	def test_abs_url(self):
		self.assertEqual(seo.abs_url("/files/a b.jpg"), BASE + "/files/a%20b.jpg")
		self.assertEqual(seo.abs_url("files/x.webp"), BASE + "/files/x.webp")
		self.assertEqual(seo.abs_url("https://cdn.x/y.png"), "https://cdn.x/y.png")
		self.assertIsNone(seo.abs_url(None))
		self.assertEqual(seo.shop_url("Pandoo", "p", "Pandoo-panda-books"), BASE + "/s/Pandoo/p/Pandoo-panda-books")

	def test_meta_text_joins_and_cuts_on_word(self):
		self.assertEqual(seo.meta_text(" Ruchka bilan  o'qiydi ", None, "Payme"), "Ruchka bilan o'qiydi. Payme.")
		long = seo.meta_text("so'z " * 80)
		self.assertLessEqual(len(long), seo.DESC_LEN)
		self.assertTrue(long.endswith("…"))
		self.assertNotIn("so'…", long)

	def test_name_list_whole_names(self):
		self.assertEqual(seo.name_list(["Panda books", "Panda books", " Ruchka "]), "Panda books, Ruchka")
		self.assertEqual(seo.name_list(["a" * 50, "b" * 50]), "a" * 50)
		self.assertEqual(seo.name_list([]), "")

	def test_product_schema_offer(self):
		shop = frappe._dict(name="Pandoo", shop_name="Pandoo")
		product = frappe._dict(
			code="Pandoo-panda-books", name="Panda books", price=500000, images=["/files/1.webp"], thumb=None,
			description="Ruchka bilan bola o'zi o'qiydi", group="Kitoblar", in_stock=True, coming_soon=0, no_price=False,
		)
		d = seo.product_schema(shop, product, BASE + "/s/Pandoo/p/Pandoo-panda-books")
		self.assertEqual(d["@type"], "Product")
		self.assertEqual(d["image"], [BASE + "/files/1.webp"])
		self.assertEqual(d["offers"]["price"], "500000")
		self.assertEqual(d["offers"]["priceCurrency"], "UZS")
		self.assertEqual(d["offers"]["availability"], "https://schema.org/InStock")

	def test_product_schema_without_price_has_no_offer(self):
		shop = frappe._dict(name="S", shop_name="S")
		product = frappe._dict(code="X", name="X", price=0, images=[], thumb=None, description="", group=None,
			in_stock=False, coming_soon=0, no_price=True)
		d = seo.product_schema(shop, product, BASE + "/s/S/p/X")
		self.assertNotIn("offers", d)
		self.assertNotIn("image", d)

	def test_shop_schema_links_socials(self):
		shop = frappe._dict(name="Pandoo", shop_name="Pandoo", tagline="Bolalar kitoblari", logo="/files/l.png",
			cover_image=None, phone=None, city="Toshkent",
			socials=[{"href": "https://instagram.com/pandoo_books"}, {"href": "https://t.me/pando_books"}])
		d = seo.shop_schema(shop, BASE + "/s/Pandoo", [{"name": "Panda books"}])
		self.assertEqual(d["sameAs"], ["https://instagram.com/pandoo_books", "https://t.me/pando_books"])
		self.assertIn("Panda books", d["description"])
		self.assertEqual(d["logo"], BASE + "/files/l.png")
		self.assertNotIn("telephone", d)  # bo'sh maydonlar JSON-LD'ga tushmaydi

	def test_robots_txt(self):
		with patch("frappe.db.get_single_value", return_value=""):
			txt = seo.robots_txt()
		self.assertIn("User-agent: *", txt)
		self.assertIn("Disallow: /desk", txt)
		self.assertIn("Disallow: /api/", txt)
		self.assertNotIn("Disallow: /s/", txt)
		self.assertIn(f"Sitemap: {BASE}/sitemap.xml", txt)

	def test_sitemap_lists_shops_and_products(self):
		d = datetime.datetime(2026, 11, 20, 10, 0)
		shops = [frappe._dict(name="Pandoo", modified=d)]
		items = [frappe._dict(name="Pandoo-panda-books", shop="Pandoo", modified=datetime.datetime(2026, 11, 21))]
		with patch("frappe.get_all", return_value=shops), patch("frappe.db.sql", return_value=items):
			links = seo.sitemap_links()
		locs = [x["loc"] for x in links]
		self.assertEqual(locs, [BASE + "/", BASE + "/s/Pandoo", BASE + "/s/Pandoo/p/Pandoo-panda-books"])
		self.assertEqual(links[1]["lastmod"], "2026-11-21")

	def test_sitemap_no_shops(self):
		with patch("frappe.get_all", return_value=[]):
			self.assertEqual([x["loc"] for x in seo.sitemap_links()], [BASE + "/"])
