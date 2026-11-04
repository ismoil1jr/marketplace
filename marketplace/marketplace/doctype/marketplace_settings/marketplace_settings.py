# Copyright (c) 2026, ismoil and contributors
# For license information, please see license.txt

import secrets

from frappe.model.document import Document


class MarketplaceSettings(Document):
	def validate(self):
		# Meta webhook obunasida Meta shu tokenni qaytaradi (sotuv/meta.webhook GET) — o'zi yaratiladi
		if not self.meta_verify_token:
			self.meta_verify_token = secrets.token_urlsafe(24)
