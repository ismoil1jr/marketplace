import traceback
from unittest.mock import patch

import frappe
import requests
from frappe.tests import UnitTestCase

from marketplace.sotuv import meta
from marketplace.sotuv.meta import MetaError

SHOP = "Test Shop"
PAGE = {"id": "p1", "name": "Sahifa", "access_token": "ptok"}


def _graph_factory(ig=True, accounts=None, ig_error=False, ad_error=False):
	def graph(method, path, token=None, **p):
		if path == "p1":
			if ig_error:
				raise MetaError("boom", 10)
			return {"instagram_business_account": {"id": "17841", "username": "mydokon"}} if ig else {"id": "p1"}
		if path == "me/adaccounts":
			if ad_error:
				raise MetaError("nope", 200)
			return {"data": accounts or []}
		raise AssertionError(path)
	return graph


class TestLinkInstagram(UnitTestCase):
	def _run(self, current_ad="", user_token="utok", **kw):
		with patch.object(meta, "_graph", side_effect=_graph_factory(**kw)), \
			patch.object(meta.frappe.db, "get_value", return_value=current_ad), \
			patch.object(meta.frappe.db, "set_value") as sv:
			warning = meta._link_instagram(SHOP, PAGE, user_token)
		saved = {}
		for c in sv.call_args_list:
			saved.update(c.args[2])
			self.assertIs(c.kwargs.get("update_modified"), False)
		return warning, saved

	def test_link_instagram_sets_ids(self):
		warning, saved = self._run(accounts=[{"account_id": "123", "name": "A", "account_status": 1}])
		self.assertIsNone(warning)
		self.assertEqual(saved, {"ig_user_id": "17841", "ig_username": "mydokon", "meta_ad_account": "act_123"})

	def test_link_instagram_two_ad_accounts_warns(self):
		warning, saved = self._run(accounts=[{"account_id": "1", "name": "Alfa", "account_status": 1},
			{"account_id": "2", "name": "Beta", "account_status": 1}, {"account_id": "3", "name": "Gamma", "account_status": 2}])
		self.assertNotIn("meta_ad_account", saved)
		self.assertIn("Alfa", warning)
		self.assertIn("Beta", warning)
		self.assertNotIn("Gamma", warning)

	def test_link_instagram_no_ig_warns(self):
		warning, saved = self._run(ig=False, accounts=[{"account_id": "123", "name": "A", "account_status": 1}])
		self.assertIn("Instagram professional akkaunt ulanmagan", warning)
		self.assertEqual(saved["ig_user_id"], "")
		self.assertEqual(saved["ig_username"], "")

	def test_link_instagram_never_raises_and_keeps_manual_ad_account(self):
		warning, saved = self._run(current_ad="act_9", ig_error=True, ad_error=True)
		self.assertTrue(warning)
		self.assertNotIn("meta_ad_account", saved)
		self.assertNotIn("utok", warning)
		self.assertNotIn("ptok", warning)

	def test_link_instagram_without_user_token_skips_ads(self):
		with patch.object(meta, "_graph", side_effect=_graph_factory()) as g, \
			patch.object(meta.frappe.db, "set_value"):
			warning = meta._link_instagram(SHOP, PAGE, None)
		self.assertTrue(warning)
		self.assertNotIn("me/adaccounts", [c.args[1] for c in g.call_args_list])


class TestGraphNoLeak(UnitTestCase):
	def test_network_error_does_not_chain_url_with_token(self):
		secret = "EAAGsecretPAGEtoken123"
		err = requests.ConnectionError(
			f"Max retries exceeded with url: /v23.0/me?access_token={secret}&appsecret_proof=abc123")
		conf = frappe._dict(app_id="a", secret="s", verify="", ver="v23.0")
		with patch.object(meta, "_conf", return_value=conf), \
			patch.object(meta.requests, "request", side_effect=err):
			with self.assertRaises(MetaError) as cm:
				meta._graph("GET", "me", secret)
		e = cm.exception
		self.assertIsNone(e.__cause__)
		self.assertTrue(e.__suppress_context__)
		text = "".join(traceback.format_exception(e))
		self.assertNotIn(secret, text)
		self.assertNotIn("access_token", text)


class TestAdAccount(UnitTestCase):
	def test_act_prefix(self):
		self.assertEqual(meta.ad_account("123"), "act_123")
		self.assertEqual(meta.ad_account(" act_123 "), "act_123")
		self.assertEqual(meta.ad_account(""), "")
		self.assertEqual(meta.ad_account(None), "")
