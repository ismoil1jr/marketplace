import json
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram, instagram_dm
from marketplace.sotuv.meta import MetaError

IG, CUST, SINCE = "ig1", "cust1", 1000
CREATED = "2026-11-17T04:19:10+0000"  # > SINCE
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

	def _fetch(self, graph_data):
		fake = {"meta_page_id": "PG", "ig_user_id": IG}
		with patch.object(instagram, "_shop", side_effect=lambda s, f: fake.get(f, "")), \
			patch.object(instagram_dm, "_page_token", return_value="tok"), \
			patch.object(instagram_dm, "_graph", return_value=graph_data) as g:
			res = instagram_dm.fetch_messages(self.shop, SINCE)
		return res, g

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
			patch.object(instagram, "_status") as stat, \
			patch.object(instagram.frappe, "enqueue") as enq, \
			patch.object(instagram.frappe.db, "commit"):
			instagram.poll()
		enq.assert_called_once()
		stat.assert_called_once()
		self.assertTrue(int(frappe.cache.get_value("mp_ig_since:Test Shop Dm")) > 0)
