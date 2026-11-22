"""Lokal «Test kirish» (botsiz): faqat developer_mode + *.local saytda; prod'da (magazinlar.uz) — yo'q."""

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace import api


class TestDevLogin(UnitTestCase):
	def test_enabled_only_on_local_dev_site(self):
		with patch.dict(frappe.local.conf, {"developer_mode": 1}), patch.object(frappe.local, "site", "marketplace.local"):
			self.assertTrue(api.dev_login_enabled())
		with patch.dict(frappe.local.conf, {"developer_mode": 0}), patch.object(frappe.local, "site", "marketplace.local"):
			self.assertFalse(api.dev_login_enabled())
		with patch.dict(frappe.local.conf, {"developer_mode": 1}), patch.object(frappe.local, "site", "magazinlar.uz"):
			self.assertFalse(api.dev_login_enabled())

	def test_endpoint_refuses_on_prod(self):
		with patch.object(api, "dev_login_enabled", return_value=False), patch("marketplace.customers.start_session") as start:
			with self.assertRaises(frappe.PermissionError):
				api.dev_login("nafis-tekstil")
			start.assert_not_called()
