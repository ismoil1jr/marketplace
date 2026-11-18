from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram
from marketplace.sotuv.meta import MetaError

SHOP = "Test Shop Poll"
KEYS = [f"mp_ig_pause:{SHOP}", f"mp_ig_since:{SHOP}", "mp_ig_ai_pause"]


class TestInstagramPoll(UnitTestCase):
	def setUp(self):
		self._clear()

	def tearDown(self):
		self._clear()

	def _clear(self):
		for k in KEYS:
			frappe.cache.delete_value(k)

	def _run(self, fetch, store=None, shops=(SHOP,)):
		with patch.object(instagram.frappe, "get_all", return_value=list(shops)) as ga, \
			patch.object(instagram, "fetch_comments", side_effect=fetch) as f, \
			patch.object(instagram, "store", side_effect=store or (lambda s, c: c["id"])) as st, \
			patch.object(instagram, "_status") as stat, \
			patch.object(instagram.frappe, "log_error") as le, \
			patch.object(instagram.frappe, "enqueue") as enq, \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		return ga, f, st, stat, le, enq

	def test_poll_skips_off_shops(self):
		ga, f, *_ = self._run(lambda *a: [], shops=())
		f.assert_not_called()
		self.assertEqual(ga.call_args.kwargs["filters"]["ig_ai_rejim"], ["!=", "O'chiq"])

	def test_poll_rate_limit_pauses_shop(self):
		def boom(*a):
			raise MetaError("limit", code=4)

		_, f, _, stat, le, _ = self._run(boom)
		self.assertTrue(frappe.cache.get_value(f"mp_ig_pause:{SHOP}"))
		stat.assert_called_once()
		le.assert_not_called()
		self.assertFalse(frappe.cache.get_value(f"mp_ig_since:{SHOP}"))
		_, f2, *_ = self._run(boom)
		f2.assert_not_called()

	def test_poll_enqueues_new_only(self):
		comments = [{"id": "a"}, {"id": "b"}]
		_, f, st, _, _, enq = self._run(
			lambda *a: comments, store=lambda s, c: c["id"] if c["id"] == "a" else None)
		self.assertEqual(st.call_count, 2)
		enq.assert_called_once()
		self.assertEqual(enq.call_args.kwargs["name"], "a")
		self.assertEqual(enq.call_args.kwargs["job_id"], "igx-a")
		self.assertTrue(int(frappe.cache.get_value(f"mp_ig_since:{SHOP}")) > 0)

	def test_poll_other_error_logged_and_continues(self):
		def boom(shop, since):
			if shop == SHOP:
				raise ValueError("x")
			return []

		_, f, _, stat, le, _ = self._run(boom, shops=(SHOP, "Other"))
		self.assertEqual(f.call_count, 2)
		stat.assert_called_once()
		le.assert_called_once()

	def test_poll_global_ai_pause_skips_all(self):
		frappe.cache.set_value("mp_ig_ai_pause", 1, expires_in_sec=60)
		ga, f, *_ = self._run(lambda *a: [])
		f.assert_not_called()
