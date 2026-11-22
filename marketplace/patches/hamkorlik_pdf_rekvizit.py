def execute():
	"""Rekvizitlar alohida qatorga ajratildi va sozlamaga keyin kiritilgan rekvizitlar saqlangan PDF'ga tushmagan edi
	(2026-11-22) — imzolanmagan shartnomalar PDF'i joriy rekvizit va yangi shablon bilan qayta yasaladi."""
	from marketplace.marketplace.doctype.hamkorlik.hamkorlik import refresh_pdfs

	refresh_pdfs()
