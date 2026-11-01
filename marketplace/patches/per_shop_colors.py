"""Ranglar do'kon bo'yicha: oldin bitta umumiy ro'yxat edi (clothes'da Nafis'ning "sabizi rang"i ko'rinib,
o'chirib bo'lmasdi). Endi har do'konda standart ranglar va o'z tovarlarida ishlatilgan ranglar; tovarlardagi
havolalar (Ranglar, galereya, kirim) o'z do'koni rangiga o'tkaziladi."""

import frappe

from marketplace.marketplace.doctype.rang.rang import remember_shop_colors
from marketplace.setup import COLOR_ATTR, COLORS

LINKS = ("Tovar Rangi", "Item Gallery", "Tovar Kirimi")


def execute():
	shops = frappe.get_all("Shop", pluck="name", order_by="creation asc")
	rangs = {r.name: r for r in frappe.get_all("Rang", fields=["name", "rang_nomi", "hex", "shop"])}
	hexes = dict(
		frappe.get_all("Item Attribute Value", filters={"parent": COLOR_ATTR}, fields=["attribute_value", "color_hex"], as_list=True)
	)
	hexes.update({name: hex_ for name, _abbr, hex_ in COLORS})
	hexes.update({r.rang_nomi: r.hex for r in rangs.values() if r.hex})

	# Har do'kon qaysi ranglarni ishlatgan: {do'kon: {nomi: necha marta}}
	used = {}
	for dt in LINKS:
		for r in frappe.db.sql(
			f"""select i.shop, c.rang from `tab{dt}` c join `tabItem` i on i.name = c.parent
			where c.parenttype = 'Item' and ifnull(c.rang, '') != '' and ifnull(i.shop, '') != ''""",
			as_dict=True,
		):
			name = rangs[r.rang].rang_nomi if r.rang in rangs else r.rang
			used.setdefault(r.shop, {}).setdefault(name, 0)
			used[r.shop][name] += 1
	for r in frappe.db.sql(
		"""select i.shop, a.attribute_value as name from `tabItem Variant Attribute` a join `tabItem` i on i.name = a.parent
		where a.attribute = %s and ifnull(a.attribute_value, '') != '' and ifnull(i.shop, '') != ''""",
		COLOR_ATTR,
		as_dict=True,
	):
		used.setdefault(r.shop, {}).setdefault(r.name, 0)
		used[r.shop][r.name] += 1

	# Eski umumiy yozuv eng ko'p ishlatgan do'konga o'tadi; hech kim ishlatmagan standart rang — eng birinchi do'konga.
	# Hech kim ishlatmagan nostandart rang (masalan sinab qo'shilgan) do'konsiz qoladi: faqat admin ko'radi
	standard = {name for name, _abbr, _hex in COLORS}
	for r in rangs.values():
		if r.shop:
			continue
		users = sorted((s for s in shops if used.get(s, {}).get(r.rang_nomi)), key=lambda s: -used[s][r.rang_nomi])
		owner = users[0] if users else (shops[0] if shops and r.rang_nomi in standard else None)
		if owner:
			frappe.db.set_value("Rang", r.name, "shop", owner, update_modified=False)

	for shop in shops:
		names = [name for name, _abbr, _hex in COLORS] + sorted(used.get(shop, {}))
		remember_shop_colors(shop, [(name, hexes.get(name)) for name in names])

	# Tovarlardagi havolalar — o'z do'konining shu nomli rangiga
	own = {
		(r.shop, r.rang_nomi.lower()): r.name
		for r in frappe.get_all("Rang", filters={"shop": ["is", "set"]}, fields=["name", "rang_nomi", "shop"])
	}
	names = dict(frappe.get_all("Rang", fields=["name", "rang_nomi"], as_list=True))
	for dt in LINKS:
		for r in frappe.db.sql(
			f"""select c.name, c.rang, i.shop from `tab{dt}` c join `tabItem` i on i.name = c.parent
			where c.parenttype = 'Item' and ifnull(c.rang, '') != '' and ifnull(i.shop, '') != ''""",
			as_dict=True,
		):
			target = own.get((r.shop, (names.get(r.rang) or r.rang).lower()))
			if target and target != r.rang:
				frappe.db.set_value(dt, r.name, "rang", target, update_modified=False)
