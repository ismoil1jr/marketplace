def execute():
	"""O'lchamlar ro'yxati bo'sh do'konlarga standart o'lchamlar (XS…3XL) — yangi do'konga ochilganda qo'yiladigan bilan bir xil.
	Bir marta: do'konchi keyin o'chirgan o'lcham qaytib chiqmaydi (after_migrate'da emas)."""
	import frappe

	from marketplace.seller_desk import remember_shop_sizes
	from marketplace.setup import SIZES

	for shop in frappe.get_all("Shop", pluck="name"):
		if not frappe.db.exists("Olcham", {"shop": shop}):
			remember_shop_sizes(shop, SIZES)
