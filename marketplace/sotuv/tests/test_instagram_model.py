import frappe
from frappe.tests import UnitTestCase

SHOP_FIELDS = ("ig_ai_rejim", "ig_ai_malumot", "ig_user_id", "ig_username", "meta_ad_account")


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
