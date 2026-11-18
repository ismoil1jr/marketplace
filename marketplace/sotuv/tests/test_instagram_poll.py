from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram
from marketplace.sotuv.meta import MetaError

SHOP = "Test Shop Poll"
LOCK = frappe.cache.make_key("mp_ig_poll_lock")
KEYS = [f"mp_ig_pause:{SHOP}", f"mp_ig_since:{SHOP}", "mp_ig_ai_pause"]


class TestInstagramPoll(UnitTestCase):
	def setUp(self):
		self._clear()

	def tearDown(self):
		self._clear()

	def _clear(self):
		for k in KEYS:
			frappe.cache.delete_value(k)
		frappe.cache.delete(LOCK)

	def _run(self, fetch, store=None, shops=(SHOP,), sweep=()):
		def get_all(doctype, **kw):
			return list(sweep) if doctype == "Instagram Xabar" else list(shops)

		with patch.object(instagram.frappe, "get_all", side_effect=get_all) as ga, \
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
		self.assertEqual(ga.call_args_list[0].kwargs["filters"]["ig_ai_rejim"], ["!=", "O'chiq"])

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

	def test_poll_sweep_enqueues_stranded(self):
		_, _, _, _, _, enq = self._run(lambda *a: [], sweep=["IGX-1"])
		enq.assert_called_once()
		self.assertEqual(enq.call_args.kwargs["job_id"], "igx-IGX-1")

	def test_sweep_filters_window(self):
		with patch.object(instagram.frappe, "get_all", return_value=[]) as ga, \
			patch.object(instagram.frappe, "enqueue"):
			instagram._sweep(SHOP)
		f = ga.call_args.kwargs["filters"]
		self.assertEqual(f["holat"], "Yangi")
		self.assertEqual(f["creation"][0], "<")
		self.assertEqual(f["vaqt"][0], ">")
		self.assertTrue(f["vaqt"][1] < f["creation"][1])
		self.assertEqual(ga.call_args.kwargs["limit"], 50)

	def test_poll_lock_held_skips(self):
		frappe.cache.set(LOCK, 1, ex=60)
		_, f, *_ = self._run(lambda *a: [])
		f.assert_not_called()

	def test_poll_releases_lock(self):
		self._run(lambda *a: [])
		self.assertFalse(frappe.cache.get(LOCK))

	def test_poll_since_never_moves_back(self):
		future = int(__import__("time").time()) + 100
		frappe.cache.set_value(f"mp_ig_since:{SHOP}", future)
		self._run(lambda *a: [])
		self.assertEqual(int(frappe.cache.get_value(f"mp_ig_since:{SHOP}")), future)
