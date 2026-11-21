# Chegirma barabani (discount wheel) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A shop can turn on a non-closable "discount wheel". The first time a visitor opens the shop, they spin it and always land on the admin's chosen hours. They then get the admin's discount price on one product, with that product added to their cart. A countdown shows on every shop page and runs only while the page is visible. When it reaches zero, the normal price returns.

**Architecture:**
- New Shop fields hold the per-shop settings.
- A new doctype, **Baraban Chegirma**, holds one row per browser. The row is identified by an HttpOnly cookie `mp_baraban`.
- `marketplace/baraban.py` exposes guest APIs `state`, `spin` and `tick`. The server owns the remaining seconds.
- `storefront.get_cart_lines`, which is the single pricing path for cart and order, applies the discount price while the token is active.
- A separate `public/js/baraban.js` and `public/css/baraban.css` draw the wheel and the countdown bar. They load only when the shop's wheel is on.

**Tech Stack:** Frappe 16, Python, vanilla JS and CSS. The storefront has no framework.

**Spec:** `docs/superpowers/specs/2026-11-21-chegirma-barabani-design.md`

## Global Constraints

- **Strings:** all user-facing strings are in Uzbek Latin. Never write «tasodifiy» or "random".
- **Wheel:**
  - It cannot be closed: no close button, no Esc, no click-outside.
  - It is shown only when the shop's wheel is on and the browser has no token for that shop.
- **Outcome:** the spin always ends on `baraban_yutuq`. Remaining time is `baraban_yutuq × 3600` seconds.
- **Countdown:**
  - Format `HH:MM:SS`, counting down every second only while `document.visibilityState === "visible"`.
  - It syncs with `tick` about every 15 s and immediately when the page becomes visible again.
  - The server deducts `min(now − oxirgi_signal, 20 s)` per tick.
- **Price:**
  - While the token is active, `baraban_narx` replaces the price of `baraban_tovar` and of its variants (`variant_of == baraban_tovar`).
  - After it expires, the normal Item Price applies.
  - The browser price is never trusted.
- **Cookie:** `mp_baraban`, HttpOnly, SameSite=Lax, 30 days. Key the cookie value per shop: the stored token row belongs to one shop, and a token for another shop is ignored.
- **Failure:** if the wheel is off, misconfigured, or its API fails, the shop works exactly as before.
- **Background:** no background processes are left running. Tests use `frappe.tests.UnitTestCase` with mocks, plus `frappe.db.rollback()` in tearDown.

## Review Focus

1. **A re-spin must not reset the timer.** `spin` with an existing valid token returns the same row. Test: `test_spin_is_once_per_browser` (Task 2).
2. **Away time is not counted.** A tick after a 2-hour gap deducts ≤ 20 s. Test: `test_tick_caps_gap` (Task 2).
3. **Expired or foreign token gives no discount.** Test: `test_cart_price_only_while_active` and `test_token_of_other_shop_ignored` (Task 3).
4. **Variants of the product get the price, other items do not.** Test: `test_cart_price_applies_to_variants_only` (Task 3).
5. **A misconfigured wheel, such as `yutuq` not among the variants, is rejected on save.** If a bad config is already saved, the site still renders and `state` returns `enabled: false`. Test: `test_validate_shop` and `test_state_disabled_on_bad_config` (Tasks 1–2).

---

### Task 1: Data model — Shop wheel fields, Baraban Chegirma doctype, validation

**Files:**
- Modify: `marketplace/marketplace/doctype/shop/shop.json`. Add a new Section Break «Chegirma barabani» with:
  - `baraban_yoqilgan` — Check, label «Baraban yoqilgan»;
  - `baraban_tovar` — Link Item, label «Tovar»;
  - `baraban_narx` — Currency, label «Chegirma narxi»;
  - `baraban_variantlar` — Data, label «Variantlar (soat, vergul bilan)», default «1,2,3,4,5»;
  - `baraban_yutuq` — Int, label «Har doim tushadigan variant (soat)», default 3.

  Put the section before the existing «Instagram AI» section (`sb_ig_ai`), or at the end if that is missing. Add descriptions in Uzbek. Use permlevel 0, like the Instagram AI fields.
- Create: `marketplace/marketplace/doctype/baraban_chegirma/{__init__.py, baraban_chegirma.json, baraban_chegirma.py}`. Module «Marketplace», autoname `hash`. Fields:
  - `shop` — Link Shop, reqd, in_list_view, search_index;
  - `token` — Data, reqd, unique;
  - `soat` — Int;
  - `qolgan_soniya` — Int, in_list_view;
  - `oxirgi_signal` — Datetime.

  Permissions: System Manager and Marketplace Manager can read and delete.
- Create: `marketplace/baraban.py` with `variants(text) -> list[int]` and `validate_shop(doc, method=None)`.
- Modify: `marketplace/hooks.py` — `doc_events["Shop"]["validate"]` gains `"marketplace.baraban.validate_shop"`. Read the existing dict. If `validate` is already a string or list, turn it into a list that keeps the existing handler.
- Test: `marketplace/tests/test_baraban.py`. Create the package `marketplace/tests/__init__.py` if it is missing.

**Interfaces — Produces:**
- `variants(text: str | None) -> list[int]`: parses «1, 2,3» into `[1, 2, 3]`, keeps the given order, drops duplicates, non-numbers and values ≤ 0. An empty result means invalid.
- `validate_shop(doc, method=None) -> None`: only when `doc.baraban_yoqilgan`.
  - Throws `frappe.ValidationError` with an Uzbek message if:
    - `baraban_tovar` is empty or not of this shop (`Item.shop == doc.name`);
    - `baraban_narx` ≤ 0;
    - `variants()` is empty;
    - `baraban_yutuq` is not in `variants()`.
  - Normalizes `doc.baraban_variantlar` to `",".join(map(str, variants))`.

- [ ] **Step 1: Write the failing tests.**
  - `test_variants_parse`: «1, 2,x,0,2,5» → `[1, 2, 5]`.
  - `test_validate_shop`: the four failing cases above raise; a valid config passes and is normalized. Use an in-memory `frappe.get_doc({"doctype": "Shop", ...})`-like `frappe._dict` with a patched `frappe.db.get_value` for the Item shop.
  - `test_doctype_exists`: `frappe.get_meta("Baraban Chegirma").has_field("qolgan_soniya")` is true, and so is `frappe.get_meta("Shop").has_field("baraban_yutuq")`.
- [ ] **Step 2: Run, expect FAIL.** `cd /home/ismoil/marketplace-bench && bench --site marketplace.local run-tests --module marketplace.tests.test_baraban`
- [ ] **Step 3: Implement.** Then run `bench --site marketplace.local migrate`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit.** `feat: chegirma barabani — Shop sozlamalari va Baraban Chegirma`

### Task 2: Server API — state / spin / tick / active

**Files:**
- Modify: `marketplace/baraban.py`
- Test: `marketplace/tests/test_baraban.py` (extend)

**Interfaces — Consumes:** Task 1 fields and `variants()`. `storefront.get_shop(slug)` returns 404 for an inactive shop; reuse it for the shop lookup in the APIs.

**Interfaces — Produces:**
- `COOKIE = "mp_baraban"`
- `MAX_STEP = 20`
- `config(shop: str) -> frappe._dict | None` returns `{tovar, narx, variantlar: list[int], yutuq, tovar_nomi, eski_narx (Item Price of tovar, else None), rasm}`.
  - It returns `None` if the wheel is off or the config is invalid; that check reuses the `validate_shop` rules without throwing.
- `_row(shop) -> frappe._dict | None` reads the cookie `frappe.request.cookies.get(COOKIE)` and returns the Baraban Chegirma row only if `row.shop == shop`.
- Guest APIs: `@frappe.whitelist(allow_guest=True, methods=["POST"])` with `@rate_limit(limit=60, seconds=60)`:
  - `state(shop) -> dict`: `{enabled: bool, spun: bool, variants, win, remaining: int, price, old_price, product: {code, name, thumb}}`. Returns `{enabled: False}` when `config` is `None`.
  - `spin(shop) -> dict`:
    - If `_row` exists, return `state` (no reset).
    - Otherwise insert a row with `token = frappe.generate_hash(length=32)`, `soat = yutuq`, `qolgan_soniya = yutuq*3600`, `oxirgi_signal = now`. Set the cookie with `frappe.local.cookie_manager.set_cookie(COOKIE, token, expires=add_days(now, 30), httponly=True, samesite="Lax")`, then return state with `spun: True`.
    - Insert with `ignore_permissions=True`.
  - `tick(shop) -> dict`: if a row exists and `qolgan_soniya > 0`, deduct `min(seconds since oxirgi_signal, MAX_STEP)` (floor at 0) and set `oxirgi_signal = now`. Returns `{remaining}`; with no row it returns 0.
- `active(shop: str) -> tuple[str, float] | None` returns `(tovar, narx)` if `config(shop)` and `_row(shop)` exist and `qolgan_soniya > 0`, otherwise `None`. It never raises: on any exception, log once and return `None`.

- [ ] **Step 1: Write the failing tests.** Patch `frappe.request` with an object whose `.cookies` is a dict, and patch `frappe.local.cookie_manager`.
  - `test_state_disabled_on_bad_config`: the wheel is on but `yutuq` is not among the variants → `{enabled: False}`.
  - `test_spin_creates_row_and_cookie`: `qolgan_soniya == 3*3600`, and `set_cookie` was called with httponly.
  - `test_spin_is_once_per_browser`: the second spin with the same cookie returns the same token and `remaining`.
  - `test_tick_caps_gap`: `oxirgi_signal` is 2 h ago → `remaining` drops by ≤ 20.
  - `test_tick_normal`: 10 s ago → drops by about 10.
  - `test_active_none_when_expired`: `qolgan_soniya = 0` → `None`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit.** `feat: chegirma barabani API — aylantirish bir marta, taymer serverda`

### Task 3: Pricing — discount price in cart and order

**Files:**
- Modify: `marketplace/storefront.py`:
  - In `get_cart_lines`, after `price` is computed per line: if `promo = baraban.active(shop.name)` and `(i.name == promo[0] or i.variant_of == promo[0])`, set `price = promo[1]`, `"retail_price"` to the normal price, and `"list_price"` to `max(normal price, old_price)`. Also set `"baraban": True`.
  - Import lazily to avoid cycles.
  - The wholesale (`ws`) price does not stack: the discount price wins.
- Test: `marketplace/tests/test_baraban.py` (extend)

**Interfaces — Consumes:** `baraban.active(shop) -> (tovar, narx) | None`.

- [ ] **Step 1: Write the failing tests.** Patch `baraban.active` and the storefront helpers `_get_prices`, `_get_stock` and `frappe.get_all` as needed, or use real Items of an existing shop if simpler. Either way, assert the returned dict values.
  - `test_cart_price_only_while_active`: with `active` set → the line price is 360000; with `None` → the normal price.
  - `test_cart_price_applies_to_variants_only`: the discounted product's variant gets the price; another item does not.
  - `test_token_of_other_shop_ignored`: a row of shop B with the cookie, while querying shop A → `active` is `None` (test `_row` directly).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.** Also run the existing modules `marketplace.sotuv.tests.test_murojaat_dedup` and `marketplace.sotuv.tests.test_lead_telegram`; they must still pass.
- [ ] **Step 5: Commit.** `feat: chegirma narxi savat va buyurtmada (faqat faol taymerda)`

### Task 4: Storefront UI — wheel modal, countdown bar, cart add, price display

**Files:**
- Create: `marketplace/public/js/baraban.js` and `marketplace/public/css/baraban.css`.
- Modify: `marketplace/templates/storefront/base.html`. When `shop.baraban_yoqilgan`, add `<link rel="stylesheet" href="/assets/marketplace/css/baraban.css?v={{ asset_version }}">` and `<script src="/assets/marketplace/js/baraban.js?v={{ asset_version }}" defer></script>` after storefront.js.
- Modify: `marketplace/storefront.py` `get_shop` — add `baraban_yoqilgan` to the selected fields.
- Modify: `marketplace/public/js/storefront.js` — expose a minimal hook `window.SF.cart = { add: cart.add, qty: cart.qty }` right after `cart` is defined. On the cart page, also expose `window.SF.reloadCart = initCart`, or the existing function that re-fetches prices.
- Modify: `marketplace/hooks.py` only if assets must be registered. They are plain `/assets/marketplace/...` files, so normally no change is needed.

**Behaviour (baraban.js):**
1. On DOMContentLoaded, `POST /api/method/marketplace.baraban.state` with `shop=SF.shop` (form-encoded, header `X-Frappe-CSRF-Token: SF.csrf`). If `!enabled`, do nothing.
2. If `!spun`, show a full-screen overlay, `role="dialog" aria-modal="true"`:
   - Title «Chegirma barabani»; subtitle «Aylantiring va chegirma vaqtini oling».
   - The wheel is an SVG with N equal segments labelled «{h} soat», alternating brand / light colors (`var(--brand)`), and a pointer at the top.
   - The center button is «Aylantirish».
   - Lock body scroll; ignore Esc and backdrop clicks.
3. On click: disable the button and call `spin`. Then animate `transform: rotate(...)` over 4.5 s with `cubic-bezier(.17,.67,.12,1)`, at least 5 full turns, ending with the winning segment under the pointer.
   - Respect `prefers-reduced-motion`: use a short 0.6 s rotation.
4. After the animation, show the result panel:
   - «🎉 Tabriklaymiz!», «Sizga {win} soatlik chegirma»;
   - the product name with `price` and `old_price` crossed out;
   - a button «Savatga o'tish». It runs `SF.cart.add(code, 1)` if `SF.cart.qty(code) == 0`, then goes to `SF.base + "/savat"`.
   - The product is also added to the cart right when the result shows, in case the user navigates away.
5. Countdown bar: a fixed bar at the top of every shop page, including the cart, shown when `spun && remaining > 0`.
   - Text: «⏳ Chegirma tugashiga: HH:MM:SS · {name} {price}».
   - It decrements every second only while visible.
   - It calls `tick` every 15 s while visible, and on `visibilitychange` → visible. The server value replaces the local value.
   - At 0 it shows «Chegirma muddati tugadi» for about 5 s and hides. On the cart page it calls `SF.reloadCart?.()` (or `location.reload()`) so the normal price appears.
   - Add body padding-top equal to the bar height so content is not covered.
6. Price display while active:
   - On catalog and product pages, find the elements that show the discounted product's price and replace them with `price`, with `old_price` crossed out. Look for `[data-code="<code>"]` cards and the product page price node; read the templates `templates/storefront/catalog_*.html` and `www/storefront/product.html` for the exact class names.
   - If a node is not found, skip it silently.
7. All network errors are swallowed. The wheel or bar simply does not show.

- [ ] **Step 1: Implement the files.** Keep `baraban.js` self-contained in an IIFE, ES2019, with no libraries.
- [ ] **Step 2: Asset check.**
  - Run `bench --site marketplace.local migrate`.
  - Ensure `sites/assets/marketplace` serves the new files. Public files of the app are symlinked; verify with `ls -la /home/ismoil/marketplace-bench/sites/assets/marketplace/js/baraban.js`.
  - Run `node --check marketplace/public/js/baraban.js` if node is available.
- [ ] **Step 3: Server render check, without a browser.**
  - In `bench --site marketplace.local console` (or execute), set a local test shop's wheel on with a valid product.
  - Render the catalog route: `frappe.website.serve.get_response("s/<shop>")`, or use `frappe.render_template` with the base template. Confirm the HTML contains `baraban.js`. Roll back afterwards.
  - Report exactly what was verified and what still needs a manual browser check.
- [ ] **Step 4: Commit.** `feat: chegirma barabani — aylanadigan baraban, sahifa tepasida taymer, savatga qo'shish`

### Task 5: Deploy notes

- [ ] Run all test modules: `marketplace.tests.test_baraban` plus the 9 existing `marketplace.sotuv.tests.*` modules. They must PASS.
- [ ] Push per the deploy flow, after the final review and the user's go-ahead. The user runs the server pull, migrate, clear-cache and restart.
- [ ] Prod settings checklist for the user:
  - Pandoo «Panda books» Item Price back to **500 000**.
  - Shop → «Chegirma barabani»: tovar = Panda books, narx = 360 000, variantlar «1,2,3,4,5», yutuq 3, yoqilgan → Save.
  - Open the shop in a private window and check:
    - the wheel shows and cannot be closed;
    - it lands on 3 hours;
    - the cart shows 360 000 and the bar counts down;
    - leaving and returning pauses and resumes the countdown.
