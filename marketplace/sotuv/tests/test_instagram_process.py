from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import instagram
from marketplace.sotuv.ig_ai import IgAiError
from marketplace.sotuv.meta import MetaError

AI_OK = {"javob_kerak": True, "javob": "Salom, narxi 100 000", "til": "uz", "telefon": None,
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
		self.assertEqual(data["izoh"], "Izoh: narxi qancha?")
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
