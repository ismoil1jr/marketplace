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
