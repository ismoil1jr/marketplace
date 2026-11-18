# Instagram AI — comment + Direct replies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every minute the site reads new comments on Panda Books' Instagram posts, reels and active ad videos, plus new Direct messages. For each one it asks Gemini for a short reply in the customer's language, then sends that reply to that same customer: a threaded reply under the comment, or a DM in the same conversation. A «Sinov» (draft) mode shows replies on the site without sending them.

**Architecture:**
- Polling only. Comment webhooks need Advanced Access, so they are not used.
- `sotuv/instagram.py` talks to the Graph API through the existing `meta._graph()` and `meta._page_token()`.
- `sotuv/ig_ai.py` builds the prompt from the shop catalog and calls Gemini with the key and models in Telefoniya Sozlamalari. It never touches Graph.
- A new doctype, **Instagram Xabar**, stores each comment, its AI reply and its status.
- Direct (DM) messages are added in Task 7 (`sotuv/instagram_dm.py`). The user asked for comments and DMs in one delivery.

**Tech Stack:** Frappe 16 / ERPNext 16, Python 3.14, `requests`, Gemini `generateContent` (JSON mode), Graph API (version from `meta._conf().ver`).

**Spec:** `docs/superpowers/specs/2026-11-16-instagram-ai-sotuvchi-design.md`

## Global Constraints

- **Language:** reply in the commenter's language — Uzbek (Latin or Cyrillic, as written) or Russian.
- **Greeting:** every reply starts with a greeting: «Assalomu alaykum!» or «Здравствуйте!».
- **Length:** a comment reply is at most 2 sentences; a DM reply is at most 3 sentences.
- **Every question is answered to its own author:**
  - a comment gets a reply under that comment (`POST {comment_id}/replies`); a reply-to-reply gets `@username` under the parent;
  - a DM gets a message to that sender's IGSID.
- **Human takeover (DM):** if the shop's account sends a DM in a conversation that our system did not send (an operator typed in the Instagram app), AI stays silent for that customer for 24 hours.
- **Stock count:** never revealed. The AI receives only `holat: "bor" | "tugagan"`, never a quantity. «Bor» → «Ha, albatta bor». «Tugagan» → «Hozircha tugagan, menejerimiz aniqlab beradi».
- **No invention:** no prices, discounts or dates beyond the catalog and the «AI uchun ma'lumot» text. If the price is missing → «Menejerimiz Direct'da aniqlab beradi».
- **Gemini:**
  - key = `stt.api_key()`;
  - models = Telefoniya Sozlamalari `gemini_model`, then `zaxira_model`, then `stt.auto_models()`;
  - `temperature` 0.3;
  - `responseMimeType` `application/json`.
- **AI output shape:** `{javob_kerak, javob, til, telefon, ism, tovar_kodi}`. Invalid JSON → nothing is posted and holat = «Xato».
- **Modes:** `ig_ai_rejim` = O'chiq / Sinov / Yoqilgan, default «O'chiq». In «Sinov» nothing is ever posted to Instagram.
- **Polling:**
  - runs every minute;
  - the first run, and any gap, looks back at most 15 minutes, so old comments are never answered;
  - Graph error codes 4, 17, 32, 613 pause that shop for 15 minutes.
- **Per-customer limit:** at most 10 posted AI replies per Instagram user per shop per hour.
- **Own comments:** comments by the shop's own IG account are never answered.
- **Strings and secrets:** user-facing strings are in Uzbek Latin. Tokens and keys never go into Error Log messages.
- **Local bench:** stop the local bench after testing (kill the honcho pgid).

## Review Focus

1. **Own reply comes back in the comment list.** It must be skipped, otherwise the bot answers itself in a loop. Test: `test_fetch_skips_own_account` (Task 3).
2. **First run on an account with old comments.** Comments older than 15 minutes must not be answered. Test: `test_fetch_ignores_old_comments` (Task 3).
3. **Customer replies under our reply (a reply-to-reply).** We answer under the parent comment with an `@username` prefix, because Instagram only nests one level. Test: `test_process_reply_to_reply_targets_parent` (Task 4).
4. **Item with no Item Price.** The catalog passes `narx: None` and the prompt says not to quote a price. Test: `test_catalog_missing_price_is_none` (Task 2).
5. **Operator answers a DM in the Instagram app.** AI must not talk over them; it stays silent for that customer for 24 hours. Test: `test_dm_operator_message_pauses_ai` (Task 7).

Also pinned, though less likely: Gemini wrapping the JSON in fences → `test_parse_reply_fenced_json` (Task 2).

---

### Task 1: Data model — Instagram Xabar + Shop fields

**Files:**
- Create: `marketplace/sotuv/doctype/instagram_xabar/{__init__.py, instagram_xabar.json, instagram_xabar.py, instagram_xabar.js}`
- Modify: `marketplace/marketplace/doctype/shop/shop.json`. Add a new section «Instagram AI» after `meta_page_token` with these fields:
  - `ig_ai_rejim` — Select «O'chiq\nSinov\nYoqilgan», default «O'chiq»;
  - `ig_ai_malumot` — Small Text, label «AI uchun ma'lumot», description «Yetkazib berish, to'lov, ish vaqti, buyurtma qanday beriladi»;
  - `ig_user_id` — Data, read_only;
  - `ig_username` — Data, read_only;
  - `meta_ad_account` — Data, label «Reklama kabineti (act_…)».
- Modify: `marketplace/permissions.py` — add `def instagram_xabar_query(user=None): return shop_query(user, "Instagram Xabar")`.
- Modify: `marketplace/hooks.py` — add `"Instagram Xabar": "marketplace.permissions.instagram_xabar_query"` to `permission_query_conditions`.
- Create: `marketplace/sotuv/tests/__init__.py`, `marketplace/sotuv/tests/test_instagram_model.py`

**Interfaces:**
- **Produces:** doctype `Instagram Xabar`, module «Sotuv», autoname `IGX-.#####`. Fields:
  - `shop` — Link Shop, reqd, in_list_view, in_standard_filter;
  - `turi` — Select «Izoh\nDM», default «Izoh»;
  - `tashqi_id` — Data, reqd, **unique**;
  - `ota_id` — Data (parent comment id);
  - `media_id` — Data;
  - `media_havola` — Data, options URL;
  - `mijoz_id` — Data;
  - `username` — Data, in_list_view;
  - `matn` — Small Text, in_list_view;
  - `ai_javob` — Small Text;
  - `til` — Data;
  - `holat` — Select «Yangi\nQoralama\nYuborildi\nJavobsiz\nXato», default «Yangi», in_list_view, in_standard_filter;
  - `xato` — Small Text;
  - `vaqt` — Datetime;
  - `javob_id` — Data;
  - `murojaat` — Link Murojaat.
- **Permissions:** the same four roles as Murojaat (System Manager, Marketplace Manager, Shop Seller, Shop Sales Manager), with read and write.
- **Sort:** `sort_field` = `vaqt`, desc.

- [ ] **Step 1: Write the failing test.** Class `TestInstagramModel(frappe.tests.UnitTestCase)` with two tests:
  - `test_shop_has_ai_fields` — `frappe.get_meta("Shop").has_field(f)` is true for all five Shop fields.
  - `test_tashqi_id_unique` — inserting two Instagram Xabar with the same `tashqi_id` raises `frappe.UniqueValidationError`. Use `frappe.db.rollback()` in `tearDown`.
- [ ] **Step 2: Enable tests and run, expect FAIL**
  - Run: `cd /home/ismoil/marketplace-bench && bench --site marketplace.local set-config allow_tests true && bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_instagram_model`
  - Expected: FAIL (doctype not found).
- [ ] **Step 3: Create the doctype JSON and the Shop fields, then migrate**
  - Run: `bench --site marketplace.local migrate`
  - `instagram_xabar.py`: `class InstagramXabar(Document): pass`.
- [ ] **Step 4: Run the tests, expect PASS** (same command as Step 2).
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): Instagram Xabar doctype va Shop «Instagram AI» maydonlari"`

### Task 2: `ig_ai.py` — catalog, prompt, Gemini, parsing

**Files:**
- Create: `marketplace/sotuv/ig_ai.py`
- Test: `marketplace/sotuv/tests/test_ig_ai.py`

**Interfaces:**
- **Consumes:**
  - `marketplace.storefront._get_prices(codes) -> dict[str, float]`;
  - `marketplace.storefront._get_stock(codes, warehouse) -> dict[str, float]`;
  - `marketplace.sotuv.stt.api_key()`, `stt.settings()`, `stt.auto_models()`, `stt.API`;
  - `marketplace.sotuv.telefoniya.normalize_phone`.
- **Produces:**
  - `class IgAiError(Exception)` — attributes `pause: bool` (quota, 429) and `retry: bool`.
  - `catalog(shop: str) -> list[dict]` — items where `shop=shop`, `is_published=1`, `disabled=0` and `variant_of` is not set, up to 60. Each dict is `{"kod", "nom", "narx": float | None, "holat": "bor" | "tugagan", "havola": get_url(f"/s/{shop}/p/{kod}")}`. Never includes a quantity.
  - `build_prompt(shop_name: str, malumot: str, items: list[dict], matn: str, turi: str, tarix: list[dict] | None = None) -> str` — `tarix` is the earlier DM turns `[{"kim": "Mijoz" | "Do'kon", "matn": str}]`, oldest first, at most 10.
  - `parse_reply(raw: str) -> dict` — returns the six keys with types `bool, str, str, str|None, str|None, str|None`. Raises `IgAiError` when there is no JSON object, or when `javob_kerak` is true but `javob` is empty.
  - `extract_phone(text: str) -> str | None` — the first run of 9 or more digits, normalized with `normalize_phone`; otherwise `None`.
  - `answer(shop: str, matn: str, turi: str = "Izoh", tarix: list[dict] | None = None) -> dict` — `parse_reply` output plus `"model"`. When the AI's `telefon` is empty, it is filled from `extract_phone(matn)`.

- [ ] **Step 1: Write the failing tests** (`unittest.mock.patch` for DB and HTTP):
  - `test_catalog_hides_quantity` — with stock 1500 → `holat == "bor"`, and no value in the dict equals 1500; with stock 0 → `"tugagan"`.
  - `test_catalog_missing_price_is_none` — an item missing from `_get_prices` → `narx is None`.
  - `test_prompt_rules` — `build_prompt(...)` contains «Assalomu alaykum», «Здравствуйте», «aniq sonini aytma», the item name and «javob_kerak».
  - `test_prompt_includes_history` — with `tarix=[{"kim": "Mijoz", "matn": "Salom"}, {"kim": "Do'kon", "matn": "Assalomu alaykum!"}]` and `turi="DM"`, the prompt contains both turns in order and the «3 gap» rule.
  - `test_parse_reply_plain` — `'{"javob_kerak": true, "javob": "Assalomu alaykum! Narxi 99 000 so\'m.", "til": "uz", "telefon": null, "ism": null, "tovar_kodi": null}'` parses to the matching dict.
  - `test_parse_reply_fenced_json` — the same JSON inside ```` ```json … ``` ```` plus a leading sentence still parses.
  - `test_parse_reply_invalid` — `"salom"` → raises `IgAiError`; `{"javob_kerak": true, "javob": ""}` → raises `IgAiError`.
  - `test_extract_phone` — «Nomerim 90 123 45 67» → `"998901234567"` (verified: `normalize_phone` prefixes 998 to 9 digits); «+998 (93) 291-93-03» → `"998932919303"`; «narxi qancha» → `None`.
  - `test_answer_falls_back_to_next_model` — the first model gives HTTP 503 and the second gives 200 with valid JSON → returns `model == second`; a 429 → raises `IgAiError` with `pause=True`.
- [ ] **Step 2: Run, expect FAIL**
  - Run: `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_ig_ai`
  - Expected: ImportError.
- [ ] **Step 3: Implement**
  - The Gemini call mirrors `stt._call`'s error mapping (429 → pause; 500–504 and 404 → retry the next model; 401/403 → raise), but sends text-only `contents`.
  - The prompt is in Uzbek and lists, verbatim, the rules from Global Constraints (greeting, language, ≤2 sentences for an izoh and ≤3 for a DM, no quantities, no invention, when to set `javob_kerak=false`).
  - Items and «AI uchun ma'lumot» are embedded as a JSON block.
- [ ] **Step 4: Run, expect PASS** (same command).
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): ig_ai — katalog, prompt va Gemini javobi"`

### Task 3: `instagram.py` — collect comments (posts, reels, ads)

**Files:**
- Create: `marketplace/sotuv/instagram.py`
- Test: `marketplace/sotuv/tests/test_instagram_fetch.py`

**Interfaces:**
- **Consumes:** `meta._graph(method, path, token=None, **params)`, `meta._page_token(shop)`, `meta.MetaError` (has `.code`).
- **Produces:**
  - `LOOKBACK = 15 * 60`
  - `RATE_CODES = {4, 17, 32, 613}`
  - `media_list(shop: str) -> list[dict]` — returns `{"id", "havola"}`:
    - `GET {ig_user_id}/media fields=id,permalink limit=25`;
    - plus, when `meta_ad_account` is set, `GET {act}/ads effective_status=["ACTIVE"] fields=creative{effective_instagram_media_id,instagram_permalink_url} limit=50`;
    - de-duplicated by id. An ads error is logged to the shop status and does not stop the posts.
  - `fetch_comments(shop: str, since_ts: int) -> list[dict]` — per media: `GET {media}/comments fields=id,text,timestamp,username,from{id,username},replies{id,text,timestamp,username,from{id,username}} limit=50`.
    - Flattens top-level comments and replies into `{"id", "parent_id" (None for top-level), "text", "username", "from_id", "timestamp" (epoch int), "media_id", "havola"}`.
    - Drops anything older than `since_ts` and anything where `from_id == ig_user_id` or `username == ig_username`.
  - `store(shop: str, c: dict) -> str | None` — inserts Instagram Xabar (`turi="Izoh"`, holat «Yangi»). Returns the name, or `None` when `tashqi_id` already exists.

- [ ] **Step 1: Write the failing tests** (patch `instagram._graph`, `_page_token` and Shop values):
  - `test_media_list_merges_posts_and_ads` — 2 posts plus 2 ads (one of them the same media as a post) → 3 unique ids.
  - `test_media_list_ads_error_keeps_posts` — the ads call raises `MetaError` → the posts are still returned.
  - `test_fetch_skips_own_account` — a reply whose `from.id == ig_user_id` is not returned.
  - `test_fetch_ignores_old_comments` — a comment with a timestamp 20 minutes ago and `since_ts = now - 15min` is not returned.
  - `test_fetch_flattens_replies` — a reply gets `parent_id` = the top-level id.
  - `test_store_dedup` — the second `store` with the same id returns `None`.
- [ ] **Step 2: Run, expect FAIL** — `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_instagram_fetch`
- [ ] **Step 3: Implement the three functions.** Convert timestamps with `frappe.utils.get_datetime` → epoch.
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): Instagram izohlarini yig'ish (post, reel, reklama)"`

### Task 4: Process and post the reply, modes, lead, operator send

**Files:**
- Modify: `marketplace/sotuv/instagram.py`
- Create/modify: `marketplace/sotuv/doctype/instagram_xabar/instagram_xabar.js` — buttons «Yuborish» (when holat is Qoralama or Xato) and «AI javobini qayta yozish».
- Test: `marketplace/sotuv/tests/test_instagram_process.py`

**Interfaces:**
- **Consumes:** `ig_ai.answer`, `ig_ai.IgAiError`, `murojaat.save_lead(shop, data, asked)`, Task 3's `store`.
- **Produces:**
  - `MAX_PER_HOUR = 10`
  - `process(name: str) -> str` — returns the final holat:
    - O'chiq → leave «Yangi»;
    - AI says `javob_kerak=false` → «Javobsiz»;
    - Sinov → «Qoralama» (with `ai_javob` saved);
    - Yoqilgan → post, then «Yuborildi» (`javob_id` saved);
    - any `IgAiError` or `MetaError` → «Xato» with `xato` set. On `IgAiError.pause`, call `frappe.cache.set_value("mp_ig_ai_pause", 1, expires_in_sec=3600)`.
    - When `telefon` is present: `save_lead(shop, {"telefon", "ism", "manba": "Instagram", "izoh": f"Izoh: {matn}", "lead_id": f"ig:{mijoz_id}:{date}"}, tovar_kodi)` and link `murojaat`.
  - `_post(shop: str, doc) -> str` — `POST {ota_id or tashqi_id}/replies message=…`. When `ota_id` is set, the message is prefixed with `@{username} `. Returns the reply id.
  - `_deliver(shop: str, doc) -> str` — the only sending entry point used by `process` and `send`. For `turi == "Izoh"` it calls `_post`; for any other `turi` it raises `frappe.ValidationError`. Task 7 adds the DM branch.
  - `process` passes `tarix` to `ig_ai.answer` only for DMs, via `instagram_dm.history(doc)`. Until Task 7 exists, guard it with `turi == "DM"`.
  - `@frappe.whitelist(methods=["POST"]) send(name: str)` — operator posts the existing `ai_javob`. Allowed for the same roles that can write the doc, and only when holat is Qoralama or Xato.
  - `@frappe.whitelist(methods=["POST"]) regenerate(name: str)` — re-runs AI and keeps the result as a draft, whatever the mode.

- [ ] **Step 1: Write the failing tests** (patch `ig_ai.answer`, `instagram._graph`, `save_lead`):
  - `test_process_sinov_never_posts` — rejim Sinov → holat «Qoralama», `_graph` POST not called.
  - `test_process_yoqilgan_posts_reply` — rejim Yoqilgan → POST `"{id}/replies"` called once, holat «Yuborildi».
  - `test_process_reply_to_reply_targets_parent` — `ota_id="P1"`, `username="ali"` → POST path `"P1/replies"` and the message starts with `"@ali "`.
  - `test_process_javobsiz` — `javob_kerak=False` → «Javobsiz», no POST.
  - `test_process_rate_limit_per_customer` — 10 «Yuborildi» docs for the same `mijoz_id` within the hour → the 11th becomes «Qoralama» with `xato` «soatlik limit».
  - `test_process_phone_creates_lead` — the AI returns `telefon` → `save_lead` called with `manba="Instagram"` and `murojaat` set.
  - `test_process_ai_error_marks_xato` — `IgAiError` → «Xato», no POST.
  - `test_send_only_from_draft` — `send` on a «Yuborildi» doc raises `frappe.ValidationError`.
- [ ] **Step 2: Run, expect FAIL** — `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_instagram_process`
- [ ] **Step 3: Implement** `process`, `_post`, `send`, `regenerate` and the form buttons. The JS uses `frappe.call` and then `frm.reload_doc()`.
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): AI izohga javob — Sinov/Yoqilgan, murojaat, qo'lda yuborish"`

### Task 5: Scheduler — `poll()` every minute

**Files:**
- Modify: `marketplace/sotuv/instagram.py`, `marketplace/hooks.py` (`scheduler_events["cron"]["* * * * *"] = ["marketplace.sotuv.instagram.poll"]`)
- Test: `marketplace/sotuv/tests/test_instagram_poll.py`

**Interfaces:**
- **Produces:**
  - `poll() -> None`:
    - Processes shops with `meta_page_id` and `ig_user_id` set and `ig_ai_rejim != "O'chiq"`.
    - Skips a shop if `frappe.cache.get_value(f"mp_ig_pause:{shop}")` is set, and skips everything while `mp_ig_ai_pause` is set.
    - `since = max(cache "mp_ig_since:{shop}", now - LOOKBACK)`.
    - Calls `fetch_comments`, then `store`, then `frappe.enqueue("marketplace.sotuv.instagram.process", queue="short", job_id=f"igx-{name}", deduplicate=True, name=name)`.
    - Sets `mp_ig_since:{shop}` to the poll start time.
    - On `MetaError.code in RATE_CODES`, sets the 15-minute pause. Other errors go to the shop's `meta_holat` and the Error Log.
    - Each shop is in its own try/except with `frappe.db.commit()`.

- [ ] **Step 1: Write the failing tests:**
  - `test_poll_skips_off_shops` — a shop with rejim O'chiq → `fetch_comments` not called.
  - `test_poll_rate_limit_pauses_shop` — `MetaError(code=4)` → the cache pause key is set and the next `poll()` skips the shop.
  - `test_poll_enqueues_new_only` — 2 comments, one already stored → `enqueue` called once.
- [ ] **Step 2: Run, expect FAIL** — `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_instagram_poll`
- [ ] **Step 3: Implement `poll` and register the cron.**
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): Instagram izohlari har daqiqada tekshiriladi"`

### Task 6: Connect — save the IG account and ad account; 10 permissions in the dialog

**Files:**
- Modify: `marketplace/sotuv/meta.py` — in `connect()`, keep `long_token` and pass it to a new `_link_instagram(shop, page, user_token)`, called from `_attach` after the page is saved.
- Modify: `marketplace/marketplace/doctype/shop/shop.js` — permissions list in `marketplace_meta_connect` becomes the spec's 10; show `ig_username` and `meta_ad_account` in the «Ulandi» message.
- Test: `marketplace/sotuv/tests/test_meta_instagram.py`

**Interfaces:**
- **Produces:**
  - `_link_instagram(shop: str, page: dict, user_token: str) -> str | None`. It returns a warning text or `None`.
    - `GET {page_id} fields=instagram_business_account{id,username}` with the page token → sets `ig_user_id` and `ig_username`.
    - `GET me/adaccounts fields=account_id,name,account_status` with the user token → if exactly one account has `account_status == 1`, sets `meta_ad_account = "act_" + account_id`.
    - Otherwise the warning lists the names, so the admin fills `meta_ad_account` by hand.
    - A missing IG account → warning «Sahifaga Instagram professional akkaunt ulanmagan».
    - Never throws, so the lead-form connection keeps working.

- [ ] **Step 1: Write the failing tests:**
  - `test_link_instagram_sets_ids` — sets `ig_user_id`, `ig_username` and `meta_ad_account="act_123"`.
  - `test_link_instagram_two_ad_accounts_warns` — 2 active accounts → `meta_ad_account` unset and the warning contains both names.
  - `test_link_instagram_no_ig_warns` — no `instagram_business_account` → warning, no exception.
- [ ] **Step 2: Run, expect FAIL** — `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_meta_instagram`
- [ ] **Step 3: Implement and update the dialog text.**
- [ ] **Step 4: Run, expect PASS**
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): Meta ulashda Instagram akkaunt va reklama kabineti saqlanadi"`

### Task 7: Direct (DM) — collect, reply to the same sender, operator takeover

**Files:**
- Create: `marketplace/sotuv/instagram_dm.py`
- Modify: `marketplace/sotuv/instagram.py` — `_deliver` gets a DM branch; `poll` also calls `instagram_dm.fetch_messages` and stores with `turi="DM"`.
- Test: `marketplace/sotuv/tests/test_instagram_dm.py`

**Interfaces:**
- **Consumes:** `meta._graph`, `meta._page_token`, and from Task 3/4: `instagram.store`, `instagram.process`, `instagram._deliver`. Shop fields `meta_page_id`, `ig_user_id`.
- **Produces:**
  - `HUMAN_PAUSE = 24 * 3600`
  - `fetch_messages(shop: str, since_ts: int) -> list[dict]`:
    - Calls `GET {page_id}/conversations platform=instagram fields=id,updated_time,messages.limit(10){id,message,created_time,from{id,username}} limit=25` with the page token.
    - Skips conversations with `updated_time < since_ts`.
    - Returns customer messages newer than `since_ts` with non-empty text, as `{"id", "parent_id": None, "text", "username", "from_id", "timestamp", "media_id": None, "havola": None, "suhbat_id": conversation id}`.
    - A shop-sent message whose `id` is not any Instagram Xabar `javob_id` and that is newer than the customer's last message is treated as an operator reply. It sets `frappe.cache.set_value(f"mp_ig_human:{shop}:{customer_id}", 1, expires_in_sec=HUMAN_PAUSE)`.
  - `history(doc) -> list[dict]` — last 10 Instagram Xabar rows of type DM for the same `shop` and `mijoz_id`, oldest first. Each row gives `{"kim": "Mijoz", "matn": matn}`, plus `{"kim": "Do'kon", "matn": ai_javob}` when holat is «Yuborildi».
  - `send_dm(shop: str, doc) -> str` — `POST {page_id}/messages` with `recipient=json.dumps({"id": doc.mijoz_id})`, `message=json.dumps({"text": doc.ai_javob})` and the page token. Returns `message_id`.
  - `is_human_paused(shop: str, mijoz_id: str) -> bool`
- **Changes in `instagram.py`:**
  - `_deliver` routes `turi == "DM"` to `instagram_dm.send_dm`.
  - `process` leaves a DM as «Qoralama» with `xato` «Operator suhbatda» when `is_human_paused`.

- [ ] **Step 1: Write the failing tests** (patch `_graph`):
  - `test_dm_fetch_customer_messages_only` — a conversation with 2 customer messages and 1 of our own (its id equals a stored `javob_id`) → 2 returned; no pause set.
  - `test_dm_operator_message_pauses_ai` — the newest message is from the shop and its id is unknown → the `mp_ig_human:{shop}:{customer}` key is set. A following `process` of that customer's DM in Yoqilgan mode → «Qoralama», no POST.
  - `test_dm_send_targets_sender` — `send_dm` POSTs to `"{page_id}/messages"`, and `recipient` decodes to `{"id": mijoz_id}`.
  - `test_dm_history_order` — 3 stored DMs → `history` returns them oldest first with the «Do'kon» turns included.
  - `test_poll_includes_dms` — `poll()` with one new comment and one new DM → `enqueue` called twice.
- [ ] **Step 2: Run, expect FAIL** — `bench --site marketplace.local run-tests --module marketplace.sotuv.tests.test_instagram_dm`
- [ ] **Step 3: Implement `instagram_dm.py` and the `instagram.py` hooks.**
- [ ] **Step 4: Run Task 4, 5 and 7 tests, expect PASS** — run the `test_instagram_process`, `test_instagram_poll` and `test_instagram_dm` modules.
- [ ] **Step 5: Commit** — `git commit -m "feat(sotuv): Instagram Direct — AI o'sha mijozga javob beradi, operator yozsa jim turadi"`

### Task 8: Sidebar link, full test run, local smoke test, deploy notes

**Files:**
- Modify: `marketplace/sotuv/sidebar/sotuv/sotuv.json` — add the item «Instagram izohlar» → List «Instagram Xabar» after «Murojaatlar».

- [ ] **Step 1: Run all new test modules together.** All of them must PASS:
  - `test_instagram_model`
  - `test_ig_ai`
  - `test_instagram_fetch`
  - `test_instagram_process`
  - `test_instagram_poll`
  - `test_meta_instagram`
  - `test_instagram_dm`
- [ ] **Step 2: Local smoke test**
  - Run `(nohup bench start > $SCR/bench.log 2>&1 &)`.
  - Check that the Shop form shows the «Instagram AI» section and that `/desk/instagram-xabar` lists records.
  - In `bench --site marketplace.local console`, run `marketplace.sotuv.ig_ai.answer("Pandoo", "Narxi qancha?")`. It needs the local Gemini key; skip it if the key is absent. Expected: a reply that starts with «Assalomu alaykum» and contains no quantity.
  - Stop the bench by its honcho pgid.
- [ ] **Step 3: Commit, then push per the deploy flow.**
  - Push: `git push origin HEAD:main HEAD:feat/ombor-excel-telegram`.
  - The user runs the server pull, migrate and restart command.
- [ ] **Step 4: Prod rollout checklist (user + Claude):**
  1. Reconnect Pandoo with the 10 permissions; the result shows `ig_username` and the ad account.
  2. Fill «AI uchun ma'lumot» (Claude drafts it).
  3. Set rejim to «Sinov».
  4. From a personal account, comment on a Panda Books post and send a DM. Within 2 minutes both appear as «Qoralama» in «Instagram izohlar».
  5. Review the drafts, then switch to «Yoqilgan».
  6. If Meta rejects posting in development mode, add the app icon and switch the app to Live.
