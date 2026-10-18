# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TelegramContact(Document):
	"""Telefon raqami ↔ Telegram chat. Mijoz botga o'z raqamini bir marta yuborgach yoziladi:
	shundan keyin bot bu raqamga kodni darhol yubora oladi."""
