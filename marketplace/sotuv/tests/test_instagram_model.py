import frappe
from frappe.tests import UnitTestCase

SHOP_FIELDS = ("ig_ai_rejim", "ig_ai_malumot", "ig_user_id", "ig_username", "meta_ad_account", "ig_holat")
READ_ONLY = ("holat", "tashqi_id", "ota_id", "mijoz_id", "javob_id", "shop", "turi", "media_id", "media_havola",
	"username", "matn", "vaqt", "til", "post_matni")
INDEXED = ("shop", "holat", "mijoz_id", "vaqt", "javob_id")


class TestInstagramModel(UnitTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_shop_has_ai_fields(self):
		meta = frappe.get_meta("Shop")
		for f in SHOP_FIELDS:
			self.assertTrue(meta.has_field(f), f)

	def test_tashqi_id_unique(self):
		shop = frappe.db.get_value("Shop", {}, "name")
		if not shop:
			self.skipTest("Bazada Shop yo'q: unique testi uchun kamida bitta Shop kerak")
		for _i in range(2):
			doc = frappe.get_doc(
				{"doctype": "Instagram Xabar", "shop": shop, "tashqi_id": "test-unique-1", "matn": "salom"}
			)
			if _i == 0:
				doc.insert(ignore_permissions=True)
			else:
				with self.assertRaises(frappe.UniqueValidationError):
					doc.insert(ignore_permissions=True)

	def test_shop_ig_holat_read_only(self):
		f = frappe.get_meta("Shop").get_field("ig_holat")
		self.assertEqual((f.fieldtype, f.label, f.read_only), ("Small Text", "Instagram AI holati", 1))

	def test_xabar_system_fields_read_only(self):
		meta = frappe.get_meta("Instagram Xabar")
		for f in READ_ONLY:
			self.assertTrue(meta.get_field(f).read_only, f)
		self.assertFalse(meta.get_field("ai_javob").read_only)
		self.assertEqual(meta.get_field("post_matni").fieldtype, "Small Text")

	def test_xabar_indexes(self):
		meta = frappe.get_meta("Instagram Xabar")
		cols = {r.Column_name for r in frappe.db.sql("show index from `tabInstagram Xabar`", as_dict=True)}
		for f in INDEXED:
			self.assertTrue(meta.get_field(f).search_index, f)
			self.assertIn(f, cols)
