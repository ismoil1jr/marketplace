def execute():
	"""Telegram mijozlar ro'yxati keyin qo'shildi: undan oldin saytda ro'yxatdan o'tgan mijozlar ham yig'iladi
	(buyurtma bergan / kirgan do'koniga, Telegram'i bog'langanlarning @username va rasmi bilan)."""
	from marketplace.tg_login import sync_registered

	sync_registered()
