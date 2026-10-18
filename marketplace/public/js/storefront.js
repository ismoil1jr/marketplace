/* Mijoz sahifalari: savat, filtr, galereya. Kutubxonasiz, oddiy JS.
   Savat brauzerda (localStorage) saqlanadi: { "kod": soni }. Narx har doim serverdan olinadi. */
(() => {
	"use strict";

	const SF = window.SF;
	const $ = (sel, root = document) => root.querySelector(sel);
	const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
	// Ko'rib chiqish rejimi (?layout=story) ichki havolalar bo'ylab saqlanadi
	const withPreview = (url) => {
		if (!SF.preview) return url;
		const u = new URL(url, location.origin);
		u.searchParams.set("layout", SF.preview);
		return u.pathname + u.search + u.hash;
	};
	if (SF.preview) {
		document.querySelectorAll(`a[href^="${SF.base}"]`).forEach((a) => (a.href = withPreview(a.getAttribute("href"))));
	}

	const fmt = (n) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so‘m";

	// ---------- Saqlash (xususiy rejimda localStorage ishlamasligi mumkin) ----------
	const store = {
		get(key, fallback) {
			try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
		},
		set(key, value) {
			try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* xotirasiz ham ishlayveradi */ }
		},
	};

	const CART_KEY = `mp_cart:${SF.shop}`;
	const META_KEY = `mp_meta:${SF.shop}`;
	const FAV_KEY = `mp_fav:${SF.shop}`;

	// meta: savat paneli darhol chizilishi uchun nom/narx/rasm nusxasi
	const meta = Object.assign(store.get(META_KEY, {}), SF.catalog || {});
	store.set(META_KEY, meta);

	const unitPrice = (code, q) => {
		const m = meta[code] || {};
		return m.ws && q >= m.wsmin ? m.ws : m.price || 0;
	};

	const cart = {
		all: () => store.get(CART_KEY, {}),
		qty: (code) => cart.all()[code] || 0,
		set(code, qty) {
			const c = cart.all();
			if (qty > 0) c[code] = Math.min(qty, 99); else delete c[code];
			store.set(CART_KEY, c);
			renderCartSummary();
		},
		add: (code, n = 1) => cart.set(code, cart.qty(code) + n),
		count: () => Object.values(cart.all()).reduce((a, b) => a + b, 0),
		total: () => Object.entries(cart.all()).reduce((s, [code, q]) => s + unitPrice(code, q) * q, 0),
	};

	function toast(text) {
		const el = $("#sf-toast");
		if (!el) return;
		el.textContent = text;
		el.classList.add("is-on");
		clearTimeout(toast.t);
		toast.t = setTimeout(() => el.classList.remove("is-on"), 1800);
	}

	// ---------- Savat xulosasi: badge, pastki panel, noutbukdagi o'ng panel ----------
	function renderCartSummary() {
		const items = cart.all();
		const count = cart.count();
		const label = `${count} ta mahsulot`;

		$$("[data-cart-count]").forEach((el) => { el.textContent = count; el.hidden = !count; });
		$$("[data-cart-total]").forEach((el) => (el.textContent = fmt(cart.total())));
		$$("[data-cart-items-label]").forEach((el) => (el.textContent = count ? label : ""));
		$$("[data-cart-qty-label]").forEach((el) => (el.textContent = `${count} ta`));
		const models = Object.keys(items).length;
		$$("[data-cart-summary]").forEach((el) => (el.textContent = `${count} dona · ${models} ta model`));
		renderRowSteppers(items);
		const bar = $("[data-cartbar]");
		if (bar) bar.hidden = !count;

		$$("[data-add]").forEach((btn) => {
			const q = items[btn.dataset.add] || 0;
			const badge = $(".sf-add__qty", btn);
			badge.textContent = q;
			badge.hidden = !q;
		});

		const lines = $("[data-side-lines]");
		if (lines) {
			const rows = Object.entries(items).filter(([code]) => meta[code]);
			lines.innerHTML = rows.length ? "" : '<p class="sf-muted">Savat bo‘sh</p>';
			for (const [code, q] of rows) {
				const m = meta[code];
				const row = document.createElement("a");
				row.className = "sf-pline";
				row.href = withPreview(`${SF.base}/p/${encodeURIComponent(code)}`);
				const img = m.thumb ? document.createElement("img") : document.createElement("span");
				if (m.thumb) { img.src = m.thumb; img.alt = ""; } else img.className = "sf-pline__ph";
				const text = document.createElement("span");
				const name = document.createElement("b");
				name.textContent = m.name;
				const small = document.createElement("small");
				small.textContent = [m.variant, `${q} dona`].filter(Boolean).join(" · ");
				text.append(name, small);
				const price = document.createElement("strong");
				price.textContent = fmt(unitPrice(code, q) * q);
				row.append(img, text, price);
				lines.append(row);
			}
			$("[data-side-total]").hidden = !rows.length;
		}
	}

	// ---------- C shablon: qatordagi "Qo'shish" → son tanlagich ----------
	function renderRowSteppers(items) {
		$$("[data-row-qty]").forEach((box) => {
			const q = items[box.dataset.rowQty] || 0;
			$(".kt-add", box).hidden = q > 0;
			$(".kt-stepper", box).hidden = q === 0;
			$("[data-row-out]", box).textContent = q;
		});
	}

	function initRowSteppers() {
		$$("[data-row-qty]").forEach((box) => {
			const code = box.dataset.rowQty;
			const max = +box.dataset.max || 99;
			$$("[data-row-step]", box).forEach((b) =>
				b.addEventListener("click", () => {
					const next = cart.qty(code) + +b.dataset.rowStep;
					if (next > max) return toast(`Omborda ${max} ta bor`);
					cart.set(code, next);
				})
			);
		});
		$$("[data-price-mode]").forEach((btn) =>
			btn.addEventListener("click", () => {
				const ws = btn.dataset.priceMode === "wholesale";
				$$("[data-price-mode]").forEach((b) => b.classList.toggle("is-active", b === btn));
				$$("[data-ws]").forEach((el) => (el.hidden = !ws));
				$$("[data-retail-note]").forEach((el) => (el.hidden = !ws));
				$$("[data-ws-note]").forEach((el) => (el.hidden = ws));
				$$("[data-ws]").forEach((el) => (el.parentElement.querySelector("[data-retail]").hidden = ws));
			})
		);
	}

	// ---------- Sevimlilar ----------
	const favs = new Set(store.get(FAV_KEY, []));
	const onFavChange = [];

	function initFavorites() {
		const syncFilter = () => $$("[data-fav-filter]").forEach((b) => (b.hidden = !favs.size));
		syncFilter();
		onFavChange.push(syncFilter);
		$$("[data-fav]").forEach((btn) => {
			btn.classList.toggle("is-on", favs.has(btn.dataset.fav));
			btn.addEventListener("click", (e) => {
				e.preventDefault();
				const code = btn.dataset.fav;
				favs.has(code) ? favs.delete(code) : favs.add(code);
				$$(`[data-fav="${CSS.escape(code)}"]`).forEach((b) => b.classList.toggle("is-on", favs.has(code)));
				store.set(FAV_KEY, [...favs]);
				toast(favs.has(code) ? "Sevimlilarga qo‘shildi" : "Sevimlilardan olindi");
				onFavChange.forEach((fn) => fn());
			});
		});
	}

	// ---------- Katalog: kategoriya, qidiruv, narx, saralash ----------
	function initCatalog() {
		const grid = $("[data-grid]");
		if (!grid) return;
		const cards = $$(".sf-card", grid);
		const state = { group: "", q: "", min: 0, max: Infinity, sort: "new" };

		function matchesGroup(card) {
			switch (state.group) {
				case "": return true;
				case "__fav": return favs.has(card.dataset.code);
				case "__new": return !!card.dataset.new;
				case "__sale": return !!card.dataset.sale;
				default: return card.dataset.group === state.group;
			}
		}

		function apply() {
			let shown = 0;
			for (const card of cards) {
				const price = +card.dataset.price;
				const ok =
					matchesGroup(card) &&
					(!state.q || card.dataset.name.includes(state.q)) &&
					price >= state.min && price <= state.max;
				card.hidden = !ok;
				if (ok) shown++;
			}
			const sorted = [...cards].sort((a, b) => {
				if (state.sort === "cheap") return a.dataset.price - b.dataset.price;
				if (state.sort === "expensive") return b.dataset.price - a.dataset.price;
				return b.dataset.created.localeCompare(a.dataset.created);
			});
			grid.append(...sorted);
			const counter = $("[data-result-count]");
			if (counter) counter.textContent = `${shown} ta mahsulot`;
			$("[data-no-results]").hidden = shown > 0;
			const active = state.group || state.q || state.min > 0 || state.max !== Infinity;
			$$("[data-reset-filters]").forEach((b) => (b.hidden = !active));
		}

		onFavChange.push(() => {
			if (state.group === "__fav" && !favs.size) setGroup("");
			else if (state.group === "__fav") apply();
		});

		function setGroup(group) {
			state.group = group;
			$$("button[data-group]").forEach((b) => b.classList.toggle("is-active", b.dataset.group === group));
			apply();
		}

		$$("button[data-group]").forEach((b) => b.addEventListener("click", () => setGroup(b.dataset.group)));
		$$("[data-group-jump]").forEach((b) =>
			b.addEventListener("click", () => {
				setGroup(b.dataset.groupJump);
				grid.scrollIntoView({ behavior: "smooth", block: "start" });
			})
		);

		let t;
		$$("[data-search]").forEach((input) =>
			input.addEventListener("input", () => {
				clearTimeout(t);
				t = setTimeout(() => {
					state.q = input.value.trim().toLowerCase();
					$$("[data-search]").forEach((other) => other !== input && (other.value = input.value));
					apply();
				}, 120);
			})
		);
		// B shablon: qidiruv maydoni tugma bilan ochiladi
		$("[data-toggle-search]")?.addEventListener("click", () => {
			const box = $("[data-search-box]");
			box.hidden = !box.hidden;
			if (!box.hidden) $("input", box).focus();
		});

		// B shablon: kartochka ichidagi rasmlarni surish va "1 / 4" hisoblagich
		$$("[data-slides]").forEach((track) => {
			const counter = $("[data-counter]", track.parentElement);
			if (!counter) return;
			const total = track.children.length;
			track.addEventListener("scroll", () => {
				counter.textContent = `${Math.round(track.scrollLeft / track.clientWidth) + 1} / ${total}`;
			}, { passive: true });
		});

		$("[data-focus-search]")?.addEventListener("click", () => {
			const input = $(".sf-search--inline input");
			input.scrollIntoView({ behavior: "smooth", block: "center" });
			input.focus({ preventScroll: true });
		});

		const min = $("[data-min]"), max = $("[data-max]");
		const onRange = () => {
			state.min = +min.value || 0;
			state.max = +max.value || Infinity;
			apply();
		};
		min?.addEventListener("input", onRange);
		max?.addEventListener("input", onRange);
		// Narx, kategoriya ("Hammasi"), qidiruv va sevimlilar filtri — hammasi boshlang'ich holatga
		$$("[data-reset-filters]").forEach((b) =>
			b.addEventListener("click", () => {
				Object.assign(state, { q: "", min: 0, max: Infinity });
				if (min) min.value = "";
				if (max) max.value = "";
				$$("[data-search]").forEach((input) => (input.value = ""));
				clearTimeout(t);
				setGroup("");
			})
		);
		$("[data-sort]")?.addEventListener("change", (e) => { state.sort = e.target.value; apply(); });

		$$("[data-add]").forEach((btn) =>
			btn.addEventListener("click", () => {
				cart.add(btn.dataset.add);
				btn.classList.remove("is-bump");
				void btn.offsetWidth;
				btn.classList.add("is-bump");
				toast("Savatga qo‘shildi");
			})
		);
	}

	// ---------- Mahsulot sahifasi ----------
	function initProduct() {
		const track = $("[data-gallery]");
		const dots = $$("[data-dots] span");
		if (track && dots.length) {
			track.addEventListener("scroll", () => {
				const i = Math.round(track.scrollLeft / track.clientWidth);
				dots.forEach((d, k) => d.classList.toggle("is-active", k === i));
			}, { passive: true });
		}

		$("[data-share]")?.addEventListener("click", async () => {
			const data = { title: document.title, url: location.href };
			try {
				if (navigator.share) await navigator.share(data);
				else { await navigator.clipboard.writeText(location.href); toast("Havola nusxalandi"); }
			} catch { /* foydalanuvchi bekor qildi */ }
		});

		const buy = $("[data-buy]");
		if (!buy) return;
		const out = $("[data-qty]", buy);
		const addBtn = $("[data-buy-add]", buy);
		let max = +buy.dataset.max || 99;
		let qty = 1;
		let code = buy.dataset.code; // variantli mahsulotda: tanlangan variant kodi
		const productCode = buy.dataset.code;
		let variantLabel = "";

		// ---- Rang va o'lcham (PDF 4-sahifa) ----
		const box = $("[data-variants]");
		if (box) {
			const opt = JSON.parse(box.dataset.variants);
			const hasColors = opt.colors.length > 0, hasSizes = opt.sizes.length > 0;
			const sel = { color: "", size: "" };
			const key = (c, s) => `${c}|${s}`;
			const avail = (c, s) => (opt.variants[key(c, s)]?.qty || 0) > 0;
			// birinchi mavjud kombinatsiyani oldindan tanlaymiz
			const first = Object.entries(opt.variants).find(([, v]) => v.qty > 0);
			if (first) [sel.color, sel.size] = first[0].split("|");

			function render() {
				$$("[data-color]", box).forEach((b) => {
					b.classList.toggle("is-active", b.dataset.color === sel.color);
					b.classList.toggle("is-out", !opt.sizes.some((s) => avail(b.dataset.color, s)) && !avail(b.dataset.color, ""));
				});
				$$("[data-size]", box).forEach((b) => {
					b.classList.toggle("is-active", b.dataset.size === sel.size);
					b.classList.toggle("is-out", !avail(hasColors ? sel.color : "", b.dataset.size));
				});
				const lab = $("[data-color-label]", box);
				if (lab) lab.textContent = sel.color || "tanlang";
				const v = opt.variants[key(hasColors ? sel.color : "", hasSizes ? sel.size : "")];
				const ready = (!hasColors || sel.color) && (!hasSizes || sel.size);
				const stockEl = $("[data-variant-stock]", box);
				if (!ready) { stockEl.textContent = "Rang va o‘lchamni tanlang"; addBtn.disabled = true; return; }
				if (!v || v.qty <= 0) { stockEl.textContent = "Bu variant tugagan"; addBtn.disabled = true; return; }
				code = v.code;
				max = v.qty;
				variantLabel = [hasColors && sel.color, hasSizes && sel.size].filter(Boolean).join(" · ");
				stockEl.textContent = v.qty <= 5 ? `Omborda ${v.qty} ta qoldi` : "Omborda bor";
				addBtn.disabled = false;
				if (qty > max) { qty = max; out.textContent = qty; }
			}
			$$("[data-color]", box).forEach((b) => b.addEventListener("click", () => { sel.color = b.dataset.color; render(); }));
			$$("[data-size]", box).forEach((b) => b.addEventListener("click", () => { sel.size = b.dataset.size; render(); }));
			render();
		}

		$$("[data-step]", buy).forEach((b) =>
			b.addEventListener("click", () => {
				qty = Math.max(1, Math.min(max, qty + +b.dataset.step));
				out.textContent = qty;
			})
		);
		addBtn?.addEventListener("click", () => {
			if (code !== productCode) {
				// variant uchun savat paneli ma'lumoti (nom, narx, rasm asosiy mahsulotdan)
				meta[code] = { ...meta[productCode], variant: variantLabel };
				store.set(META_KEY, meta);
			}
			cart.add(code, qty);
			toast(`Savatga qo‘shildi${variantLabel ? ` (${variantLabel})` : ""} · ${cart.count()} ta mahsulot`);
		});
	}

	// ---------- Savat sahifasi: narxlar serverdan ----------
	async function initCart() {
		const box = $("[data-cart-lines]");
		if (!box) return;
		const tpl = $("#sf-line-tpl");

		async function load() {
			const lines = Object.entries(cart.all()).map(([code, qty]) => ({ code, qty }));
			if (!lines.length) return render({ lines: [], total: 0 });
			const url = `/api/method/marketplace.api.get_cart?shop=${encodeURIComponent(SF.shop)}&lines=${encodeURIComponent(JSON.stringify(lines))}`;
			try {
				const res = await fetch(url, { headers: { Accept: "application/json" } });
				if (!res.ok) throw new Error(res.status);
				render((await res.json()).message);
			} catch {
				box.innerHTML = '<p class="sf-muted sf-center sf-pad">Savatni yuklab bo‘lmadi. Internetni tekshirib, sahifani yangilang.</p>';
			}
		}

		function render(data) {
			// Serverda yo'q yoki tugagan tovarlarni savatdan tozalaymiz, narxni yangilaymiz
			const fresh = {};
			for (const l of data.lines) {
				if (l.qty > 0) fresh[l.code] = l.qty;
				meta[l.code] = { name: l.name, price: l.retail_price ?? l.price, thumb: l.thumb, variant: l.variant, ws: l.wholesale_price, wsmin: l.wholesale_min };
			}
			const removed = Object.keys(cart.all()).filter((c) => !(c in fresh)).length;
			store.set(CART_KEY, fresh);
			store.set(META_KEY, meta);

			box.innerHTML = "";
			if (!data.lines.length) {
				box.innerHTML = `<div class="sf-empty"><p>Savat bo‘sh</p><a class="sf-btn" href="${withPreview(SF.base)}">Xaridni boshlash</a></div>`;
			}
			for (const l of data.lines) {
				const node = tpl.content.cloneNode(true);
				const href = withPreview(`${SF.base}/p/${encodeURIComponent(l.code)}`);
				$$("[data-link]", node).forEach((a) => (a.href = href));
				const img = $("[data-img]", node);
				if (l.thumb) img.src = l.thumb; else img.remove();
				$("[data-name]", node).textContent = l.name;
				const vEl = $("[data-variant]", node);
				if (l.variant) { vEl.textContent = l.variant; vEl.hidden = false; }
				$("[data-price]", node).textContent = fmt(l.price);
				$("[data-qty]", node).textContent = l.qty;
				const note = $("[data-note]", node);
				if (l.max_qty < 99 && l.qty >= l.max_qty) { note.hidden = false; note.textContent = `Omborda ${l.max_qty} ta qoldi`; }
				$$("[data-line-step]", node).forEach((b) =>
					b.addEventListener("click", () => {
						const next = l.qty + +b.dataset.lineStep;
						if (next > l.max_qty) return toast(`Omborda ${l.max_qty} ta bor`);
						cart.set(l.code, next);
						load();
					})
				);
				box.append(node);
			}
			if (removed) toast("Ba’zi tovarlar tugagani uchun savatdan olindi");

			const count = data.lines.reduce((s, l) => s + l.qty, 0);
			for (const sel of ["[data-summary]", "[data-checkout]", "[data-checkout-form]", "[data-delivery]"]) {
				const el = $(sel);
				if (el) el.hidden = !count;
			}
			$("[data-summary-label]").textContent = `Mahsulotlar (${count})`;
			$("[data-summary-amount]").textContent = fmt(data.total);
			$("[data-summary-total]").textContent = fmt(data.total);
		}

		load();
	}

	// ---------- Server bilan ishlash ----------
	async function api(method, data, httpMethod = "POST") {
		const url = `/api/method/marketplace.api.${method}`;
		const opts = { method: httpMethod, headers: { Accept: "application/json" } };
		if (httpMethod === "POST") {
			opts.headers["Content-Type"] = "application/json";
			if (SF.csrf) opts.headers["X-Frappe-CSRF-Token"] = SF.csrf;
			opts.body = JSON.stringify(data || {});
		}
		const res = await fetch(url, opts);
		const body = await res.json().catch(() => ({}));
		if (!res.ok) {
			let msg = "Xatolik yuz berdi. Qayta urinib ko‘ring.";
			try {
				const first = JSON.parse(JSON.parse(body._server_messages)[0]);
				msg = first.message.replace(/<[^>]+>/g, "");
			} catch { /* xabarsiz xato */ }
			if (res.status === 429) msg = "Juda ko‘p urinish. Birozdan keyin qayta urinib ko‘ring.";
			throw new Error(msg);
		}
		return body.message;
	}

	// ---------- Kirish: telefon → Telegram kodi → tasdiqlash ----------
	// Belgilash: macros.html auth_form(). Savat, "Buyurtmalarim" va buyurtma sahifasida ishlatiladi.
	// onUser(me) — kirgandan/chiqqandan keyin (me = null — chiqdi). Qaytaradi: setUser (tashqaridan holatni berish uchun).
	function initAuth(root, onUser = () => {}) {
		const guest = $("[data-auth-guest]", root), user = $("[data-auth-user]", root);
		const phoneIn = $("[data-phone]", root), sendBtn = $("[data-send-code]", root);
		const otpBox = $("[data-otp]", root), boxes = $("[data-otp-boxes]", root);
		const note = $("[data-otp-note]", root), resend = $("[data-resend]", root), dev = $("[data-otp-dev]", root);
		const botBtn = $("[data-otp-bot]", root), botBox = $("[data-otp-botbox]", root);
		// Kod kutilayotgan holat: mijoz Telegram'ga o'tib qaytsa yoki sahifa yangilansa ham saqlanadi
		const PENDING_KEY = "sf_auth_pending";
		const first = $("[data-first]", root), last = $("[data-last]", root);
		let timer, verifying = false;

		const setUser = (me) => {
			guest.hidden = !!me;
			user.hidden = !me;
			if (me) {
				$("[data-me-name]", user).textContent = me.name;
				$("[data-me-phone]", user).textContent = me.phone_masked;
			} else {
				restorePending();
			}
			onUser(me);
		};

		// telefon: "901234567" -> "90 123 45 67"
		phoneIn.addEventListener("input", () => {
			const d = phoneIn.value.replace(/\D/g, "").slice(0, 9);
			phoneIn.value = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean).join(" ");
		});

		function buildBoxes(n) {
			boxes.innerHTML = "";
			for (let i = 0; i < n; i++) {
				const inp = document.createElement("input");
				// maxLength qo'yilmaydi: aks holda paste va telefonning "kodni qo'yish" avtoto'ldirishi 1 raqamga kesiladi
				Object.assign(inp, { inputMode: "numeric", autocomplete: i === 0 ? "one-time-code" : "off" });
				inp.setAttribute("aria-label", `Kod, ${i + 1}-raqam`);
				boxes.append(inp);
			}
			const all = $$("input", boxes);
			all.forEach((inp, i) => {
				inp.addEventListener("input", () => {
					const digits = inp.value.replace(/\D/g, "");
					if (digits.length > 1) { // paste yoki SMS/Telegram avtoto'ldirish
						digits.split("").slice(0, n - i).forEach((d, k) => (all[i + k].value = d));
					} else inp.value = digits.slice(-1);
					const next = all.find((x) => !x.value);
					(next || all[n - 1]).focus();
					if (all.every((x) => x.value)) verify(all.map((x) => x.value).join(""));
				});
				inp.addEventListener("keydown", (e) => {
					if (e.key === "Backspace" && !inp.value && i > 0) all[i - 1].focus();
				});
			});
			all[0].focus();
		}

		function countdown(sec, masked, bot) {
			clearInterval(timer);
			resend.hidden = true;
			const where = bot.username ? `@${bot.username} Telegram botiga` : "Telegram'ga";
			const tick = () => {
				const m = Math.floor(sec / 60), s = String(sec % 60).padStart(2, "0");
				note.textContent = bot.link
					? `Kod ${where} keladi · ${m}:${s}`
					: `Kod ${masked} raqamiga, ${where} yuborildi · ${m}:${s}`;
				if (sec-- <= 0) { clearInterval(timer); note.textContent = `Kod ${masked} raqamiga yuborildi.`; resend.hidden = false; }
			};
			tick();
			timer = setInterval(tick, 1000);
		}

		async function sendCode() {
			if (!first.value.trim()) return toast("Ismingizni yozing");
			if (phoneIn.value.replace(/\D/g, "").length !== 9) return toast("Telefon raqamini to‘liq yozing");
			sendBtn.disabled = true;
			try {
				const r = await api("request_code", { phone: phoneIn.value });
				showPending({
					phone: phoneIn.value, first: first.value, last: last.value, length: r.length, masked: r.masked,
					link: r.bot_link || null, username: r.bot_username || null,
					resend_at: Date.now() + r.resend_after * 1000, until: Date.now() + r.ttl * 1000,
				});
				dev.hidden = !r.dev_code;
				if (r.dev_code) dev.textContent = `TEST rejimi (Telegram token kiritilmagan): kod ${r.dev_code}`;
			} catch (e) {
				toast(e.message);
			} finally {
				sendBtn.disabled = false;
			}
		}

		// Bot bu raqamni hali tanimasa: mijoz botni ochib, raqamini bir marta yuboradi (yo'riqnoma bilan)
		function showPending(p) {
			try { localStorage.setItem(PENDING_KEY, JSON.stringify(p)); } catch (e) {}
			otpBox.hidden = false;
			buildBoxes(p.length);
			if (botBox) {
				botBox.hidden = !p.link;
				if (p.link) botBtn.href = p.link;
				const nameEl = $("[data-otp-botname]", root);
				if (nameEl && p.username) nameEl.textContent = `@${p.username}`;
			}
			countdown(Math.max(0, Math.round((p.resend_at - Date.now()) / 1000)), p.masked, p);
		}

		function restorePending() {
			let p = null;
			try { p = JSON.parse(localStorage.getItem(PENDING_KEY) || "null"); } catch (e) {}
			if (!p || p.until < Date.now()) return;
			phoneIn.value = p.phone || "";
			first.value = first.value || p.first || "";
			last.value = last.value || p.last || "";
			showPending(p);
		}

		async function verify(code) {
			if (verifying) return;
			verifying = true;
			try {
				const me = await api("verify_code", {
					phone: phoneIn.value, code, first_name: first.value, last_name: last.value,
				});
				clearInterval(timer);
				try { localStorage.removeItem(PENDING_KEY); } catch (e) {}
				toast("Telefon tasdiqlandi ✓");
				setUser(me);
			} catch (e) {
				toast(e.message);
				$$("input", boxes).forEach((x) => (x.value = ""));
				$("input", boxes)?.focus();
			} finally {
				verifying = false;
			}
		}

		sendBtn.addEventListener("click", sendCode);
		resend.addEventListener("click", sendCode);
		$("[data-logout]", root).addEventListener("click", async () => {
			await api("logout", {}).catch(() => {});
			setUser(null);
		});
		return setUser;
	}

	// ---------- Rasmiylashtirish: Telegram kodi → buyurtma ----------
	function initCheckout() {
		const form = $("[data-checkout-form]");
		if (!form) return;
		const btn = $("[data-checkout-btn]"), hint = $("[data-checkout-hint]");
		const addressField = $("[data-address-field]"), address = $("[data-address]");

		const setUser = initAuth(form, (me) => {
			btn.disabled = !me;
			hint.hidden = !!me;
		});

		$$("input[name=delivery]").forEach((r) =>
			r.addEventListener("change", () => (addressField.hidden = r.value !== "Kuryer" || !r.checked))
		);

		btn.addEventListener("click", async () => {
			const delivery = $("input[name=delivery]:checked").value;
			if (delivery === "Kuryer" && address.value.trim().length < 5) {
				address.focus();
				return toast("Yetkazib berish manzilini yozing");
			}
			btn.disabled = true;
			btn.textContent = "Buyurtma yaratilmoqda…";
			try {
				const lines = Object.entries(cart.all()).map(([code, qty]) => ({ code, qty }));
				const r = await api("place_order", { shop: SF.shop, lines, delivery_method: delivery, address: address.value });
				store.set(CART_KEY, {}); // buyurtma yaratildi — savat tozalanadi
				location.href = withPreview(r.url);
			} catch (e) {
				toast(e.message);
				btn.disabled = false;
				btn.textContent = "To‘lovga o‘tish";
			}
		});

		api("me", null, "GET").then(setUser).catch(() => setUser(null));
	}

	// ---------- "Buyurtmalarim" va buyurtma sahifasi: kirish va chiqish ----------
	// Sahifa serverda chiziladi: kirilgach yoki chiqilgach shunchaki qayta yuklanadi.
	function initAccount() {
		const box = $("[data-auth-page]");
		if (box) initAuth(box, (me) => me && setTimeout(() => location.reload(), 400));
		$("[data-orders-logout]")?.addEventListener("click", async (e) => {
			e.currentTarget.disabled = true;
			await api("logout", {}).catch(() => {});
			location.reload();
		});
	}

	// ---------- To'lov sahifasi ----------
	function initPayment() {
		const box = $("[data-pay]");
		if (!box) return;
		const btn = $("[data-pay-btn]");
		const label = () => {
			const m = $("input[name=pay]:checked", box)?.value;
			btn.disabled = !m;
			btn.textContent = m === "Naqd" || !m ? "Buyurtmani tasdiqlash" : `${btn.dataset.total} to‘lash`;
		};
		$$("input[name=pay]", box).forEach((r) => r.addEventListener("change", label));
		label();
		btn.addEventListener("click", async () => {
			const method = $("input[name=pay]:checked", box)?.value;
			btn.disabled = true;
			try {
				const r = await api("choose_payment", { order: box.dataset.order, method });
				if (r.redirect) location.href = r.redirect;
				else location.reload();
			} catch (e) {
				toast(e.message);
				btn.disabled = false;
			}
		});
	}

	// Tayyor savat havolasi: /s/dokon?cart=kod:2,kod2:1 — sotuvchi Direct'da mijozga yuborishi mumkin
	function applyCartLink() {
		const params = new URLSearchParams(location.search);
		const raw = params.get("cart");
		if (!raw) return;
		for (const part of raw.split(",")) {
			const [code, qty] = part.split(":");
			if (code) cart.add(code.trim(), Math.max(1, parseInt(qty, 10) || 1));
		}
		params.delete("cart");
		history.replaceState(null, "", location.pathname + (params.size ? `?${params}` : "") + location.hash);
	}

	// ---------- Karusel: 5 soniyada o'zi aylanadi, barmoq bilan surilsa to'xtaydi ----------
	function initCarousel() {
		const root = $("[data-carousel]");
		const track = $("[data-carousel-track]");
		if (!root || !track || track.children.length < 2) return;
		const dots = $$("[data-carousel-dot]", root);
		const count = track.children.length;
		let current = 0;
		let timer = null;
		const go = (i) => track.scrollTo({ left: ((i + count) % count) * track.clientWidth });
		track.addEventListener("scroll", () => {
			current = Math.round(track.scrollLeft / track.clientWidth);
			dots.forEach((d, i) => d.setAttribute("aria-selected", String(i === current)));
		}, { passive: true });
		dots.forEach((d) => d.addEventListener("click", () => { stop(); go(+d.dataset.carouselDot); }));
		const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
		const start = () => { if (!reduce && !timer) timer = setInterval(() => go(current + 1), 5000); };
		const stop = () => { clearInterval(timer); timer = null; };
		track.addEventListener("pointerdown", stop, { passive: true });
		track.addEventListener("touchstart", stop, { passive: true });
		document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
		start();
	}

	applyCartLink();
	initCarousel();
	renderCartSummary();
	initFavorites();
	initCatalog();
	initProduct();
	initCart();
	initRowSteppers();
	initCheckout();
	initAccount();
	initPayment();

	// Boshqa tabda savat o'zgarsa, bu yerda ham yangilansin
	window.addEventListener("storage", (e) => e.key === CART_KEY && renderCartSummary());
})();
