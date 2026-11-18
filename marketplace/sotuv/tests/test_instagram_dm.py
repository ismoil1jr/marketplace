import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram, instagram_dm
from marketplace.sotuv.meta import MetaError

IG, CUST, SINCE = "ig1", "cust1", 1000


def _iso(secs_ago):
	return (datetime.now(timezone.utc) - timedelta(seconds=secs_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


CREATED = _iso(60)  # > SINCE va oxirgi 24 soat ichida (operator xabari pauzani faqat 24 soat ichida yoqadi)
AI_OK = {"javob_kerak": True, "javob": "Salom", "til": "uz", "telefon": None,
	"ism": None, "tovar_kodi": None, "model": "m"}


def _msg(i, frm, text="salom", t=CREATED):
	return {"id": i, "message": text, "created_time": t, "from": {"id": frm, "username": frm}}


def _conv(*msgs, updated=CREATED):
	return {"data": [{"id": "c1", "updated_time": updated, "messages": {"data": list(msgs)}}]}


class TestInstagramDm(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")
		self.n = 0
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)
		self.key = f"mp_ig_human:{self.shop}:{CUST}"
		frappe.cache.delete_value(self.key)

	def tearDown(self):
		frappe.cache.delete_value(self.key)
		frappe.db.rollback()

	def _doc(self, **kw):
		self.n += 1
		vals = {"doctype": "Instagram Xabar", "shop": self.shop, "turi": "DM", "holat": "Yangi",
			"tashqi_id": f"t7-{frappe.generate_hash(length=8)}-{self.n}", "mijoz_id": CUST,
			"username": "ali", "matn": "narxi qancha?"}
		vals.update(kw)
		return frappe.get_doc(vals).insert(ignore_permissions=True)

	def _fetch(self, graph_data, since=SINCE):
		fake = {"meta_page_id": "PG", "ig_user_id": IG}
		with patch.object(instagram, "_shop", side_effect=lambda s, f: fake.get(f, "")), \
			patch.object(instagram_dm, "_page_token", return_value="tok"), \
			patch.object(instagram_dm, "_graph", return_value=graph_data) as g:
			res = instagram_dm.fetch_messages(self.shop, since)
		return res, g

	def _ttl(self):
		return frappe.cache.ttl(frappe.cache.make_key(self.key))

	def test_dm_fetch_customer_messages_only(self):
		self._doc(javob_id="OURS", holat="Yuborildi", ai_javob="x")
		res, g = self._fetch(_conv(_msg("m3", CUST, "yana"), _msg("OURS", IG, "boshqa"), _msg("m1", CUST, "bor")))
		self.assertEqual([m["id"] for m in res], ["m3", "m1"])
		self.assertEqual(res[0]["suhbat_id"], "c1")
		self.assertEqual(g.call_args.args[1], "PG/conversations")
		self.assertFalse(instagram_dm.is_human_paused(self.shop, CUST))

	def test_dm_own_reply_matched_by_text(self):
		self._doc(holat="Yuborildi", ai_javob="Salom, narxi 100", javob_id="OTHER-ID")
		self._fetch(_conv(_msg("conv-id", IG, "Salom, narxi 100"), _msg("m1", CUST)))
		self.assertFalse(instagram_dm.is_human_paused(self.shop, CUST))

	def test_dm_skips_empty_text_and_old(self):
		res, _ = self._fetch(_conv(_msg("m2", CUST, ""), _msg("m1", CUST, "x", "1970-01-01T00:00:10+0000")))
		self.assertEqual(res, [])

	def test_dm_old_operator_message_does_not_pause(self):
		self._fetch(_conv(_msg("op", IG, "eski", "1970-01-01T00:00:10+0000"), _msg("m1", CUST)))
		self.assertFalse(instagram_dm.is_human_paused(self.shop, CUST))

	def test_dm_operator_message_pauses_ai(self):
		self._fetch(_conv(_msg("op1", IG, "men yozaman"), _msg("m1", CUST)))
		self.assertTrue(instagram_dm.is_human_paused(self.shop, CUST))
		doc = self._doc()
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram.ig_ai, "answer", return_value=AI_OK) as ai, \
			patch.object(instagram, "_graph") as g:
			res = instagram.process(doc.name)
		doc.reload()
		self.assertEqual((res, doc.holat, doc.xato), ("Qoralama", "Qoralama", "Operator suhbatda"))
		g.assert_not_called()
		ai.assert_not_called()

	def test_dm_send_targets_sender(self):
		doc = self._doc(ai_javob="Salom")
		fake = {"meta_page_id": "PG"}
		with patch.object(instagram, "_shop", side_effect=lambda s, f: fake.get(f, "")), \
			patch.object(instagram_dm, "_page_token", return_value="tok"), \
			patch.object(instagram_dm, "_graph", return_value={"message_id": "MID"}) as g:
			mid = instagram._deliver(self.shop, doc)
		self.assertEqual(mid, "MID")
		args, kw = g.call_args
		self.assertEqual(args[:3], ("POST", "PG/messages", "tok"))
		self.assertEqual(json.loads(kw["recipient"]), {"id": CUST})
		self.assertEqual(json.loads(kw["message"]), {"text": "Salom"})

	def test_dm_history_order(self):
		a = self._doc(matn="bir", ai_javob="javob1", holat="Yuborildi", vaqt="2026-11-17 10:00:00")
		self._doc(matn="ikki", holat="Qoralama", ai_javob="qoralama", vaqt="2026-11-17 10:01:00")
		self._doc(matn="uch", holat="Javobsiz", vaqt="2026-11-17 10:02:00")
		cur = self._doc(matn="hozir", vaqt="2026-11-17 10:03:00")
		self._doc(matn="boshqa mijoz", mijoz_id="zzz", vaqt="2026-11-17 10:00:30")
		self.assertTrue(a)
		self.assertEqual(instagram_dm.history(cur), [
			{"kim": "Mijoz", "matn": "bir"}, {"kim": "Do'kon", "matn": "javob1"},
			{"kim": "Mijoz", "matn": "ikki"}, {"kim": "Mijoz", "matn": "uch"}])

	def test_poll_includes_dms(self):
		def get_all(doctype, **kw):
			return [] if doctype == "Instagram Xabar" else ["Test Shop Dm"]

		lock = frappe.cache.make_key("mp_ig_poll_lock")
		keys = ["mp_ig_pause:Test Shop Dm", "mp_ig_since:Test Shop Dm", "mp_ig_ai_pause"]
		for k in keys:
			frappe.cache.delete_value(k)
		frappe.cache.delete(lock)
		self.addCleanup(lambda: [frappe.cache.delete_value(k) for k in keys] + [frappe.cache.delete(lock)])
		with patch.object(instagram.frappe, "get_all", side_effect=get_all), \
			patch.object(instagram, "fetch_comments", return_value=[{"id": "c"}]), \
			patch.object(instagram_dm, "fetch_messages", return_value=[{"id": "d"}]), \
			patch.object(instagram, "store", side_effect=lambda s, c, turi="Izoh": f"{turi}-{c['id']}") as st, \
			patch.object(instagram.frappe, "enqueue") as enq, \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		self.assertEqual(enq.call_count, 2)
		self.assertEqual(st.call_args_list[1].kwargs["turi"], "DM")

	def test_poll_dm_error_does_not_block_comments(self):
		def get_all(doctype, **kw):
			return [] if doctype == "Instagram Xabar" else ["Test Shop Dm"]

		lock = frappe.cache.make_key("mp_ig_poll_lock")
		keys = ["mp_ig_pause:Test Shop Dm", "mp_ig_since:Test Shop Dm", "mp_ig_ai_pause"]
		for k in keys:
			frappe.cache.delete_value(k)
		frappe.cache.delete(lock)
		self.addCleanup(lambda: [frappe.cache.delete_value(k) for k in keys] + [frappe.cache.delete(lock)])
		with patch.object(instagram.frappe, "get_all", side_effect=get_all), \
			patch.object(instagram, "fetch_comments", return_value=[{"id": "c"}]), \
			patch.object(instagram_dm, "fetch_messages", side_effect=MetaError("x", code=10)), \
			patch.object(instagram, "store", side_effect=lambda s, c, turi="Izoh": c["id"]), \
			patch.object(instagram, "_ig_status") as stat, \
			patch.object(instagram.frappe, "enqueue") as enq, \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		enq.assert_called_once()
		stat.assert_called_once()
		self.assertTrue(int(frappe.cache.get_value("mp_ig_since:Test Shop Dm")) > 0)

	def test_dm_no_ig_user_id_returns_nothing(self):
		fake = {"meta_page_id": "PG", "ig_user_id": ""}
		with patch.object(instagram, "_shop", side_effect=lambda s, f: fake.get(f, "")), \
			patch.object(instagram_dm, "_page_token", return_value="tok"), \
			patch.object(instagram_dm, "_ig_status") as stat, \
			patch.object(instagram_dm, "_graph") as g:
			res = instagram_dm.fetch_messages(self.shop, SINCE)
		self.assertEqual(res, [])
		g.assert_not_called()
		stat.assert_called_once()

	def test_dm_own_text_match_is_whitespace_normalized(self):
		self._doc(holat="Yuborildi", ai_javob="Assalomu alaykum!  Ha, bor.\n", javob_id="X")
		self._fetch(_conv(_msg("cid", IG, "Assalomu alaykum! Ha, bor."), _msg("m1", CUST)))
		self.assertFalse(instagram_dm.is_human_paused(self.shop, CUST))

	def test_dm_different_text_arms_pause(self):
		self._doc(holat="Yuborildi", ai_javob="Assalomu alaykum! Ha, bor.", javob_id="X")
		self._fetch(_conv(_msg("cid", IG, "Assalomu alaykum! Yo'q, tugadi."), _msg("m1", CUST)))
		self.assertTrue(instagram_dm.is_human_paused(self.shop, CUST))

	def test_poll_coalesces_burst_per_customer(self):
		lock = frappe.cache.make_key("mp_ig_poll_lock")
		keys = ["mp_ig_pause:Test Shop Dm", "mp_ig_since:Test Shop Dm", "mp_ig_ai_pause"]
		for k in keys:
			frappe.cache.delete_value(k)
		frappe.cache.delete(lock)
		self.addCleanup(lambda: [frappe.cache.delete_value(k) for k in keys] + [frappe.cache.delete(lock)])
		msgs = [{"id": f"b{i}", "from_id": CUST, "timestamp": 2000 + i} for i in (1, 3, 2)]
		msgs.append({"id": "o1", "from_id": "other", "timestamp": 2001})
		sets = []
		with patch.object(instagram.frappe, "get_all", side_effect=lambda d, **kw: [] if d == "Instagram Xabar" else ["Test Shop Dm"]), \
			patch.object(instagram, "fetch_comments", return_value=[]), \
			patch.object(instagram_dm, "fetch_messages", return_value=msgs), \
			patch.object(instagram, "store", side_effect=lambda s, c, turi="Izoh": c["id"]), \
			patch.object(instagram.frappe.db, "set_value", side_effect=lambda dt, n, v: sets.append((n, v))), \
			patch.object(instagram.frappe, "enqueue") as enq, \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		self.assertEqual(sorted(c.kwargs["name"] for c in enq.call_args_list), ["b3", "o1"])
		self.assertEqual(sorted(n for n, _v in sets), ["b1", "b2"])
		self.assertTrue(all(v["holat"] == "Javobsiz" and v["xato"] == "Keyingi xabar bilan birga javob beriladi" for _n, v in sets))

	def test_dm_history_of_newest_includes_earlier_burst_and_no_later(self):
		self._doc(matn="bir", holat="Javobsiz", vaqt="2026-11-17 10:00:00")
		self._doc(matn="ikki", holat="Javobsiz", vaqt="2026-11-17 10:00:10")
		cur = self._doc(matn="uch", vaqt="2026-11-17 10:00:20")
		self._doc(matn="keyingi", vaqt="2026-11-17 10:05:00")
		self.assertEqual(instagram_dm.history(cur), [{"kim": "Mijoz", "matn": "bir"}, {"kim": "Mijoz", "matn": "ikki"}])
		first = frappe.get_all("Instagram Xabar", filters={"matn": "bir", "shop": self.shop}, pluck="name")[0]
		self.assertNotIn({"kim": "Mijoz", "matn": "keyingi"}, instagram_dm.history(frappe.get_doc("Instagram Xabar", first)))

	def test_dm_operator_pause_rearmed_from_message_older_than_since(self):
		# Redis tozalangan (deploy): operator 3 soat oldin yozgan, since — 15 daqiqa oldin
		since = int(time.time()) - 15 * 60
		res, _ = self._fetch(_conv(_msg("m1", CUST, "yana savol", _iso(60)), _msg("op", IG, "men yozaman", _iso(3 * 3600)),
			updated=_iso(60)), since=since)
		self.assertEqual([m["id"] for m in res], ["m1"])
		self.assertTrue(instagram_dm.is_human_paused(self.shop, CUST))
		self.assertTrue(21 * 3600 - 120 <= self._ttl() <= 21 * 3600 + 5, self._ttl())

	def test_dm_operator_message_25h_old_not_armed(self):
		since = int(time.time()) - 15 * 60
		self._fetch(_conv(_msg("m1", CUST, "salom", _iso(60)), _msg("op", IG, "eski", _iso(25 * 3600)),
			updated=_iso(60)), since=since)
		self.assertFalse(instagram_dm.is_human_paused(self.shop, CUST))

	def test_dm_pause_ttl_from_newest_operator_message(self):
		since = int(time.time()) - 15 * 60
		self._fetch(_conv(_msg("m1", CUST, "x", _iso(60)), _msg("op2", IG, "ikkinchi", _iso(3600)),
			_msg("op1", IG, "birinchi", _iso(10 * 3600)), updated=_iso(60)), since=since)
		self.assertTrue(23 * 3600 - 120 <= self._ttl() <= 23 * 3600 + 5, self._ttl())

	def test_human_pause_keys_survive_clear_cache(self):
		self.assertIn("mp_ig_human:*", frappe.get_hooks("persistent_cache_keys"))
		frappe.cache.set_value(self.key, 1, expires_in_sec=60)
		kept = set()
		for pattern in frappe.get_hooks("persistent_cache_keys"):
			kept.update(frappe.cache.get_keys(pattern))
		self.assertIn(frappe.cache.make_key(self.key), kept)


class TestDirectFromComment(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")

	def tearDown(self):
		frappe.db.rollback()

	def _izoh(self, **kw):
		vals = {"doctype": "Instagram Xabar", "shop": self.shop, "turi": "Izoh", "holat": "Yuborildi",
			"tashqi_id": f"pr-{frappe.generate_hash(length=8)}", "username": "ali_77", "matn": "+",
			"direct_javob": "Assalomu alaykum! Batafsil:  narxi 490 000 so'm.", "direct_id": "MID-1"}
		vals.update(kw)
		return frappe.get_doc(vals).insert(ignore_permissions=True)

	def test_private_reply_is_ours_by_id_and_text(self):
		from marketplace.sotuv import instagram_dm

		self._izoh()
		self.assertTrue(instagram_dm._is_ours(self.shop, "cust9", {"id": "MID-1", "text": "x"}))
		self.assertTrue(instagram_dm._is_ours(self.shop, "cust9", {"id": "other", "text": "Assalomu alaykum! Batafsil: narxi 490 000 so'm."}))
		self.assertFalse(instagram_dm._is_ours(self.shop, "cust9", {"id": "other", "text": "Operator yozdi"}))

	def test_history_starts_with_comment_and_private_reply(self):
		from marketplace.sotuv import instagram_dm

		self._izoh()
		dm = frappe.get_doc({"doctype": "Instagram Xabar", "shop": self.shop, "turi": "DM", "holat": "Yangi",
			"tashqi_id": f"dm-{frappe.generate_hash(length=8)}", "username": "ali_77", "mijoz_id": "cust9",
			"matn": "Qanday buyurtma beraman?"}).insert(ignore_permissions=True)
		h = instagram_dm.history(dm)
		self.assertEqual(h[0], {"kim": "Mijoz", "matn": "(izoh) +"})
		self.assertEqual(h[1]["kim"], "Do'kon")
