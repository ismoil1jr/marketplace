from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram
from marketplace.sotuv.ig_ai import IgAiError
from marketplace.sotuv.meta import MetaError

AI_OK = {"javob_kerak": True, "javob": "Assalomu alaykum! Narxi 100 000 so'm.", "til": "uz", "telefon": None,
	"ism": None, "tovar_kodi": None, "model": "m"}


def _ai(**kw):
	return {**AI_OK, **kw}


class TestInstagramProcess(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")
		self.n = 0
		# commit'ni o'chiramiz: tearDown rollback dev bazani toza qoldiradi
		p = patch.object(frappe.db, "commit")
		p.start()
		self.addCleanup(p.stop)

	def tearDown(self):
		frappe.db.rollback()

	def _doc(self, **kw):
		self.n += 1
		vals = {"doctype": "Instagram Xabar", "shop": self.shop, "turi": "Izoh", "holat": "Yangi",
			"tashqi_id": f"t4-{frappe.generate_hash(length=8)}-{self.n}", "mijoz_id": "cust1",
			"username": "ali", "matn": "narxi qancha?"}
		vals.update(kw)
		return frappe.get_doc(vals).insert(ignore_permissions=True)

	def _run(self, doc, rejim="Yoqilgan", ai=None, lead=None):
		graph = patch.object(instagram, "_graph", return_value={"id": "R1"})
		with patch.object(instagram, "_shop", return_value=rejim), \
			patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram.ig_ai, "answer", **({"side_effect": ai} if isinstance(ai, Exception) else {"return_value": ai or _ai()})), \
			patch.object(instagram, "save_lead", return_value=lead or ("MUR-1", False)) as sl, \
			graph as g:
			res = instagram.process(doc.name)
		doc.reload()
		return res, g, sl

	def test_process_sinov_never_posts(self):
		doc = self._doc()
		res, g, _ = self._run(doc, "Sinov")
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertEqual(doc.ai_javob, AI_OK["javob"])
		g.assert_not_called()

	def test_process_ochiq_leaves_yangi(self):
		doc = self._doc()
		res, g, _ = self._run(doc, "O'chiq")
		self.assertEqual((res, doc.holat), ("Yangi", "Yangi"))
		g.assert_not_called()

	def test_process_yoqilgan_posts_reply(self):
		doc = self._doc()
		res, g, _ = self._run(doc)
		self.assertEqual((res, doc.holat, doc.javob_id), ("Yuborildi", "Yuborildi", "R1"))
		g.assert_called_once()
		self.assertEqual(g.call_args.args[:2], ("POST", f"{doc.tashqi_id}/replies"))
		self.assertEqual(g.call_args.kwargs["message"], AI_OK["javob"])

	def test_process_passes_post_text_to_ai(self):
		doc = self._doc(post_matni="Atomic Habits")
		with patch.object(instagram, "_shop", return_value="Sinov"), \
			patch.object(instagram.ig_ai, "answer", return_value=_ai()) as ai:
			instagram.process(doc.name)
		self.assertEqual(ai.call_args.kwargs["post_matni"], "Atomic Habits")

	def test_process_gate_no_greeting_keeps_draft(self):
		doc = self._doc()
		res, g, sl = self._run(doc, ai=_ai(javob="Narxi 100 000", telefon="998901234567"))
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("salomlashuv", doc.xato)
		self.assertEqual(doc.ai_javob, "Narxi 100 000")
		g.assert_not_called()
		sl.assert_called_once()  # lid baribir yoziladi

	def test_process_gate_url_in_comment_keeps_draft(self):
		doc = self._doc()
		res, g, _ = self._run(doc, ai=_ai(javob="Assalomu alaykum! Batafsil: https://t.me/x"))
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("havola", doc.xato)
		g.assert_not_called()

	def test_process_gate_not_applied_in_sinov(self):
		doc = self._doc()
		res, g, _ = self._run(doc, "Sinov", ai=_ai(javob="Narxi 100 000"))
		self.assertEqual((res, doc.holat, doc.xato), ("Qoralama", "Qoralama", ""))

	def test_send_manual_bypasses_gate(self):
		doc = self._doc(holat="Qoralama", ai_javob="Narxi 100 000", xato="Javob salomlashuv bilan boshlanmagan")
		with patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_graph", return_value={"id": "R7"}) as g:
			instagram.send(doc.name)
		doc.reload()
		self.assertEqual(doc.holat, "Yuborildi")
		g.assert_called_once()

	def test_regenerate_refuses_when_locked_read_says_sent(self):
		doc = self._doc(holat="Qoralama", ai_javob="x")
		real = frappe.db.get_value

		def gv(*a, **kw):
			if kw.get("for_update"):
				return "Yuborildi"
			return real(*a, **kw)

		with patch.object(frappe.db, "get_value", side_effect=gv) as gvm, \
			patch.object(instagram.ig_ai, "answer") as ai:
			with self.assertRaises(frappe.ValidationError):
				instagram.regenerate(doc.name)
		ai.assert_not_called()
		self.assertTrue(any(c.kwargs.get("for_update") for c in gvm.call_args_list))

	def test_hourly_limit_falls_back_to_username(self):
		for _ in range(instagram.MAX_PER_HOUR):
			self._doc(holat="Yuborildi", mijoz_id="", username="vali")
		doc = self._doc(mijoz_id="", username="vali")
		res, g, _ = self._run(doc)
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("soatlik limit", doc.xato)
		g.assert_not_called()

	def test_hourly_limit_no_id_no_username_is_unique(self):
		for _ in range(instagram.MAX_PER_HOUR):
			self._doc(holat="Yuborildi", mijoz_id="", username="")
		doc = self._doc(mijoz_id="", username="")
		res, g, _ = self._run(doc)
		self.assertEqual(res, "Yuborildi")
		g.assert_called_once()

	def test_lead_id_falls_back_to_username_then_name(self):
		doc = self._doc(mijoz_id="", username="vali")
		_, _, sl = self._run(doc, "Sinov", ai=_ai(telefon="998901234567"))
		self.assertTrue(sl.call_args.args[1]["lead_id"].startswith("ig:vali:"))
		doc2 = self._doc(mijoz_id="", username="")
		_, _, sl2 = self._run(doc2, "Sinov", ai=_ai(telefon="998901234567"))
		self.assertTrue(sl2.call_args.args[1]["lead_id"].startswith(f"ig:{doc2.name}:"))

	def test_reply_to_reply_without_username_has_no_at(self):
		doc = self._doc(ota_id="P1", username="")
		_, g, _ = self._run(doc)
		self.assertEqual(g.call_args.kwargs["message"], AI_OK["javob"])

	def test_shop_hourly_cap_keeps_draft(self):
		doc = self._doc()
		with patch.object(instagram, "_shop_hourly_count", return_value=instagram.SHOP_MAX_PER_HOUR):
			res, g, _ = self._run(doc)
		self.assertEqual((res, doc.holat, doc.xato), ("Qoralama", "Qoralama", "do'kon soatlik limiti"))
		g.assert_not_called()

	def test_shop_hourly_cap_counts_sent_comments(self):
		with patch.object(instagram.frappe.db, "count", return_value=3) as cnt:
			self.assertEqual(instagram._shop_hourly_count(self.shop), 3)
		f = cnt.call_args.args[1]
		self.assertEqual((f["shop"], f["turi"], f["holat"]), (self.shop, "Izoh", "Yuborildi"))
		self.assertEqual(f["modified"][0], ">")

	def test_shop_hourly_cap_not_for_dm(self):
		doc = self._doc(turi="DM")
		with patch.object(instagram, "_shop_hourly_count", return_value=10**6), \
			patch.object(instagram.instagram_dm, "is_human_paused", return_value=False), \
			patch.object(instagram.instagram_dm, "history", return_value=[]), \
			patch.object(instagram.instagram_dm, "send_dm", return_value="MID") as sd:
			res, _, _ = self._run(doc)
		self.assertEqual(res, "Yuborildi")
		sd.assert_called_once()

	def test_process_not_yangi_is_noop(self):
		doc = self._doc(holat="Yuborildi")
		res, g, _ = self._run(doc)
		self.assertEqual(res, "Yuborildi")
		g.assert_not_called()

	def test_process_reply_to_reply_targets_parent(self):
		doc = self._doc(ota_id="P1", username="ali")
		_, g, _ = self._run(doc)
		self.assertEqual(g.call_args.args[1], "P1/replies")
		self.assertTrue(g.call_args.kwargs["message"].startswith("@ali "))

	def test_process_javobsiz(self):
		doc = self._doc()
		res, g, _ = self._run(doc, ai=_ai(javob_kerak=False, javob=""))
		self.assertEqual((res, doc.holat), ("Javobsiz", "Javobsiz"))
		g.assert_not_called()

	def test_process_rate_limit_per_customer(self):
		for _ in range(instagram.MAX_PER_HOUR):
			self._doc(holat="Yuborildi")
		doc = self._doc()
		res, g, _ = self._run(doc)
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("soatlik limit", doc.xato)
		g.assert_not_called()

	def test_process_phone_creates_lead(self):
		doc = self._doc()
		_, _, sl = self._run(doc, ai=_ai(telefon="998901234567", ism="Ali", tovar_kodi="X1"))
		self.assertEqual(doc.murojaat, "MUR-1")
		shop, data, asked = sl.call_args.args
		self.assertEqual(data["manba"], "Instagram")
		self.assertEqual(data["izoh"], "Instagram: @ali\nIzoh: narxi qancha?")
		self.assertTrue(data["lead_id"].startswith("ig:cust1:"))
		self.assertEqual(asked, "X1")

	def test_process_ai_error_marks_xato(self):
		doc = self._doc()
		res, g, _ = self._run(doc, ai=IgAiError("kvota", pause=True))
		self.assertEqual((res, doc.holat), ("Xato", "Xato"))
		self.assertTrue(doc.xato)
		g.assert_not_called()
		self.assertTrue(frappe.cache.get_value("mp_ig_ai_pause"))
		frappe.cache.delete_value("mp_ig_ai_pause")

	def test_send_only_from_draft(self):
		doc = self._doc(holat="Yuborildi", ai_javob="x")
		with self.assertRaises(frappe.ValidationError):
			instagram.send(doc.name)

	def test_send_posts_draft(self):
		doc = self._doc(holat="Qoralama", ai_javob="Salom")
		with patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_graph", return_value={"id": "R9"}) as g:
			instagram.send(doc.name)
		doc.reload()
		self.assertEqual((doc.holat, doc.javob_id), ("Yuborildi", "R9"))
		g.assert_called_once()

	def test_regenerate_always_draft(self):
		doc = self._doc(holat="Xato")
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram.ig_ai, "answer", return_value=_ai(javob="Yangi")), \
			patch.object(instagram, "_graph") as g:
			instagram.regenerate(doc.name)
		doc.reload()
		self.assertEqual((doc.holat, doc.ai_javob), ("Qoralama", "Yangi"))
		g.assert_not_called()

	def test_send_meta_error_keeps_xato(self):
		doc = self._doc(holat="Qoralama", ai_javob="Salom")
		with patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_graph", side_effect=MetaError("rad", 100)):
			with self.assertRaises(frappe.ValidationError):
				instagram.send(doc.name)
		doc.reload()
		self.assertEqual(doc.holat, "Xato")
		self.assertTrue(doc.xato)

	def test_process_blank_reply_is_xato(self):
		doc = self._doc()
		res, g, _ = self._run(doc, ai=_ai(javob="  "))
		self.assertEqual((res, doc.holat), ("Xato", "Xato"))
		self.assertEqual(doc.xato, "AI bo'sh javob qaytardi")
		g.assert_not_called()

	def test_commit_follows_post_before_lead(self):
		doc = self._doc()
		order = []
		with patch.object(instagram, "_lead", side_effect=lambda *a: order.append("lead")), \
			patch.object(frappe.db, "commit", side_effect=lambda: order.append("commit")):
			self._run(doc, ai=_ai(telefon="998901234567"))
		self.assertEqual(order, ["commit", "lead"])

	def test_send_second_clicker_sees_locked_state(self):
		doc = self._doc(holat="Qoralama", ai_javob="Salom")
		real = frappe.db.get_value

		def gv(*a, **kw):
			if kw.get("for_update"):
				return frappe._dict(holat="Yuborildi", ai_javob="Salom")
			return real(*a, **kw)

		with patch.object(frappe.db, "get_value", side_effect=gv), \
			patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_graph") as g:
			with self.assertRaises(frappe.ValidationError):
				instagram.send(doc.name)
		g.assert_not_called()


DIRECT = "Assalomu alaykum! Panda Books — gapiradigan ruchkali kitoblar. Narxi 490 000 so'm, yetkazish bepul. Buyurtma uchun ism va telefon raqamingizni yozing."


class TestInstagramPlusToDirect(UnitTestCase):
	"""«+» / batafsil so'rov: avval o'sha izoh egasiga Direct (private reply), keyin izohga qisqa javob."""

	setUp = TestInstagramProcess.setUp
	tearDown = TestInstagramProcess.tearDown
	_doc = TestInstagramProcess._doc
	_run = TestInstagramProcess._run

	def test_plus_sends_private_reply_then_public(self):
		doc = self._doc(matn="+")
		ai = _ai(javob="Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩", direct=DIRECT)
		res, g, _ = self._run(doc, ai=ai)
		self.assertEqual((res, doc.holat), ("Yuborildi", "Yuborildi"))
		self.assertEqual(g.call_count, 2)
		first, second = g.call_args_list
		self.assertTrue(first.args[1].endswith("/messages"))
		self.assertEqual(frappe.parse_json(first.kwargs["recipient"]), {"comment_id": doc.tashqi_id})
		self.assertEqual(frappe.parse_json(first.kwargs["message"]), {"text": DIRECT})
		self.assertEqual(second.args[1], f"{doc.tashqi_id}/replies")
		self.assertEqual(doc.direct_javob, DIRECT)
		self.assertTrue(doc.direct_id)

	def test_private_reply_failure_no_public_reply(self):
		doc = self._doc(matn="+")
		ai = _ai(javob="Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩", direct=DIRECT)
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram.ig_ai, "answer", return_value=ai), \
			patch.object(instagram, "_graph", side_effect=MetaError("no messaging", 10)) as g:
			res = instagram.process(doc.name)
		doc.reload()
		self.assertEqual((res, doc.holat), ("Xato", "Xato"))
		self.assertIn("Direct", doc.xato)
		g.assert_called_once()  # izohga «Direct'ga yubordik» deb yozilmadi

	def test_direct_text_goes_through_gate(self):
		doc = self._doc(matn="+")
		ai = _ai(javob="Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩",
			direct="Assalomu alaykum! Arzonrog'i @raqib_shop sahifasida.")
		res, g, _ = self._run(doc, ai=ai)
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("Direct", doc.xato)
		g.assert_not_called()

	def test_sinov_keeps_direct_as_draft(self):
		doc = self._doc(matn="+")
		ai = _ai(javob="Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩", direct=DIRECT)
		res, g, _ = self._run(doc, "Sinov", ai=ai)
		self.assertEqual((res, doc.direct_javob), ("Qoralama", DIRECT))
		g.assert_not_called()

	def test_send_delivers_pending_direct_once(self):
		doc = self._doc(matn="+", holat="Qoralama", ai_javob="Assalomu alaykum! Direct'ga yubordik 📩", direct_javob=DIRECT)
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_graph", return_value={"id": "R1", "message_id": "M1"}) as g:
			instagram.send(doc.name)
		doc.reload()
		self.assertEqual(doc.holat, "Yuborildi")
		self.assertEqual(g.call_count, 2)
		self.assertEqual(doc.direct_id, "M1")

	def test_lead_has_username_and_name(self):
		doc = self._doc(matn="ismim Ali, 90 123 45 67", username="ali_77")
		_res, _g, sl = self._run(doc, ai=_ai(telefon="998901234567", ism="Ali"))
		data = sl.call_args.args[1]
		self.assertEqual(data["ism"], "Ali")
		self.assertIn("@ali_77", data["izoh"])

	def test_lead_without_name_uses_username(self):
		doc = self._doc(matn="90 123 45 67", username="ali_77")
		_res, _g, sl = self._run(doc, ai=_ai(telefon="998901234567"))
		self.assertEqual(sl.call_args.args[1]["ism"], "@ali_77")


class TestPlusDirectSafety(UnitTestCase):
	setUp = TestInstagramProcess.setUp
	tearDown = TestInstagramProcess.tearDown
	_doc = TestInstagramProcess._doc
	_run = TestInstagramProcess._run

	PUBLIC = "Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩"

	def test_promised_direct_without_text_is_draft(self):
		doc = self._doc(matn="+")
		res, g, _ = self._run(doc, ai=_ai(javob=self.PUBLIC, direct=None))
		self.assertEqual((res, doc.holat), ("Qoralama", "Qoralama"))
		self.assertIn("Direct", doc.xato)
		g.assert_not_called()

	def test_reply_comment_gets_no_direct(self):
		doc = self._doc(matn="+", ota_id="P1")
		res, g, _ = self._run(doc, ai=_ai(javob=self.PUBLIC, direct=DIRECT))
		self.assertEqual(res, "Qoralama")  # «yubordik» va'dasi bor, lekin javob ostidagi izohga Direct yo'q
		g.assert_not_called()

	def test_long_ordinary_question_gets_no_direct(self):
		doc = self._doc(matn="Assalomu alaykum, kitoblar necha yoshdagi bolalarga mos va ruchka zaryadi qancha vaqt ishlaydi?")
		res, g, _ = self._run(doc, ai=_ai(direct=DIRECT))
		self.assertEqual((res, doc.holat), ("Yuborildi", "Yuborildi"))
		g.assert_called_once()  # faqat ochiq javob
		self.assertFalse(doc.direct_javob)

	def test_direct_hourly_cap(self):
		for i in range(instagram.DIRECT_MAX_PER_HOUR):
			self._doc(matn="+", holat="Yuborildi", direct_id=f"D{i}", mijoz_id=f"c{i}")
		doc = self._doc(matn="+", mijoz_id="new")
		res, g, _ = self._run(doc, ai=_ai(javob=self.PUBLIC, direct=DIRECT))
		self.assertEqual(res, "Qoralama")
		self.assertIn("Direct", doc.xato)
		g.assert_not_called()

	def test_send_stops_if_other_click_finished_after_direct(self):
		doc = self._doc(matn="+", holat="Qoralama", ai_javob=self.PUBLIC, direct_javob=DIRECT)
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram, "_page_token", return_value="tok"), \
			patch.object(instagram, "_still", return_value=False), \
			patch.object(instagram, "_graph", return_value={"id": "R1", "message_id": "M1"}) as g:
			instagram.send(doc.name)
		self.assertEqual(g.call_count, 1)  # Direct ketdi, ochiq javobni ikkinchi bosuvchi allaqachon yozgan

	def test_rerun_keeps_sent_direct_text(self):
		doc = self._doc(matn="+", holat="Qoralama", ai_javob=self.PUBLIC, direct_javob=DIRECT, direct_id="M1")
		with patch.object(instagram, "_shop", return_value="Sinov"), \
			patch.object(instagram.ig_ai, "answer", return_value=_ai(javob=self.PUBLIC, direct="Boshqa matn")):
			instagram.regenerate(doc.name)
		doc.reload()
		self.assertEqual(doc.direct_javob, DIRECT)


class TestPromisedRegex(UnitTestCase):
	def test_only_sent_promise_matches(self):
		yes = ("Assalomu alaykum! Batafsil ma'lumotni Direct'ga yubordik 📩", "Assalomu alaykum! Direct'ga yubordim.",
			"Здравствуйте! Подробности отправили в Direct.", "Здравствуйте! Отправили вам в директ.")
		no = ("Assalomu alaykum! Narxini menejerimiz Direct'da aniqlab beradi.", "Assalomu alaykum! Direct'ga yozing.",
			"Assalomu alaykum! Ism va raqamingizni Direct'ga yuboring.", "Assalomu alaykum! Ha, bor.")
		for t in yes:
			self.assertTrue(instagram._PROMISED.search(t), t)
		for t in no:
			self.assertFalse(instagram._PROMISED.search(t), t)


class TestTrivialSkipsAi(UnitTestCase):
	setUp = TestInstagramProcess.setUp
	tearDown = TestInstagramProcess.tearDown
	_doc = TestInstagramProcess._doc

	def test_emoji_comment_no_ai_call(self):
		doc = self._doc(matn="😍😍")
		with patch.object(instagram, "_shop", return_value="Yoqilgan"), \
			patch.object(instagram.ig_ai, "answer") as ai, \
			patch.object(instagram, "_graph") as g:
			res = instagram.process(doc.name)
		doc.reload()
		self.assertEqual((res, doc.holat), ("Javobsiz", "Javobsiz"))
		ai.assert_not_called()
		g.assert_not_called()
