"""Item.standard_rate (ro'yxatdagi «Sotish narxi») — Item Price'dagi joriy narx bilan tenglashtiriladi.
ERPNext standard_rate'ni faqat yaratishda Item Price'ga ko'chiradi; keyin narx Item Price'da yashaydi va
standard_rate 0 bo'lib qolar edi — ro'yxatda narx ko'rinmasdi (seller_desk.item_price_on_update endi sinxron tutadi)."""

import frappe


def execute():
	from marketplace.storefront import _selling_price_list

	price_list = _selling_price_list()
	frappe.db.sql(
		"""
		update `tabItem` i
		join `tabItem Price` p on p.item_code = i.name and p.price_list = %s
		set i.standard_rate = p.price_list_rate
		where i.standard_rate != p.price_list_rate and i.shop is not null and i.shop != ''
		""",
		(price_list,),
	)
