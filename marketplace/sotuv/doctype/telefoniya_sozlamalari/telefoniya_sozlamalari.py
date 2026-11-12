# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TelefoniyaSozlamalari(Document):
	"""Telefoniya: yozuvlarni saqlash muddati, fayl hajmi chegarasi va AI (Gemini) transkripsiya — sotuv/stt.py."""

	def validate(self):
		for field, label in (("saqlash_kuni", _("Saqlash muddati")), ("maks_fayl_mb", _("Maksimal fayl hajmi")),
		                     ("stt_min_sekund", _("Minimal davomiylik")), ("stt_maks_daqiqa", _("Maksimal davomiylik"))):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} manfiy bo'lishi mumkin emas").format(label))
		self.gemini_model = (self.gemini_model or "").strip()
		self.zaxira_model = (self.zaxira_model or "").strip()

	def on_update(self):
		"""Kalit, model yoki «AI yoqilgan» o'zgargan bo'lishi mumkin: AI endi ishlasa — avval xato bo'lgan yozuvlar
		qayta navbatga, navbat darhol fonda boshlanadi (15 daqiqani kutmasdan)."""
		from marketplace.sotuv import stt

		frappe.clear_document_cache(self.doctype, self.name)
		if stt.blockers():
			return
		stt.retry_failed()
		frappe.enqueue("marketplace.sotuv.stt.process_queue", queue="long", timeout=3600, enqueue_after_commit=True)
