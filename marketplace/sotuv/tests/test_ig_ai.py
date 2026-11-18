import json
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from marketplace.sotuv import ig_ai

OK = '{"javob_kerak": true, "javob": "Assalomu alaykum! Narxi 99 000 so\'m.", "til": "uz", "telefon": null, "ism": null, "tovar_kodi": null}'


def _resp(status, text=OK):
	r = MagicMock()
	r.status_code = status
	r.text = text
	r.json.return_value = (
		{"candidates": [{"content": {"parts": [{"text": text}]}}]} if status == 200 else {"error": {"message": "x"}}
	)
	return r


class TestIgAi(UnitTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _catalog(self, stock):
		rows = [frappe._dict(name="IT-1", item_name="Krossovka", is_stock_item=1, has_variants=0, mp_tez_kunda=0)]
		with (
			patch("frappe.get_all", return_value=rows),
			patch("marketplace.storefront._get_prices", return_value={"IT-1": 99000.0}),
			patch("marketplace.storefront._get_stock", return_value=stock),
			patch("frappe.db.get_value", return_value="WH"),
		):
			return ig_ai.catalog("Shop")

	def test_catalog_hides_quantity(self):
		item = self._catalog({"IT-1": 1500})[0]
		self.assertEqual(item["holat"], "bor")
		self.assertNotIn(1500, item.values())
		self.assertNotIn(1500.0, item.values())
		self.assertEqual(self._catalog({"IT-1": 0})[0]["holat"], "tugagan")

	def _holat(self, **fields):
		row = frappe._dict(name="IT-9", item_name="Y", is_stock_item=1, has_variants=0, mp_tez_kunda=0)
		row.update(fields)
		with (
			patch("frappe.get_all", return_value=[row]),
			patch("marketplace.storefront._get_prices", return_value={"IT-9": 5.0}),
			patch("marketplace.storefront._get_stock", return_value={}),
			patch("marketplace.storefront._get_variant_stock", return_value={"IT-9": 7}),
			patch("frappe.db.get_value", return_value="WH"),
		):
			return ig_ai.catalog("Shop")[0]

	def test_catalog_variant_template_in_stock(self):
		item = self._holat(has_variants=1, is_stock_item=0)
		self.assertEqual(item["holat"], "bor")
		self.assertNotIn(7, item.values())

	def test_catalog_non_stock_item_is_bor(self):
		self.assertEqual(self._holat(is_stock_item=0)["holat"], "bor")

	def test_catalog_tez_kunda_is_tugagan(self):
		self.assertEqual(self._holat(mp_tez_kunda=1, has_variants=1)["holat"], "tugagan")

	def test_catalog_missing_price_is_none(self):
		rows = [frappe._dict(name="IT-2", item_name="X", is_stock_item=1, has_variants=0, mp_tez_kunda=0)]
		with (
			patch("frappe.get_all", return_value=rows),
			patch("marketplace.storefront._get_prices", return_value={}),
			patch("marketplace.storefront._get_stock", return_value={}),
			patch("frappe.db.get_value", return_value="WH"),
		):
			self.assertIsNone(ig_ai.catalog("Shop")[0]["narx"])

	def _items(self):
		return [{"kod": "IT-1", "nom": "Krossovka", "narx": 99000.0, "holat": "bor", "havola": "http://x/s/S/p/IT-1"}]

	def test_prompt_rules(self):
		p = ig_ai.build_prompt("Shop", "Toshkent", self._items(), "Narxi?", "Izoh")
		for s in ("Assalomu alaykum", "Здравствуйте", "aniq sonini aytma", "Krossovka", "javob_kerak"):
			self.assertIn(s, p)

	def test_prompt_includes_history(self):
		tarix = [{"kim": "Mijoz", "matn": "Salom"}, {"kim": "Do'kon", "matn": "Assalomu alaykum!"}]
		p = ig_ai.build_prompt("Shop", "", self._items(), "Narxi?", "DM", tarix)
		self.assertIn("3 gap", p)
		self.assertLess(p.index("Mijoz: Salom"), p.index("Do'kon: Assalomu alaykum!"))

	def test_parse_reply_plain(self):
		self.assertEqual(
			ig_ai.parse_reply(OK),
			{"javob_kerak": True, "javob": "Assalomu alaykum! Narxi 99 000 so'm.", "til": "uz",
			 "telefon": None, "ism": None, "tovar_kodi": None},
		)

	def test_parse_reply_fenced_json(self):
		out = ig_ai.parse_reply("Mana javob:\n```json\n" + OK + "\n```")
		self.assertTrue(out["javob_kerak"])
		self.assertEqual(out["til"], "uz")

	def test_parse_reply_invalid(self):
		with self.assertRaises(ig_ai.IgAiError):
			ig_ai.parse_reply("salom")
		with self.assertRaises(ig_ai.IgAiError):
			ig_ai.parse_reply('{"javob_kerak": true, "javob": ""}')

	def test_extract_phone(self):
		self.assertEqual(ig_ai.extract_phone("Nomerim 90 123 45 67"), "998901234567")
		self.assertEqual(ig_ai.extract_phone("+998 (93) 291-93-03"), "998932919303")
		self.assertIsNone(ig_ai.extract_phone("narxi qancha"))

	def _cfg(self):
		return frappe._dict(gemini_model="m1", zaxira_model="m2")

	def test_answer_falls_back_to_next_model(self):
		with (
			patch.object(ig_ai, "catalog", return_value=[]),
			patch.object(ig_ai.stt, "settings", return_value=self._cfg()),
			patch.object(ig_ai.stt, "api_key", return_value="k"),
			patch("frappe.db.get_value", return_value=frappe._dict(shop_name="Nom", ig_ai_malumot="", warehouse="WH")),
			patch("marketplace.telegram_bot.http.post", side_effect=[_resp(503), _resp(200)]),
		):
			out = ig_ai.answer("Shop", "Narxi?")
		self.assertEqual(out["model"], "m2")
		self.assertTrue(out["javob_kerak"])

	def test_answer_non_json_200_is_iga_error(self):
		bad = _resp(200)
		bad.json.side_effect = ValueError("no json")
		with (
			patch.object(ig_ai, "catalog", return_value=[]),
			patch.object(ig_ai.stt, "settings", return_value=frappe._dict(gemini_model="m1", zaxira_model="")),
			patch.object(ig_ai.stt, "api_key", return_value="k"),
			patch("frappe.db.get_value", return_value=frappe._dict(shop_name="Nom", ig_ai_malumot="")),
			patch("marketplace.telegram_bot.http.post", return_value=bad),
		):
			with self.assertRaises(ig_ai.IgAiError) as cm:
				ig_ai.answer("Shop", "Narxi?")
		self.assertTrue(cm.exception.retry)

	def test_answer_quota_pauses(self):
		with (
			patch.object(ig_ai, "catalog", return_value=[]),
			patch.object(ig_ai.stt, "settings", return_value=self._cfg()),
			patch.object(ig_ai.stt, "api_key", return_value="k"),
			patch("frappe.db.get_value", return_value=frappe._dict(shop_name="Nom", ig_ai_malumot="", warehouse="WH")),
			patch("marketplace.telegram_bot.http.post", return_value=_resp(429)),
		):
			with self.assertRaises(ig_ai.IgAiError) as cm:
				ig_ai.answer("Shop", "Narxi?")
		self.assertTrue(cm.exception.pause)

	def test_answer_fills_phone_from_text(self):
		with (
			patch.object(ig_ai, "catalog", return_value=[]),
			patch.object(ig_ai.stt, "settings", return_value=self._cfg()),
			patch.object(ig_ai.stt, "api_key", return_value="k"),
			patch("frappe.db.get_value", return_value=frappe._dict(shop_name="Nom", ig_ai_malumot="", warehouse="WH")),
			patch("marketplace.telegram_bot.http.post", return_value=_resp(200)),
		):
			out = ig_ai.answer("Shop", "Nomerim 90 123 45 67")
		self.assertEqual(out["telefon"], "998901234567")
