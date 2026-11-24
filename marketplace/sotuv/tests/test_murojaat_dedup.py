import frappe
from frappe.tests import UnitTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime, today

from marketplace.sotuv import murojaat as m

PHONE = "998330740490"


def _shop():
	return frappe.db.get_value("Shop", {}, "name")


def _lead(shop, holat="Yangi", tovar=None, ago_min=60, **extra):
	doc = frappe.get_doc({
		"doctype": "Murojaat", "shop": shop, "mijoz_ismi": "Test", "telefon": "+998 33 074 04 90",
		"normal_telefon": PHONE, "holat": holat, "tovar": tovar, "manba": "Instagram", **extra,
	}).insert(ignore_permissions=True)
	frappe.db.set_value("Murojaat", doc.name, "creation", add_to_date(now_datetime(), minutes=-ago_min), update_modified=False)
	return doc.name


class TestMurojaatDedup(UnitTestCase):
	def setUp(self):
		self.shop = _shop()
		if not self.shop:
			self.skipTest("Shop yo'q")
		frappe.db.delete("Murojaat", {"normal_telefon": PHONE})

	def tearDown(self):
		frappe.db.rollback()
		frappe.cache.delete_keys("mp_lead_seen:")

	def test_repeat_bumps_date_once_per_lead(self):
		first = _lead(self.shop, holat="Keyinroq", keyingi_qongiroq=add_days(today(), 5), tashqi_id="A")
		data = {"telefon": "+998 33 074 04 90", "lead_id": "l:B"}
		m.save_lead(self.shop, data)
		self.assertEqual(getdate(frappe.db.get_value("Murojaat", first, "keyingi_qongiroq")), getdate(today()))
		# menejer qayta qo'ng'iroqni yana 5 kunga qo'ydi — Meta o'sha lidni 10 daqiqadan keyin qayta yuboradi
		frappe.db.set_value("Murojaat", first, "keyingi_qongiroq", add_days(today(), 5), update_modified=False)
		m.save_lead(self.shop, data)
		self.assertEqual(getdate(frappe.db.get_value("Murojaat", first, "keyingi_qongiroq")), getdate(add_days(today(), 5)))
		self.assertEqual(frappe.db.get_value("Murojaat", first, "tashqi_id"), "A")

	def test_sync_skips_buyurtma_berdi(self):
		a = _lead(self.shop, holat="Yangi", ago_min=120)
		b = _lead(self.shop, holat="Yangi", ago_min=60)
		frappe.db.set_value("Murojaat", a, "holat", "Buyurtma berdi", update_modified=False)
		m._sync_duplicates(frappe.get_doc("Murojaat", a))
		self.assertEqual(frappe.db.get_value("Murojaat", b, "holat"), "Yangi")

	def test_sync_requires_same_tovar(self):
		items = frappe.get_all("Item", filters={"shop": self.shop, "disabled": 0}, pluck="name", limit=1)
		if not items:
			self.skipTest("Do'konda tovar yo'q")
		a = _lead(self.shop, holat="Yangi", ago_min=120)
		b = _lead(self.shop, holat="Yangi", tovar=items[0], ago_min=60)
		frappe.db.set_value("Murojaat", a, "holat", "Olmaydi", update_modified=False)
		m._sync_duplicates(frappe.get_doc("Murojaat", a))
		self.assertEqual(frappe.db.get_value("Murojaat", b, "holat"), "Yangi")

	def test_patch_skips_olmaydi(self):
		from marketplace.patches import murojaat_takror_holat

		first = _lead(self.shop, holat="Olmaydi", ago_min=120)
		frappe.get_doc({
			"doctype": "Menejer Xulosasi", "murojaat": first, "telefon": "+998 33 074 04 90", "shop": self.shop,
			"kanal": "Qo‘ng‘iroq", "natija": "Olmaydi", "menejer": "Administrator",
		}).insert(ignore_permissions=True)
		new = _lead(self.shop, holat="Yangi", ago_min=60)
		murojaat_takror_holat.execute()
		self.assertEqual(frappe.db.get_value("Murojaat", new, "holat"), "Yangi")

	def test_patch_ignores_later_leads(self):
		from marketplace.patches import murojaat_takror_holat

		row = _lead(self.shop, holat="Yangi", ago_min=120)
		later = _lead(self.shop, holat="Keyinroq", ago_min=60)
		frappe.get_doc({
			"doctype": "Menejer Xulosasi", "murojaat": later, "telefon": "+998 33 074 04 90", "shop": self.shop,
			"kanal": "Qo‘ng‘iroq", "natija": "Keyinroq", "menejer": "Administrator",
		}).insert(ignore_permissions=True)
		murojaat_takror_holat.execute()
		self.assertEqual(frappe.db.get_value("Murojaat", row, "holat"), "Yangi")

	def _count(self):
		return frappe.db.count("Murojaat", {"shop": self.shop, "normal_telefon": PHONE})

	def test_open_lead_same_phone_not_duplicated(self):
		first = _lead(self.shop, holat="Keyinroq", keyingi_qongiroq=add_days(today(), 5))
		name, dup = m.save_lead(self.shop, {"telefon": "+998 33 074 04 90", "ism": "Nasiba", "lead_id": "l:123"})
		self.assertEqual((name, dup), (first, True))
		self.assertEqual(self._count(), 1)
		row = frappe.db.get_value("Murojaat", first, ["keyingi_qongiroq", "tashqi_id", "holat"], as_dict=True)
		self.assertEqual(getdate(row.keyingi_qongiroq), getdate(today()))
		self.assertEqual(row.tashqi_id, "123")
		self.assertEqual(row.holat, "Keyinroq")

	def test_closed_lead_creates_new(self):
		_lead(self.shop, holat="Olmaydi")
		name, dup = m.save_lead(self.shop, {"telefon": "+998 33 074 04 90", "ism": "Nasiba"})
		self.assertFalse(dup)
		self.assertEqual(self._count(), 2)
		self.assertEqual(frappe.db.get_value("Murojaat", name, "holat"), "Yangi")

	def test_different_tovar_creates_new(self):
		items = frappe.get_all("Item", filters={"shop": self.shop, "disabled": 0}, pluck="name", limit=2)
		if len(items) < 2:
			self.skipTest("Do'konda 2 ta tovar yo'q")
		_lead(self.shop, holat="Keyinroq", tovar=items[0])
		name, dup = m.save_lead(self.shop, {"telefon": "+998 33 074 04 90"}, items[1])
		self.assertFalse(dup)
		self.assertEqual(self._count(), 2)

	def test_result_syncs_open_duplicates(self):
		a = _lead(self.shop, holat="Yangi", ago_min=120)
		b = _lead(self.shop, holat="Yangi", ago_min=60)
		closed = _lead(self.shop, holat="Olmaydi", ago_min=30)
		frappe.db.set_value("Murojaat", a, {"holat": "Keyinroq", "keyingi_qongiroq": add_days(today(), 2),
		                                    "menejer": "Administrator"}, update_modified=False)
		m._sync_duplicates(frappe.get_doc("Murojaat", a))
		row = frappe.db.get_value("Murojaat", b, ["holat", "keyingi_qongiroq", "menejer"], as_dict=True)
		self.assertEqual(row.holat, "Keyinroq")
		self.assertEqual(getdate(row.keyingi_qongiroq), getdate(add_days(today(), 2)))
		self.assertEqual(row.menejer, "Administrator")
		self.assertEqual(frappe.db.get_value("Murojaat", closed, "holat"), "Olmaydi")

	def test_patch_adopts_latest_result_for_yangi_duplicate(self):
		from marketplace.patches import murojaat_takror_holat

		first = _lead(self.shop, holat="Keyinroq", ago_min=120)
		frappe.get_doc({
			"doctype": "Menejer Xulosasi", "murojaat": first, "telefon": "+998 33 074 04 90", "shop": self.shop,
			"kanal": "Qo‘ng‘iroq", "natija": "Keyinroq", "keyingi_qongiroq": today(), "menejer": "Administrator",
		}).insert(ignore_permissions=True)
		dup = _lead(self.shop, holat="Yangi", ago_min=60, izoh="eski izoh")
		murojaat_takror_holat.execute()
		row = frappe.db.get_value("Murojaat", dup, ["holat", "keyingi_qongiroq", "izoh"], as_dict=True)
		self.assertEqual(row.holat, "Keyinroq")
		self.assertEqual(getdate(row.keyingi_qongiroq), getdate(today()))
		self.assertIn("Takroriy murojaat", row.izoh)
		self.assertIn("eski izoh", row.izoh)

	def test_patch_leaves_yangi_without_history(self):
		from marketplace.patches import murojaat_takror_holat

		lone = _lead(self.shop, holat="Yangi")
		murojaat_takror_holat.execute()
		self.assertEqual(frappe.db.get_value("Murojaat", lone, "holat"), "Yangi")


class TestOxirgiNatija(UnitTestCase):
	"""Murojaat holati — menejerning oxirgi natijasi bo'yicha (eski «Buyurtma berdi»da qolib ketmaydi)."""

	def setUp(self):
		self.shop = _shop()
		if not self.shop:
			self.skipTest("Shop yo'q")
		frappe.db.delete("Murojaat", {"normal_telefon": PHONE})

	def tearDown(self):
		frappe.db.rollback()

	def test_result_holat(self):
		self.assertEqual(m.result_holat("Buyurtma berdi", "Olmaydi"), "Olmaydi")
		self.assertEqual(m.result_holat("Buyurtma berdi", "Javob bermadi"), "Javob bermadi")
		self.assertEqual(m.result_holat("Buyurtma berdi", "Oladi"), "Buyurtma berdi")
		self.assertEqual(m.result_holat("Olmaydi", "Oladi"), "Oladi")
		self.assertEqual(m.result_holat("Yangi", "Oladi", order=frappe._dict(name="SO-1")), "Buyurtma berdi")

	def test_sync_orders_only_after_last_result(self):
		from unittest.mock import patch

		now = now_datetime()
		lead = frappe._dict(name="L1", normal_telefon=PHONE, creation=add_to_date(now, days=-6), aloqa_vaqt=add_to_date(now, days=-1))
		old_so = frappe._dict(name="SO-OLD", customer_phone="+" + PHONE, creation=add_to_date(now, days=-5))
		new_so = frappe._dict(name="SO-NEW", customer_phone="+" + PHONE, creation=now)
		for orders, expected in (([old_so], None), ([old_so, new_so], "SO-NEW")):
			with patch.object(m.frappe, "get_all", side_effect=[[lead], orders]), \
				patch.object(m.frappe.db, "set_value") as sv:
				m._sync_orders(self.shop)
			if expected:
				sv.assert_called_once_with("Murojaat", "L1", {"holat": "Buyurtma berdi", "buyurtma": expected}, update_modified=False)
			else:
				sv.assert_not_called()

	def test_patch_moves_stuck_lead(self):
		from marketplace.patches import murojaat_oxirgi_natija

		stuck = _lead(self.shop, holat="Buyurtma berdi", ago_min=300)
		ok = _lead(self.shop, holat="Buyurtma berdi", ago_min=200, mijoz_ismi="Boshqa")
		for name, natija in ((stuck, "Olmaydi"), (ok, "Oladi")):
			frappe.get_doc({
				"doctype": "Menejer Xulosasi", "murojaat": name, "telefon": "+998 33 074 04 90", "shop": self.shop,
				"kanal": "Qo‘ng‘iroq", "natija": natija, "menejer": "Administrator",
			}).insert(ignore_permissions=True)
		murojaat_oxirgi_natija.execute()
		self.assertEqual(frappe.db.get_value("Murojaat", stuck, "holat"), "Olmaydi")
		self.assertEqual(frappe.db.get_value("Murojaat", ok, "holat"), "Buyurtma berdi")
