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
