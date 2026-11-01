# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TelegramMijoz(Document):
	"""Do'kon saytida ro'yxatdan o'tgan mijoz: Telegram profili (ism, @username, rasm), telefoni va qachon,
	necha marta kirgani. Kirishda (tg_login.remember) va boshqa do'kondan buyurtmada (remember_order) yoziladi,
	eskilari — tg_login.sync_registered. Qo'lda yaratilmaydi."""
