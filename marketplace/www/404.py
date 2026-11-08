import frappe

no_cache = 1


def get_context(context):
	"""Topilmagan sahifa 404 kodi bilan qaytsin (Frappe get_context ichidagi xatoda 200 berib yuboradi — qidiruv tizimlari
	uchun "soft 404")."""
	context.http_status_code = 404
