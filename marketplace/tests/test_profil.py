"""Profil: bitta qurilmani chiqarish (faqat o'zinikini, shu qurilmani emas) va sevimlilar ro'yxati."""

import secrets
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from marketplace import api, customers

SHOP = "nafis-tekstil"


def _session(customer, phone):
	token_hash = customers._hash(secrets.token_urlsafe(16))
	doc = frappe.get_doc({"doctype": "Customer Session", "customer": customer, "phone": phone, "token_hash": token_hash,
	                      "expires_at": add_to_date(now_datetime(), days=1), "last_seen": now_datetime()}).insert(ignore_permissions=True)
	return doc.name, token_hash


class TestProfil(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Shop", SHOP):
			self.skipTest("nafis-tekstil yo'q")
		self.addCleanup(frappe.db.rollback)
		self.me = customers.get_or_create_customer("+998901110011", "Profil", "Bir", shop=SHOP)
		self.other = customers.get_or_create_customer("+998901110012", "Profil", "Ikki", shop=SHOP)

	def test_end_one_session_only_own_and_not_current(self):
		current, current_hash = _session(self.me, "+998901110011")
		laptop, _ = _session(self.me, "+998901110011")
		foreign, _ = _session(self.other, "+998901110012")
		with patch.object(customers, "_current_token_hash", return_value=current_hash):
			customers.end_one_session(self.me, laptop)
			self.assertFalse(frappe.db.exists("Customer Session", laptop))
			with self.assertRaises(frappe.ValidationError):
				customers.end_one_session(self.me, foreign)  # boshqa mijozniki
			with self.assertRaises(frappe.ValidationError):
				customers.end_one_session(self.me, current)  # shu qurilma — «Chiqish» tugmasi bilan
		self.assertTrue(frappe.db.exists("Customer Session", foreign))
		self.assertTrue(frappe.db.exists("Customer Session", current))

	def test_fav_items_only_this_shop_published_in_order(self):
		mine = frappe.get_all("Item", filters={"shop": SHOP, "is_published": 1, "disabled": 0, "variant_of": ["is", "not set"]},
		                      pluck="name", limit=2)
		foreign = frappe.get_all("Item", filters={"shop": ["!=", SHOP], "is_published": 1}, pluck="name", limit=1)
		if len(mine) < 2:
			self.skipTest("tovar yetarli emas")
		cards = api.fav_items(SHOP, [mine[1], "yoq-tovar", *foreign, mine[0]])
		self.assertEqual([c["code"] for c in cards], [mine[1], mine[0]])
		self.assertTrue(cards[0]["url"].startswith(f"/s/{SHOP}/p/"))
