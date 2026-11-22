"""Mijoz sessiyasi: parallel so'rovlar (chat polling + yuborish) bir-birini yiqitmasin.

current_customer() har so'rovda Customer Session.last_seen'ni yozardi — bir mijozning ikki parallel so'rovi bitta
qatorni yangilab, MariaDB 1020 «Record has changed since last read» (QueryDeadlockError) bilan yiqilardi."""

import secrets
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, get_datetime, now_datetime

from marketplace import customers


class TestCurrentCustomer(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.customer = customers.get_or_create_customer("+998901110021", "Seans", "Sinov")
		self.token = secrets.token_urlsafe(16)
		self.session = frappe.get_doc({
			"doctype": "Customer Session", "customer": self.customer, "phone": "+998901110021",
			"token_hash": customers._hash(self.token), "expires_at": add_to_date(now_datetime(), days=1),
			"last_seen": now_datetime(),
		}).insert(ignore_permissions=True).name
		p = patch.object(frappe, "request", SimpleNamespace(cookies={customers.COOKIE: self.token}), create=True)
		p.start()
		self.addCleanup(p.stop)

	def seen(self):
		return get_datetime(frappe.db.get_value("Customer Session", self.session, "last_seen"))

	def test_recent_last_seen_is_not_rewritten(self):
		with patch.object(frappe.db, "set_value", wraps=frappe.db.set_value) as sv:
			self.assertEqual(customers.current_customer().customer, self.customer)
		self.assertFalse([c for c in sv.call_args_list if c.args[:1] == ("Customer Session",)])

	def test_old_last_seen_is_refreshed(self):
		old = add_to_date(now_datetime(), minutes=-30)
		frappe.db.set_value("Customer Session", self.session, "last_seen", old, update_modified=False)
		customers.current_customer()
		self.assertGreater(self.seen(), get_datetime(old))

	def test_conflict_on_last_seen_does_not_fail_request(self):
		frappe.db.set_value("Customer Session", self.session, "last_seen", add_to_date(now_datetime(), minutes=-30), update_modified=False)
		real = frappe.db.set_value

		def conflict(doctype, *a, **kw):
			if doctype == "Customer Session":
				raise frappe.QueryDeadlockError("1020 Record has changed since last read")
			return real(doctype, *a, **kw)

		with patch.object(frappe.db, "set_value", side_effect=conflict):
			self.assertEqual(customers.current_customer().customer, self.customer)
