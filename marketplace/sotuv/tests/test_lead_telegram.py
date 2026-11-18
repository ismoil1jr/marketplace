from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from marketplace import telegram_bot
from marketplace.sotuv import murojaat as m

PHONE = "998977770011"


class TestLeadTelegram(UnitTestCase):
	def setUp(self):
		self.shop = frappe.db.get_value("Shop", {}, "name")
		if not self.shop:
			self.skipTest("Shop yo'q")
		frappe.db.delete("Murojaat", {"normal_telefon": PHONE})

	def tearDown(self):
		frappe.db.rollback()

	def _lead(self):
		return frappe.get_doc({
			"doctype": "Murojaat", "shop": self.shop, "mijoz_ismi": "Ali Valiyev", "telefon": "+998 97 777 00 11",
			"normal_telefon": PHONE, "holat": "Yangi", "manba": "Instagram", "tovar_nomi": "Panda books",
			"izoh": "Instagram: @ali_77\nDirect: narxi qancha?",
		}).insert(ignore_permissions=True)

	def test_new_lead_message_goes_to_manager_ids_with_button(self):
		frappe.db.set_value("Shop", self.shop, "murojaat_telegram_ids", "111, 222", update_modified=False)
		lead = self._lead()
		with patch.object(telegram_bot, "token", return_value="t"), patch.object(telegram_bot, "send") as send:
			telegram_bot.notify_new_lead(lead.name)
		self.assertEqual([c.args[0] for c in send.call_args_list], ["111", "222"])
		text = send.call_args.args[1]
		self.assertEqual(text, "📣 Murojaat keldi: <b>Ali Valiyev</b>")
		url = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["url"]
		self.assertIn(f"sotuv-paneli?murojaat={lead.name}", url)

	def test_no_ids_no_message(self):
		frappe.db.set_value("Shop", self.shop, "murojaat_telegram_ids", "", update_modified=False)
		lead = self._lead()
		with patch.object(telegram_bot, "token", return_value="t"), patch.object(telegram_bot, "send") as send:
			telegram_bot.notify_new_lead(lead.name)
		send.assert_not_called()

	def test_only_new_leads_are_announced(self):
		with patch("frappe.enqueue") as enq:
			name, dup = m.save_lead(self.shop, {"telefon": "+998 97 777 00 11", "ism": "Ali"})
			self.assertFalse(dup)
			again, dup2 = m.save_lead(self.shop, {"telefon": "+998 97 777 00 11", "ism": "Ali"})
		self.assertTrue(dup2)
		calls = [c for c in enq.call_args_list if c.args and c.args[0] == "marketplace.telegram_bot.notify_new_lead"]
		self.assertEqual(len(calls), 1)
		self.assertEqual(calls[0].kwargs["name"], name)
		self.assertTrue(calls[0].kwargs.get("enqueue_after_commit"))
