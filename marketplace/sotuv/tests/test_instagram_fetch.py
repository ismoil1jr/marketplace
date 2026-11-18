import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram
from marketplace.sotuv.meta import MetaError

SHOP = "Test Shop"


def _iso(secs_ago):
	t = datetime.now(timezone.utc) - timedelta(seconds=secs_ago)
	return t.strftime("%Y-%m-%dT%H:%M:%S+0000")


def _shop_vals(**kw):
	vals = {"ig_user_id": "111", "ig_username": "mydokon", "meta_ad_account": ""}
	vals.update(kw)
	return lambda dt, name, field: vals.get(field)


class TestMediaList(UnitTestCase):
	def _run(self, graph, **shop):
		with patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram.frappe.db, "get_value", side_effect=_shop_vals(**shop)), \
			patch.object(instagram, "_status") as st, \
			patch.object(instagram, "_graph", side_effect=graph):
			return instagram.media_list(SHOP), st

	def test_media_list_merges_posts_and_ads(self):
		def graph(method, path, token=None, **p):
			if path.endswith("/media"):
				return {"data": [{"id": "m1", "permalink": "l1"}, {"id": "m2", "permalink": "l2"}]}
			return {"data": [
				{"creative": {"effective_instagram_media_id": "m2", "instagram_permalink_url": "l2"}},
				{"creative": {"effective_instagram_media_id": "m3", "instagram_permalink_url": "l3"}},
			]}
		out, _ = self._run(graph, meta_ad_account="act_1")
		self.assertEqual(sorted(m["id"] for m in out), ["m1", "m2", "m3"])

	def test_media_list_ads_error_keeps_posts(self):
		def graph(method, path, token=None, **p):
			if path.endswith("/media"):
				return {"data": [{"id": "m1", "permalink": "l1"}]}
			raise MetaError("boom", 200)
		out, st = self._run(graph, meta_ad_account="act_1")
		self.assertEqual([m["id"] for m in out], ["m1"])
		st.assert_called_once()


class TestFetch(UnitTestCase):
	def _fetch(self, comments, since):
		def graph(method, path, token=None, **p):
			if path.endswith("/media"):
				return {"data": [{"id": "m1", "permalink": "l1"}]}
			return {"data": comments}
		with patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram.frappe.db, "get_value", side_effect=_shop_vals()), \
			patch.object(instagram, "_status"), \
			patch.object(instagram, "_graph", side_effect=graph):
			return instagram.fetch_comments(SHOP, since)

	def test_fetch_skips_own_account(self):
		c = [{"id": "c1", "text": "a", "timestamp": _iso(10), "username": "x", "from": {"id": "9", "username": "x"},
			"replies": {"data": [{"id": "r1", "text": "b", "timestamp": _iso(5), "username": "mydokon",
				"from": {"id": "111", "username": "mydokon"}}]}}]
		out = self._fetch(c, int(time.time()) - 900)
		self.assertEqual([x["id"] for x in out], ["c1"])

	def test_fetch_ignores_old_comments(self):
		c = [{"id": "c1", "text": "a", "timestamp": _iso(20 * 60), "username": "x", "from": {"id": "9"}}]
		self.assertEqual(self._fetch(c, int(time.time()) - 900), [])

	def test_fetch_flattens_replies(self):
		c = [{"id": "c1", "text": "a", "timestamp": _iso(10), "username": "x", "from": {"id": "9"},
			"replies": {"data": [{"id": "r1", "text": "b", "timestamp": _iso(5), "username": "y", "from": {"id": "8"}}]}}]
		out = {x["id"]: x for x in self._fetch(c, int(time.time()) - 900)}
		self.assertIsNone(out["c1"]["parent_id"])
		self.assertEqual(out["r1"]["parent_id"], "c1")
		self.assertEqual(out["r1"]["media_id"], "m1")
		self.assertIsInstance(out["r1"]["timestamp"], int)


class TestStore(UnitTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_store_dedup(self):
		shop = frappe.db.get_value("Shop", {}, "name")
		if not shop:
			self.skipTest("Shop yo'q")
		c = {"id": "test_dedup_1", "parent_id": None, "text": "salom", "username": "u", "from_id": "5",
			"timestamp": int(time.time()), "media_id": "m1", "havola": "https://instagram.com/p/abc/"}
		self.assertTrue(instagram.store(shop, c))
		self.assertIsNone(instagram.store(shop, c))
