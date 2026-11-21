"""Chegirma barabani: do'kon sozlamalarini tekshirish va yordamchilar."""

import frappe
from frappe import _


def variants(text):
	"""«1, 2,3» -> [1, 2, 3]: tartib saqlanadi, takror, raqam bo'lmagan va <= 0 tashlanadi."""
	out = []
	for part in str(text or "").split(","):
		part = part.strip()
		if not part.isdigit():
			continue
		n = int(part)
		if n > 0 and n not in out:
			out.append(n)
	return out


def validate_shop(doc, method=None):
	if not doc.get("baraban_yoqilgan"):
		return
	tovar = doc.get("baraban_tovar")
	if not tovar or frappe.db.get_value("Item", tovar, "shop") != doc.name:
		frappe.throw(_("Baraban tovari shu do'konning tovari bo'lishi kerak"))
	if (doc.get("baraban_narx") or 0) <= 0:
		frappe.throw(_("Chegirma narxi noldan katta bo'lishi kerak"))
	vs = variants(doc.get("baraban_variantlar"))
	if not vs:
		frappe.throw(_("Variantlar noto'g'ri: soatlarni vergul bilan yozing, masalan 1,2,3"))
	if doc.get("baraban_yutuq") not in vs:
		frappe.throw(_("Har doim tushadigan variant variantlar ichida bo'lishi kerak"))
	doc.baraban_variantlar = ",".join(map(str, vs))
