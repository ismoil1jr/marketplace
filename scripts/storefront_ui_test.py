"""Mijoz sahifasini haqiqiy brauzerda bosib tekshiradi (Playwright + Firefox).

O'rnatish (bir marta):  python3 -m venv ~/pw && ~/pw/bin/pip install playwright && ~/pw/bin/playwright install firefox
Ishga tushirish:        ~/pw/bin/python apps/marketplace/scripts/storefront_ui_test.py  (bench start ishlab turganda)
"""

import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8001"
SHOP = f"{BASE}/s/nafis-tekstil"
results = []


def check(name, ok, info=""):
	results.append(bool(ok))
	print("✅" if ok else "❌", name, f"— {info}" if info else "")


def text(locator):
	return locator.inner_text().replace("\u00a0", " ")


def visible_cards(pg):
	return pg.locator(".sf-card:visible").count()


def run(pg, width):
	print(f"\n── Ekran kengligi {width}px ──")
	errors = []
	pg.on("pageerror", lambda e: errors.append(str(e)))
	pg.goto(SHOP)
	pg.evaluate("localStorage.clear()")
	pg.reload()
	total = visible_cards(pg)
	check("Katalog ochildi", total == 8, f"{total} ta kartochka")

	chips = ".sf-catlist" if width >= 1100 else ".sf-chips"
	pg.locator(f"{chips} button", has_text="Shimlar").click()
	check("Kategoriya: Shimlar", visible_cards(pg) == 2, f"{visible_cards(pg)} ta")
	pg.locator(f"{chips} button", has_text="Hammasi").click()
	check("Kategoriya: Hammasi", visible_cards(pg) == 8)

	search = pg.locator("[data-search]:visible").first
	search.fill("futbolka")
	pg.wait_for_timeout(250)
	check("Qidiruv: futbolka", visible_cards(pg) == 1, f"{visible_cards(pg)} ta")
	search.fill("")
	pg.wait_for_timeout(250)

	pg.locator('.sf-card[data-code="nafis-tekstil-zigir-shim"] [data-fav]').click()
	fav_btn = pg.locator(f"{chips} [data-fav-filter]")
	check("Sevimlilar tugmasi paydo bo'ldi", fav_btn.is_visible())
	fav_btn.click()
	check("Sevimlilar filtri", visible_cards(pg) == 1)
	pg.locator('.sf-card[data-code="nafis-tekstil-zigir-shim"] [data-fav]').click()
	check("Oxirgi sevimli olinganda filtr yopiladi", visible_cards(pg) == 8 and not fav_btn.is_visible())

	pg.locator('.sf-card[data-code="nafis-tekstil-zigir-koylak-oq"] [data-add]').click()
	pg.locator('.sf-card[data-code="nafis-tekstil-paxta-futbolka"] [data-add]').click()
	pg.locator('.sf-card[data-code="nafis-tekstil-paxta-futbolka"] [data-add]').click()
	total_el = pg.locator("[data-cart-total]:visible").first
	check("Savatga qo'shish: jami", "367 000" in text(total_el), text(total_el))
	check("Kartochkadagi son belgisi", pg.locator('.sf-card[data-code="nafis-tekstil-paxta-futbolka"] .sf-add__qty').inner_text() == "2")
	check("Kardigan tugagan: + tugmasi yo'q", pg.locator('.sf-card[data-code="nafis-tekstil-trikotaj-kardigan"] [data-add]').count() == 0)

	pg.goto(f"{SHOP}/p/nafis-tekstil-klassik-shim")
	pg.locator("[data-step='1']").click()
	pg.locator("[data-step='1']").click()
	pg.locator("[data-buy-add]").click()
	check("Mahsulot sahifasi: 3 dona qo'shildi", pg.evaluate("JSON.parse(localStorage.getItem('mp_cart:nafis-tekstil'))['nafis-tekstil-klassik-shim']") == 3)

	pg.goto(f"{SHOP}/savat")
	pg.wait_for_selector(".sf-line")
	check("Savat sahifasi: 3 qator", pg.locator(".sf-line").count() == 3)
	check("Savat jami", "1 102 000" in text(pg.locator("[data-summary-total]")), text(pg.locator("[data-summary-total]")))
	line = pg.locator(".sf-line", has_text="Paxta futbolka")
	line.locator("[data-line-step='-1']").click()
	pg.wait_for_timeout(400)
	check("Savatda − bosildi", "1 013 000" in text(pg.locator("[data-summary-total]")), text(pg.locator("[data-summary-total]")))
	line = pg.locator(".sf-line", has_text="Paxta futbolka")
	line.locator("[data-line-step='-1']").click()
	pg.wait_for_timeout(400)
	check("0 ga tushgan qator o'chdi", pg.locator(".sf-line").count() == 2)

	pg.evaluate("localStorage.setItem('mp_cart:nafis-tekstil', JSON.stringify({'nafis-tekstil-trikotaj-kardigan': 1, 'bunyod-mebel-futbolka-01': 2}))")
	pg.reload()
	pg.wait_for_timeout(600)
	check("Tugagan / begona tovar savatdan tozalandi", pg.locator(".sf-line").count() == 0 and pg.locator(".sf-empty").is_visible())
	check("JS xatolari yo'q", not errors, errors)


def run_story(pg):
	print("\n── B shablon (story), 390px ──")
	errors = []
	pg.on("pageerror", lambda e: errors.append(str(e)))
	pg.goto(f"{SHOP}?layout=story")
	pg.evaluate("localStorage.clear()")
	pg.reload()
	check("Story shabloni ochildi", pg.locator(".st-card").count() == 8 and "layout-story" in pg.locator("body").get_attribute("class"))
	pg.locator(".st-hl", has_text="Shimlar").click()
	check("Highlight: Shimlar", visible_cards(pg) == 2)
	pg.locator(".st-hl", has_text="Chegirma").click()
	check("Highlight: Chegirma", visible_cards(pg) == 1)
	pg.locator(".st-hl", has_text="Yangi").click()
	check("Highlight: Yangi (4 ta eng yangi)", visible_cards(pg) == 4)
	pg.locator(".st-hl", has_text="Hammasi").click()
	slides = pg.locator('.st-card[data-code="nafis-tekstil-zigir-koylak-oq"] [data-slides]')
	slides.evaluate("e => e.scrollTo({left: e.clientWidth})")
	pg.wait_for_timeout(300)
	check("Rasm hisoblagichi 2 / 2", pg.locator('.st-card[data-code="nafis-tekstil-zigir-koylak-oq"] [data-counter]').inner_text() == "2 / 2")
	pg.locator("[data-toggle-search]").click()
	pg.locator("[data-search]").fill("shim")
	pg.wait_for_timeout(250)
	check("Qidiruv tugmasi va qidiruv", visible_cards(pg) == 2)
	pg.locator("[data-search]").fill("")
	pg.locator('.st-card[data-code="nafis-tekstil-zigir-shim"] [data-add]').click()
	check("Savat paneli: 1 ta", text(pg.locator("[data-cart-qty-label]")) == "1 ta" and pg.locator("[data-cartbar]").is_visible())
	pg.locator('.st-card[data-code="nafis-tekstil-zigir-shim"] .st-card__name').click()
	pg.wait_for_load_state()
	check("Havola bo'ylab mahsulot sahifasi ham story shablonida", "layout-story" in pg.locator("body").get_attribute("class"))
	pg.goto(SHOP)
	check("Parametrsiz havola do'konning haqiqiy shablonini ochadi", "layout-vitrina" in pg.locator("body").get_attribute("class"))
	check("JS xatolari yo'q (story)", not errors, errors)


with sync_playwright() as p:
	browser = p.firefox.launch()
	page = browser.new_page(viewport={"width": 390, "height": 844})
	run_story(page)
	page.close()
	for w, h in ((390, 844), (820, 1180), (1440, 900)):
		page = browser.new_page(viewport={"width": w, "height": h})
		run(page, w)
		page.close()
	browser.close()

print(f"\n{sum(results)}/{len(results)} o'tdi")
sys.exit(0 if all(results) else 1)
