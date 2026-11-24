from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace import payments
from marketplace.sotuv import api


class FakeSO(frappe._dict):
	def db_set(self, values, update_modified=True):
		self.update(values)

	def add_comment(self, *args, **kwargs):
		pass


class TestTolanganOladi(UnitTestCase):
	"""Click/Payme orqali to'langan buyurtma menejerning «Yangi» bo'limida qo'ng'iroq kutmaydi: «To'langan · Oladi»."""

	def tearDown(self):
		frappe.db.rollback()

	def _pay(self, natija=None):
		so = FakeSO(name="SO-T", payment_status="To'lov kutilmoqda", delivery_method="Kuryer", per_delivered=0,
		            mp_aloqa_natija=natija)
		with patch("frappe.get_doc", return_value=so), patch("marketplace.kassa.stamp_paid"), \
			patch("marketplace.orders.confirm_order", return_value=True), \
			patch("marketplace.seller_desk.notify_couriers") as couriers, patch("marketplace.seller_desk.notify_shop"):
			payments.mark_paid("SO-T", "Click", "(Click 1)")
		return so, couriers

	def test_paid_becomes_oladi_and_goes_to_couriers(self):
		so, couriers = self._pay()
		self.assertEqual(so.payment_status, "To'langan")
		self.assertEqual(so.mp_aloqa_natija, "Oladi")
		self.assertTrue(so.mp_aloqa_vaqt)
		couriers.assert_called_once()

	def test_payment_after_keyinroq_wins(self):
		so, couriers = self._pay(natija="Keyinroq")  # menejer «Keyinroq» degan, keyin mijoz Click bilan to'ladi
		self.assertEqual(so.mp_aloqa_natija, "Oladi")
		couriers.assert_called_once()

	def test_yangi_excludes_paid(self):
		f = api._filters("yangi", "SHOP")
		self.assertIn("To'langan", f["payment_status"][1])
		self.assertEqual(f["payment_status"][0], "not in")

	def test_patch_marks_old_paid_orders(self):
		from marketplace.patches import tolangan_buyurtma_oladi

		name = frappe.db.get_value("Sales Order", {"docstatus": 1})
		if not name:
			self.skipTest("Buyurtma yo'q")
		frappe.db.set_value("Sales Order", name, {"payment_status": "To'langan", "payment_method": "Click", "mp_aloqa_natija": None},
		                    update_modified=False)
		tolangan_buyurtma_oladi.execute()
		self.assertEqual(frappe.db.get_value("Sales Order", name, "mp_aloqa_natija"), "Oladi")
