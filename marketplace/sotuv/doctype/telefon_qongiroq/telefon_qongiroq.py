# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import cint


class TelefonQongiroq(Document):
	"""Ilovadan (ASMIZ Call Agent) kelgan qo'ng'iroq yozuvi: sotuv/telefoniya.ingest_call.
	Holat: Yangi -> Yozuv bor -> Transkripsiya -> Tahlil qilindi (yoki Xato) — sotuv/stt.py."""

	def validate(self):
		self.natija = "Javob berildi" if cint(self.davomiyligi) > 0 else "Javob yo'q"
		self.yozuv_bor = 1 if self.yozuv else 0
		if self.yozuv and self.holat in (None, "", "Yangi"):
			self.holat = "Yozuv bor"
