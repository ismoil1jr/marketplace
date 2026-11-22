"""Tovar murojaati chati: mijoz (sayt) va sotuv menejeri (Desk). Local'dagi nafis-tekstil do'koni bilan."""

import io
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.datastructures import FileStorage

from marketplace.sotuv import tovar_chat as tc

SHOP = "nafis-tekstil"
SELLER = "sotuv-manager@gmail.com"
COURIER = "kuryer.nafis@test.uz"


def _png(size=(2400, 1200)):
	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGBA", size, (255, 0, 0, 128)).save(buf, "PNG")
	buf.seek(0)
	return FileStorage(stream=buf, filename="rasm.png", content_type="image/png")


class TestTovarChat(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Shop", SHOP):
			self.skipTest("nafis-tekstil do'koni yo'q")
		from marketplace.customers import get_or_create_customer

		frappe.set_user("Administrator")
		self.item = frappe.get_all("Item", filters={"shop": SHOP, "is_published": 1, "disabled": 0, "variant_of": ["is", "not set"]},
		                           pluck="name", limit=1)[0]
		self.c1 = frappe._dict(customer=get_or_create_customer("+998901110001", "Sinov", "Bir", shop=SHOP), phone="+998901110001", name="Sinov Bir")
		self.c2 = frappe._dict(customer=get_or_create_customer("+998901110002", "Sinov", "Ikki", shop=SHOP), phone="+998901110002", name="Sinov Ikki")
		# Sinov mijozlarining oldingi chatlari (avvalgi yurishdan qolgan bo'lsa) — toza boshlanadi
		old = frappe.get_all(tc.TM, filters={"customer": ["in", [self.c1.customer, self.c2.customer]]}, pluck="name")
		if old:
			frappe.db.delete(tc.XABAR, {"murojaat": ["in", old]})
			frappe.db.delete(tc.TM, {"name": ["in", old]})
		self.addCleanup(frappe.db.rollback)
		for target in ("frappe.enqueue", "frappe.publish_realtime"):
			p = patch(target)
			setattr(self, target.split(".")[-1], p.start())
			self.addCleanup(p.stop)
		self._who = None
		self.addCleanup(lambda: self._who and self._who.stop())
		self.as_customer(self.c1)

	def _switch(self, customer):
		if self._who:
			self._who.stop()
		self._who = patch("marketplace.customers.current_customer", return_value=customer)
		self._who.start()

	def as_customer(self, c):
		frappe.set_user("Guest")
		self._switch(c)

	def as_seller(self, user=SELLER):
		frappe.set_user(user)
		self._switch(None)

	def send(self, **kw):
		return tc.mijoz_yuborish(SHOP, self.item, **kw)

	def test_first_message_creates_thread_with_product_card(self):
		r = self.send(client_id="a1", matn="  Salom, bu bormi?  ")
		thread = frappe.get_doc(tc.TM, r["thread"])
		self.assertEqual((thread.shop, thread.tovar, thread.customer), (SHOP, self.item, self.c1.customer))
		self.assertEqual(tc.customer_threads(self.c1.customer, SHOP)[0].oxirgi_xabar, "Salom, bu bormi?")
		kinds = frappe.get_all(tc.XABAR, filters={"murojaat": thread.name}, pluck="turi", order_by="creation asc")
		self.assertEqual(kinds, ["Tovar", "Matn"])
		self.assertTrue(r["message"]["mine"])
		# Do'konga: qo'ng'iroqcha + Telegram; kuryerga — yo'q
		users = {c.kwargs.get("user") for c in self.publish_realtime.call_args_list}
		self.assertIn(SELLER, users)
		self.assertNotIn(COURIER, users)
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": SELLER, "document_name": thread.name}))
		self.assertEqual(self.enqueue.call_args.args[0], "marketplace.sotuv.tovar_chat.notify_telegram")

	def test_retry_with_same_client_id_does_not_duplicate(self):
		a = self.send(client_id="same", matn="Salom")
		b = self.send(client_id="same", matn="Salom")
		self.assertEqual(a["message"]["id"], b["message"]["id"])
		self.assertEqual(frappe.db.count(tc.XABAR, {"murojaat": a["thread"], "turi": "Matn"}), 1)

	def test_parallel_first_messages_do_not_create_two_threads(self):
		"""Rasm va matn bir vaqtda «birinchi xabar» bo'lib kelsa: ikkinchi so'rov chatni hali ko'rmagan (eski o'qish),
		lekin qulf ostida qayta tekshiradi — ikkinchi chat yaratilmaydi."""
		first = self.send(client_id="p1", matn="Rasm")
		real = tc.find_thread
		calls = []

		def stale_then_real(*a):
			calls.append(a)
			return None if len(calls) == 1 else real(*a)

		with patch.object(tc, "find_thread", side_effect=stale_then_real):
			second = self.send(client_id="p2", matn="Matn")
		self.assertEqual(second["thread"], first["thread"])
		self.assertEqual(frappe.db.count(tc.TM, {"customer": self.c1.customer, "tovar": self.item}), 1)
		self.assertEqual(frappe.db.count(tc.XABAR, {"murojaat": first["thread"], "turi": "Tovar"}), 1)

	def test_product_card_cannot_be_edited_or_deleted(self):
		r = self.send(matn="Salom")
		card = frappe.db.get_value(tc.XABAR, {"murojaat": r["thread"], "turi": "Tovar"})
		with self.assertRaises(frappe.PermissionError):
			tc.mijoz_ochirish(card)
		with self.assertRaises(frappe.PermissionError):
			tc.mijoz_tahrirlash(card, "boshqa")

	def test_read_receipts_both_ways(self):
		r = self.send(matn="Rangi bormi?")
		self.as_seller()
		opened = tc.ochish(r["thread"])
		self.assertFalse(opened["messages"][-1]["mine"])
		reply = tc.yuborish(r["thread"], client_id="s1", matn="Ha, bor")["message"]
		self.assertFalse(reply["oqilgan"])
		self.as_customer(self.c1)
		since = tc.mijoz_ochish(SHOP, self.item, oqidi=0)
		mine = [m for m in since["messages"] if m["turi"] == "Matn" and m["mine"]]
		self.assertTrue(mine[0]["oqilgan"])  # menejer ochdi — mijozda ✓✓
		self.assertEqual(tc.customer_unread(self.c1.customer, SHOP), 1)
		tc.mijoz_ochish(SHOP, self.item)  # mijoz ko'rdi
		self.assertEqual(tc.customer_unread(self.c1.customer, SHOP), 0)
		self.as_seller()
		changed = tc.ochish(r["thread"], since=opened["since"], oqidi=0)["messages"]
		self.assertTrue(next(m for m in changed if m["id"] == reply["id"])["oqilgan"])

	def test_edit_and_delete_own_message_only(self):
		r = self.send(matn="Salom")
		mid = r["message"]["id"]
		edited = tc.mijoz_tahrirlash(mid, "Assalomu alaykum")
		self.assertTrue(edited["tahrirlangan"])
		self.assertEqual(tc.customer_threads(self.c1.customer, SHOP)[0].oxirgi_xabar, "Assalomu alaykum")
		self.as_seller()
		with self.assertRaises(frappe.PermissionError):
			tc.tahrirlash(mid, "menejer o'zgartirdi")
		self.as_customer(self.c1)
		before = tc.mijoz_ochish(SHOP, self.item)["since"]
		tc.mijoz_ochirish(mid)
		self.assertNotIn(mid, [m["id"] for m in tc.mijoz_ochish(SHOP, self.item)["messages"]])
		gone = next(m for m in tc.mijoz_ochish(SHOP, self.item, since=before)["messages"] if m["id"] == mid)
		self.assertTrue(gone["ochirilgan"])
		self.assertIsNone(gone["matn"])
		self.assertEqual(tc.customer_threads(self.c1.customer, SHOP)[0].oxirgi_xabar, "Tovar bo‘yicha murojaat")

	def test_other_customer_cannot_touch_thread(self):
		r = self.send(matn="Salom")
		self.as_customer(self.c2)
		self.assertIsNone(tc.mijoz_ochish(SHOP, self.item)["thread"])  # o'z chati — hali yo'q
		with self.assertRaises(frappe.DoesNotExistError):
			tc.mijoz_ochirish(r["message"]["id"])

	def test_sticker_and_image(self):
		with self.assertRaises(frappe.ValidationError):
			self.send(turi="Stiker", stiker="<script>")
		self.assertEqual(self.send(turi="Stiker", stiker="👍")["message"]["stiker"], "👍")
		with patch.object(tc, "_request_file", return_value=_png()):
			msg = self.send(turi="Rasm")["message"]
		self.assertTrue(msg["rasm"].startswith("/api/method/marketplace.sotuv.tovar_chat.rasm"))
		f = frappe.get_doc("File", {"attached_to_doctype": tc.XABAR, "attached_to_name": msg["id"]})
		self.assertTrue(f.is_private)
		from PIL import Image

		im = Image.open(io.BytesIO(f.get_content(encodings=[])))
		self.assertEqual((im.format, max(im.size)), ("JPEG", tc.IMAGE_SIDE))
		# rasm faqat shu chat egalariga
		tc.rasm(msg["id"])
		self.assertEqual(frappe.local.response.display_content_as, "inline")
		self.assertIsInstance(frappe.local.response.filecontent, bytes)  # matnga aylanib buzilmasin
		self.as_customer(self.c2)
		with self.assertRaises(frappe.PermissionError):
			tc.rasm(msg["id"])
		self.as_seller(COURIER)
		with self.assertRaises(frappe.PermissionError):
			tc.rasm(msg["id"])

	def test_not_an_image_is_rejected(self):
		bad = FileStorage(stream=io.BytesIO(b"not an image"), filename="x.png")
		with patch.object(tc, "_request_file", return_value=bad), self.assertRaises(frappe.ValidationError):
			self.send(turi="Rasm")

	def test_item_of_another_shop_is_rejected(self):
		other = frappe.get_all("Item", filters={"shop": ["!=", SHOP], "is_published": 1}, pluck="name", limit=1)
		if not other:
			self.skipTest("boshqa do'kon tovari yo'q")
		with self.assertRaises(frappe.DoesNotExistError):
			tc.mijoz_yuborish(SHOP, other[0], matn="Salom")

	def test_seller_list_and_new_count(self):
		r = self.send(matn="Salom")
		self.as_seller()
		data = tc.royxat()
		row = next(x for x in data["rows"] if x.name == r["thread"])
		self.assertEqual((row.unread, row.mijoz_ismi), (1, "Sinov Bir"))
		self.assertGreaterEqual(data["yangi"], 1)
		tc.ochish(r["thread"])
		self.assertEqual(next(x for x in tc.royxat()["rows"] if x.name == r["thread"]).unread, 0)

	def test_customer_threads_for_profile(self):
		r = self.send(matn="Salom")
		rows = tc.customer_threads(self.c1.customer, SHOP)
		self.assertEqual(rows[0].name, r["thread"])
		self.assertEqual(rows[0].url, f"/s/{SHOP}/chat/{self.item}")
