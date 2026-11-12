"""Saytni «yangi ochilgandek» tozalash: ishga tushirishdan oldin, test ma'lumotlarini butunlay o'chirish uchun.

O'chadi:
* barcha do'konlar va ularga tegishli hamma narsa: tovarlar (rasm/video fayllari bilan), narxlar, kirimlar,
  ombor qoldiqlari, buyurtmalar, yetkazishlar, to'lovlar, kassa yozuvlari, mijozlar (kontaktlari bilan),
  doimiy mijozlar, kontragentlar, ranglar, o'lchamlar;
* Sotuv: murojaatlar, qo'ng'iroqlar (audio fayllari bilan), menejer xulosalari, majburiy tasdiqlar;
* do'kon omborlari va do'kon kategoriyalari; standartdan tashqari rang/o'lcham qiymatlari;
* do'kon xodimlari (foydalanuvchilar) va ularning Telegram bog'lanishlari, saytga kirgan mijozlar sessiyalari;
* shu hujjatlarning izohlari, tarixi, bildirishnomalari, xato jurnali;
* hujjat raqamlari: buyurtma, kirim, murojaat va boshqalar yana 00001 dan boshlanadi.

Qoladi: kompaniya va buxgalteriya sozlamalari, Marketplace Settings (bot, telefon, Meta ilova),
Telefoniya Sozlamalari (Gemini), standart omborlar (Stores, Do'konlar guruhi...) va standart kategoriyalar,
standart rang/o'lchamlar, Administrator va platforma xodimlari (System Manager yoki Marketplace Manager roli bor).

Qanday ishlatiladi (frappe foydalanuvchisi ostida, bench papkasida):

    bench --site <sayt> backup --with-files                     # 1) zaxira, qaytarish uchun
    bench --site <sayt> execute marketplace.wipe.run            # 2) nima o'chishini ko'rish, HECH NARSA O'CHMAYDI
    bench --site <sayt> execute marketplace.wipe.run --kwargs "{'confirm': 'HAMMASINI-TOZALA'}"   # 3) o'chirish
    bench --site <sayt> clear-cache && bench --site <sayt> clear-website-cache

Bir martalik vosita: ishlatib bo'lingach bu faylni o'chirib yuborsa bo'ladi.
"""

import os
import re

import frappe
from frappe.utils.nestedset import rebuild_tree

CONFIRM = "HAMMASINI-TOZALA"
PLATFORM_ROLES = {"System Manager", "Marketplace Manager"}
APP_MODULES = ("Marketplace", "Sotuv", "Dokon")

# ERPNext hujjatlari — bu saytda faqat do'konlar ishlatadi, shuning uchun jadval to'liq bo'shatiladi
ERP_DOCTYPES = (
	"Sales Order", "Delivery Note", "Sales Invoice", "Payment Entry", "Journal Entry", "Stock Entry",
	"Stock Reconciliation", "Purchase Receipt", "Purchase Invoice", "Purchase Order", "Material Request",
	"Pick List", "Quotation", "Stock Reservation Entry", "Serial and Batch Bundle", "Repost Item Valuation",
	"Repost Payment Ledger", "GL Entry", "Stock Ledger Entry", "Payment Ledger Entry", "Bin", "Item Price",
	"Item", "Customer",
)

# Hujjatga ishora qiluvchi yordamchi jadvallar: (jadval, hujjat turi ustuni)
REFS = (
	("Comment", "reference_doctype"), ("Version", "ref_doctype"), ("Communication", "reference_doctype"),
	("Communication Link", "link_doctype"), ("Notification Log", "document_type"), ("ToDo", "reference_type"),
	("DocShare", "share_doctype"), ("Tag Link", "document_type"), ("Activity Log", "reference_doctype"),
	("Document Follow", "ref_doctype"), ("Deleted Document", "deleted_doctype"), ("__global_search", "doctype"),
)


def run(confirm=None):
	plan = _plan()
	_report(plan)
	if confirm != CONFIRM:
		print(f"\nHech narsa o'chirilmadi. O'chirish uchun: --kwargs \"{{'confirm': '{CONFIRM}'}}\"")
		return
	try:
		paths = _apply(plan)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		raise
	# fayllar bazadan keyin: xato bo'lsa baza qaytariladi, fayllar joyida qoladi
	removed = _remove_files(paths)
	removed += _remove_files(_orphan_disk_files())
	frappe.clear_cache()
	print(f"\nTayyor: baza tozalandi, diskdan {removed} ta fayl o'chirildi.")
	print("Endi: bench --site <sayt> clear-cache && bench --site <sayt> clear-website-cache")


# ---------------- Reja: nima o'chadi ----------------


def _plan():
	doctypes = _wipe_doctypes()
	shops = frappe.get_all("Shop", pluck="name")
	users = frappe.get_all("User", filters={"name": ["not in", ["Administrator", "Guest"]]}, pluck="name")
	keep_users = [u for u in users if PLATFORM_ROLES & set(frappe.get_roles(u))]
	drop_users = [u for u in users if u not in keep_users]
	customer_contacts = _linked_parents("Contact", "Customer")
	user_contacts = frappe.get_all("Contact", filters={"user": ["in", drop_users]}, pluck="name") if drop_users else []
	return frappe._dict(
		doctypes=doctypes,
		counts={dt: frappe.db.count(dt) for dt in doctypes},
		shops=shops,
		warehouses=frappe.get_all("Warehouse", filters={"shop": ["is", "set"]}, pluck="name"),
		item_groups=frappe.get_all("Item Group", filters={"shop": ["is", "set"]}, pluck="name"),
		attr_values=_extra_attribute_values(),
		keep_users=keep_users,
		drop_users=drop_users,
		contacts=sorted(set(customer_contacts) | set(user_contacts)),
		addresses=_linked_parents("Address", "Customer"),
		series=_series_to_reset(doctypes),
		error_logs=frappe.db.count("Error Log"),
		loose_files=_loose_files(),
		orphans=len(_orphan_disk_files()),
	)


def _wipe_doctypes():
	app = frappe.get_all(
		"DocType", filters={"module": ["in", APP_MODULES], "istable": 0, "issingle": 0, "is_virtual": 0}, pluck="name"
	)
	erp = [dt for dt in ERP_DOCTYPES if frappe.db.exists("DocType", dt)]
	return [dt for dt in app + erp if frappe.db.table_exists(dt)]


def _settings_files():
	"""Sozlamalarda (Single doctype'lar) ishlatilgan fayllar — hech qachon o'chmaydi."""
	return {r[0].rsplit("/", 1)[-1] for r in frappe.db.sql("select value from tabSingles where value like '%%/files/%%'")}


def _loose_files():
	"""Hech qaysi hujjatga biriktirilmagan yuklamalar (Excel importlar, skrinshotlar), sozlamadagilardan tashqari."""
	keep = _settings_files()
	rows = frappe.get_all(
		"File", filters={"is_folder": 0, "attached_to_doctype": ["is", "not set"]}, fields=["name", "file_url", "thumbnail_url"]
	)
	return [r for r in rows if (r.file_url or "").rsplit("/", 1)[-1] not in keep]


def _orphan_disk_files():
	"""Diskda turgan, lekin bazada File yozuvi yo'q fayllar (oldingi o'chirishlardan qolgan rasm nusxalari va h.k.)."""
	used = _settings_files()
	for f in frappe.get_all("File", fields=["file_url", "thumbnail_url"]):
		used.update(u.rsplit("/", 1)[-1] for u in (f.file_url, f.thumbnail_url) if u)
	out = []
	for folder in (frappe.get_site_path("public", "files"), frappe.get_site_path("private", "files")):
		if os.path.isdir(folder):
			out += [os.path.join(folder, n) for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)) and n not in used]
	return out


def _linked_parents(parenttype, link_doctype):
	return frappe.get_all(
		"Dynamic Link", filters={"parenttype": parenttype, "link_doctype": link_doctype}, pluck="parent", distinct=True
	)


def _extra_attribute_values():
	"""Do'konlar qo'shgan rang/o'lcham qiymatlari (standart ro'yxatdan tashqari)."""
	from marketplace.setup import COLOR_ATTR, COLORS, SIZE_ATTR, SIZES

	standard = {COLOR_ATTR: {c[0] for c in COLORS}, SIZE_ATTR: set(SIZES)}
	rows = frappe.get_all(
		"Item Attribute Value", filters={"parent": ["in", list(standard)]}, fields=["name", "parent", "attribute_value"]
	)
	return [r for r in rows if r.attribute_value not in standard[r.parent]]


def _series_to_reset(doctypes):
	"""Hujjat nomlaridagi raqamdan oldingi qism (SAL-ORD-2026-, nafis-tekstil- ...) — o'sha hisoblagichlar 0 ga.
	format:...{#####} nomli hujjatlar umumiy "" hisoblagichni ishlatadi (faqat ilovamiz hujjatlari)."""
	from frappe.model.naming import parse_naming_series

	prefixes = set()
	for dt in doctypes:
		autoname = frappe.db.get_value("DocType", dt, "autoname") or ""
		if autoname.startswith("format:") and "#" in autoname:
			prefixes.add("")
		# Hujjatning o'z raqamlash qoliplari (MAT-RECO-.YYYY.- ...): hujjat qolmagan, lekin hisoblagich qolgan bo'lsa ham
		field = frappe.get_meta(dt).get_field("naming_series")
		templates = (field.options or "").split("\n") if field else []
		if "#" in autoname and not autoname.startswith(("format:", "field:", "hash")):
			templates.append(autoname)
		for t in templates:
			t = t.split("#", 1)[0].rstrip(".")
			if t:
				try:
					prefixes.add(parse_naming_series(t, doctype=dt))
				except Exception:
					pass
		for name in frappe.get_all(dt, pluck="name"):
			m = re.match(r"^(.*?)(\d{3,})$", str(name))
			if m:
				prefixes.add(m.group(1))
	existing = set(frappe.db.sql_list("select name from tabSeries"))
	return sorted(prefixes & existing)


def _report(p):
	print("=== Saytni tozalash rejasi ===")
	print("Do'konlar:", ", ".join(p.shops) or "—")
	print("\nO'chadigan yozuvlar:")
	for dt in p.doctypes:
		if p.counts[dt]:
			print(f"  {dt:28s} {p.counts[dt]}")
	print(f"  {'Do`kon omborlari':28s} {len(p.warehouses)}  {', '.join(p.warehouses)}")
	print(f"  {'Do`kon kategoriyalari':28s} {len(p.item_groups)}")
	print(f"  {'Qo`shimcha rang/o`lcham':28s} {len(p.attr_values)}")
	print(f"  {'Kontaktlar':28s} {len(p.contacts)}")
	print(f"  {'Manzillar':28s} {len(p.addresses)}")
	print(f"  {'Xato jurnali':28s} {p.error_logs}")
	print(f"  {'Biriktirilmagan fayllar':28s} {len(p.loose_files)}")
	print(f"  {'Diskdagi egasiz fayllar':28s} {p.orphans}")
	print("\nO'chadigan foydalanuvchilar (do'kon xodimlari):")
	for u in p.drop_users:
		print("  -", u)
	print("Qoladigan foydalanuvchilar: Administrator" + "".join(f", {u}" for u in p.keep_users))
	print("Noldan boshlanadigan raqamlar:", ", ".join(repr(s) for s in p.series) or "—")
	_warn_settings(p)


def _warn_settings(p):
	"""Sozlamalarda o'chadigan ombor/do'konga ishora qolib ketmasin (masalan Stock Settings'da standart ombor)."""
	names = list(p.shops) + list(p.warehouses)
	if not names:
		return
	rows = frappe.db.sql("select doctype, field, value from tabSingles where value in %s", (tuple(names),))
	for dt, field, value in rows:
		print(f"DIQQAT: {dt}.{field} = {value} — o'chadi, sozlamani keyin yangilang")


# ---------------- Bajarish ----------------


def _apply(p):
	paths = _file_paths(p)
	for dt in p.doctypes:
		_delete_all(dt)
	_delete_names("Warehouse", p.warehouses)
	_delete_names("Item Group", p.item_groups)
	frappe.db.delete("Item Attribute Value", {"name": ["in", [r.name for r in p.attr_values] or [""]]})
	_delete_names("Contact", p.contacts)
	_delete_names("Address", p.addresses)
	frappe.db.delete("File", {"name": ["in", [f.name for f in p.loose_files] or [""]]})
	for user in p.drop_users:
		frappe.delete_doc("User", user, ignore_permissions=True, force=True, delete_permanently=True)
	# Do'kon/omborga berilgan ruxsatlar va standart qiymatlar (qolgan foydalanuvchilarda ham)
	frappe.db.delete("User Permission", {"allow": ["in", ["Shop", "Warehouse", "Item", "Customer"]]})
	gone = list(p.shops) + list(p.warehouses)
	if gone:
		frappe.db.delete("DefaultValue", {"defvalue": ["in", gone]})
	gone_types = tuple(p.doctypes)
	for table, column in REFS:
		if table == "__global_search":
			frappe.db.sql("delete from `__global_search` where `doctype` in %s", (gone_types,))
		elif frappe.db.table_exists(table, cached=False) and frappe.db.has_column(table, column):
			frappe.db.sql(f"delete from `tab{table}` where `{column}` in %s", (gone_types,))
	frappe.db.delete("Error Log")
	if p.series:
		frappe.db.sql("delete from tabSeries where name in %s", (tuple(p.series),))
	for tree in ("Item Group", "Warehouse"):
		rebuild_tree(tree)
	return paths


def _delete_all(doctype):
	"""Butun jadval + uning jadval-maydonlari (faqat shu hujjat turiga tegishli qatorlar) + biriktirilgan fayllar."""
	for df in frappe.get_meta(doctype).get_table_fields():
		frappe.db.delete(df.options, {"parenttype": doctype})
	frappe.db.delete("File", {"attached_to_doctype": doctype})
	frappe.db.delete(doctype)


def _delete_names(doctype, names):
	if not names:
		return
	for df in frappe.get_meta(doctype).get_table_fields():
		frappe.db.delete(df.options, {"parenttype": doctype, "parent": ["in", names]})
	frappe.db.delete("File", {"attached_to_doctype": doctype, "attached_to_name": ["in", names]})
	frappe.db.delete(doctype, {"name": ["in", names]})


def _file_paths(p):
	"""Diskdagi fayllar: o'chadigan hujjatlarga biriktirilganlar (boshqa joyda ishlatilmasa)."""
	targets = [["attached_to_doctype", "in", p.doctypes]]
	for dt, names in (("User", p.drop_users), ("Contact", p.contacts), ("Warehouse", p.warehouses), ("Item Group", p.item_groups)):
		if names:
			targets.append(["attached_to_doctype", "=", dt])  # nom bo'yicha pastda ajratiladi
	files = frappe.get_all(
		"File", or_filters=targets, fields=["name", "file_url", "thumbnail_url", "attached_to_doctype", "attached_to_name"]
	)
	partial = {"User": set(p.drop_users), "Contact": set(p.contacts), "Warehouse": set(p.warehouses), "Item Group": set(p.item_groups)}
	doomed = [
		f for f in files
		if f.attached_to_doctype in p.doctypes or f.attached_to_name in partial.get(f.attached_to_doctype, ())
	]
	doomed += p.loose_files
	doomed_names = {f.name for f in doomed}
	urls = {u for f in doomed for u in (f.file_url, f.thumbnail_url) if u}
	# Shu fayl boshqa (qoladigan) yozuvda ham ishlatilsa — diskdan o'chmaydi
	shared = set(frappe.get_all("File", filters={"file_url": ["in", list(urls) or [""]], "name": ["not in", list(doomed_names) or [""]]}, pluck="file_url"))
	return [_disk_path(u) for u in urls - shared if _disk_path(u)]


def _disk_path(url):
	if url.startswith("/private/files/"):
		return frappe.get_site_path(url.lstrip("/"))
	if url.startswith("/files/"):
		return frappe.get_site_path("public", url.lstrip("/"))
	return None


def _remove_files(paths):
	removed = 0
	for path in paths:
		try:
			os.remove(path)
			removed += 1
		except FileNotFoundError:
			pass
	return removed


# ---------------- Faqat murojaatlar (test lidlar) ----------------

LEADS_CONFIRM = "MUROJAATLARNI-OCHIR"


def murojaatlar(dokon=None, confirm=None):
	"""Faqat murojaatlarni o'chirish (masalan, test lidlar). Boshqa hech narsa o'chmaydi.

	O'chadi: murojaatlar, ularga bog'langan menejer xulosalari va bildirishnomalari.
	Qoladi: qo'ng'iroqlar (yozuvi bilan; murojaat havolasi bo'shatiladi), buyurtmalar, mijozlar, tovarlar.
	O'chirilganlar «Deleted Document» ro'yxatida qoladi — kerak bo'lsa Desk'dan tiklanadi.

	    bench --site <sayt> execute marketplace.wipe.murojaatlar                      # hisobot, hech narsa o'chmaydi
	    bench --site <sayt> execute marketplace.wipe.murojaatlar --kwargs "{'confirm': 'MUROJAATLARNI-OCHIR'}"
	    # faqat bitta do'kon: --kwargs "{'dokon': 'Pandoo', 'confirm': 'MUROJAATLARNI-OCHIR'}"
	"""
	filters = {"shop": dokon} if dokon else {}
	rows = frappe.get_all("Murojaat", filters=filters, fields=["name", "shop", "mijoz_ismi", "telefon", "creation"], order_by="creation asc")
	names = [r.name for r in rows] or [""]
	by_shop = {}
	for r in rows:
		by_shop[r.shop] = by_shop.get(r.shop, 0) + 1
	print("=== Murojaatlarni o'chirish ===")
	print("Do'kon:", dokon or "barcha do'konlar")
	print("Murojaatlar:", len(rows), "|", ", ".join(f"{k}: {v}" for k, v in by_shop.items()) or "—")
	for r in rows[:30]:
		print(f"  {r.name}  {r.shop}  {r.mijoz_ismi or ''}  {r.telefon or ''}  {str(r.creation)[:16]}")
	if len(rows) > 30:
		print(f"  … va yana {len(rows) - 30} ta")
	print("Ular bilan o'chadigan menejer xulosalari:", frappe.db.count("Menejer Xulosasi", {"murojaat": ["in", names]}))
	print("Qoladigan qo'ng'iroqlar (havolasi bo'shatiladi):", frappe.db.count("Telefon Qongiroq", {"murojaat": ["in", names]}))
	if not rows:
		return
	if confirm != LEADS_CONFIRM:
		print(f"\nHech narsa o'chirilmadi. O'chirish uchun: --kwargs \"{{'confirm': '{LEADS_CONFIRM}'}}\"")
		return
	for r in rows:
		# Murojaat.on_trash: menejer xulosalarini o'chiradi, qo'ng'iroqdan havolani bo'shatadi
		frappe.delete_doc("Murojaat", r.name, ignore_permissions=True)
	frappe.db.delete("Notification Log", {"document_type": "Murojaat", "document_name": ["in", names]})
	frappe.db.commit()
	print(f"\nTayyor: {len(rows)} ta murojaat o'chirildi. Qolgan murojaatlar: {frappe.db.count('Murojaat', filters)}")
