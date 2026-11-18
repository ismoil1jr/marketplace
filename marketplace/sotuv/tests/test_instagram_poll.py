from unittest.mock import patch

import frappe
import requests
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram, instagram_dm, meta
from marketplace.sotuv.meta import MetaError

SHOP = "Test Shop Poll"
LOCK = frappe.cache.make_key("mp_ig_poll_lock")
KEYS = [f"mp_ig_pause:{SHOP}", f"mp_ig_since:{SHOP}", "mp_ig_ai_pause", f"mp_ig_last_err:{SHOP}"]
SECRET = "EAAGsecretPAGEtoken123"


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
			patch.object(instagram_dm, "fetch_messages", return_value=[]), \
			patch.object(instagram, "store", side_effect=store or (lambda s, c: c["id"])) as st, \
			patch.object(instagram, "_ig_status") as stat, \
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

	def test_enqueue_after_commit(self):
		_, _, _, _, _, enq = self._run(lambda *a: [{"id": "a"}])
		self.assertIs(enq.call_args.kwargs["enqueue_after_commit"], True)
		_, _, _, _, _, enq = self._run(lambda *a: [], sweep=["IGX-1"])
		self.assertIs(enq.call_args.kwargs["enqueue_after_commit"], True)

	def test_is_rate_limit(self):
		for code in (4, 17, 32, 613, 80000, 80001, 80002, 80006, 80014, 80099, "80004"):
			self.assertTrue(instagram.is_rate_limit(code), code)
		for code in (None, "", 10, 100, 190, 80100, 79999, "x"):
			self.assertFalse(instagram.is_rate_limit(code), code)

	def test_poll_buc_rate_limit_pauses_shop(self):
		def boom(*a):
			raise MetaError("Application request limit reached", code=80002)

		_, _, _, stat, le, _ = self._run(boom)
		self.assertTrue(frappe.cache.get_value(f"mp_ig_pause:{SHOP}"))
		stat.assert_called_once()
		le.assert_not_called()

	def test_poll_buc_rate_limit_from_dm_pauses_shop(self):
		with patch.object(instagram.frappe, "get_all", side_effect=lambda d, **kw: [] if d == "Instagram Xabar" else [SHOP]), \
			patch.object(instagram, "fetch_comments", return_value=[]), \
			patch.object(instagram_dm, "fetch_messages", side_effect=MetaError("limit", code=80006)), \
			patch.object(instagram, "_ig_status"), \
			patch.object(instagram.frappe, "log_error") as le, \
			patch.object(instagram.frappe, "enqueue"), \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		self.assertTrue(frappe.cache.get_value(f"mp_ig_pause:{SHOP}"))
		le.assert_not_called()

	def test_poll_network_error_never_logs_token(self):
		conf = frappe._dict(app_id="a", secret="s", verify="", ver="v23.0")
		url_err = requests.ConnectionError(
			f"HTTPSConnectionPool(host='graph.facebook.com'): Max retries exceeded with url: "
			f"/v23.0/1/media?access_token={SECRET}&appsecret_proof=abc123")

		def fetch(shop, since):
			return meta._graph("GET", "1/media", SECRET)

		with patch.object(meta, "_conf", return_value=conf), \
			patch.object(meta.requests, "request", side_effect=url_err):
			_, _, _, stat, le, _ = self._run(fetch)
		le.assert_called_once()
		logged = str(le.call_args.kwargs.get("message")) + str(le.call_args.args)
		self.assertNotIn(SECRET, logged)
		self.assertNotIn("access_token", logged)
		self.assertNotIn("Traceback", logged)
		self.assertNotIn(SECRET, str(stat.call_args))

	def test_poll_unexpected_error_traceback_is_scrubbed(self):
		def boom(*a):
			raise ValueError(f"bad url ?access_token={SECRET}&appsecret_proof=abc")

		_, _, _, _, le, _ = self._run(boom)
		le.assert_called_once()
		self.assertNotIn(SECRET, le.call_args.kwargs["message"])
		self.assertNotIn("appsecret_proof=abc", le.call_args.kwargs["message"])

	def _poll_real_status(self, fetch):
		sets = []
		with patch.object(instagram.frappe, "get_all", side_effect=lambda d, **kw: [] if d == "Instagram Xabar" else [SHOP]), \
			patch.object(instagram, "fetch_comments", side_effect=fetch), \
			patch.object(instagram_dm, "fetch_messages", return_value=[]), \
			patch.object(meta.frappe.db, "set_value", side_effect=lambda *a, **kw: sets.append(a)), \
			patch.object(instagram.frappe, "log_error") as le, \
			patch.object(instagram.frappe, "enqueue"), \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		return sets, le

	def test_poll_same_error_written_and_logged_once(self):
		def boom(*a):
			raise MetaError("Error validating access token: Session has expired", code=190)

		sets1, le1 = self._poll_real_status(boom)
		sets2, le2 = self._poll_real_status(boom)
		self.assertEqual(le1.call_count + le2.call_count, 1)
		self.assertEqual(len(sets1) + len(sets2), 1)
		dt, name, field = sets1[0][:3]
		self.assertEqual((dt, name, field), ("Shop", SHOP, "ig_holat"))
		self.assertFalse([s for s in sets1 + sets2 if "meta_holat" in s])
		# boshqa xato — yana yoziladi
		sets3, le3 = self._poll_real_status(lambda *a: (_ for _ in ()).throw(MetaError("x", code=100)))
		self.assertEqual((len(sets3), le3.call_count), (1, 1))


class TestIgStatus(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")
		self.key = f"mp_ig_last_err:{self.shop}"
		frappe.cache.delete_value(self.key)

	def tearDown(self):
		frappe.cache.delete_value(self.key)
		frappe.db.rollback()

	def test_ig_status_goes_to_ig_holat_not_meta_holat(self):
		frappe.db.set_value("Shop", self.shop, "meta_holat", "LEAD-HOLAT", update_modified=False)
		self.assertTrue(meta._ig_status(self.shop, "Direct xabarlarini olib bo'lmadi (kod 10)"))
		self.assertFalse(meta._ig_status(self.shop, "Direct xabarlarini olib bo'lmadi (kod 10)"))
		ig, lead = frappe.db.get_value("Shop", self.shop, ["ig_holat", "meta_holat"])
		self.assertIn("Direct xabarlarini olib bo'lmadi (kod 10)", ig)
		self.assertEqual(lead, "LEAD-HOLAT")
