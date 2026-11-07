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
	// "To'lovga o'tish" bosilgan buyurtma: {order, lines}. Savat buyurtma yakunlangandagina (to'langan / naqd
	// tasdiqlangan) bo'shaydi — to'lov sahifasidan chiqib ketsa yoki orqaga qaytsa, savat joyida turadi
	const PENDING_KEY = `mp_pending:${SF.shop}`;

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

	// Tasdiq oynasi (telefonda pastdan chiqadi): «Yo'q» — qizil, «Ha» — oddiy. Promise<boolean>
	function confirmSheet({ title, text = "", yes = "Ha", no = "Yo‘q" }) {
		return new Promise((resolve) => {
			const box = document.createElement("div");
			box.className = "sf-share sf-confirm";
			box.innerHTML = `<div class="sf-share__panel" role="alertdialog" aria-modal="true" aria-label="${title}">
				<b>${title}</b>${text ? `<p class="sf-confirm__text">${text}</p>` : ""}
				<div class="sf-confirm__btns">
					<button type="button" class="sf-confirm__no" data-no>${no}</button>
					<button type="button" class="sf-confirm__yes" data-yes>${yes}</button>
				</div>
			</div>`;
			const done = (ok) => { box.remove(); document.removeEventListener("keydown", onKey); resolve(ok); };
			const onKey = (e) => { if (e.key === "Escape") done(false); };
			box.addEventListener("click", (e) => {
				if (e.target === box || e.target.closest("[data-no]")) done(false);
				else if (e.target.closest("[data-yes]")) done(true);
			});
			document.addEventListener("keydown", onKey);
			document.body.append(box);
			$("[data-no]", box).focus();
		});
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
		// Noutbukda o'ng "Savat" paneli faqat savatda narsa bo'lganda (bo'sh panel joy olmasin — kartalar kengroq)
		const layout = $(".sf-layout");
		if (layout) layout.toggleAttribute("data-cart-empty", !count);

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
					if (next > max) return toast(`Faqat ${max} ta qolgan`);
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
		const syncFilter = () => {
			$$("[data-fav-filter]").forEach((b) => (b.hidden = !favs.size));
			$$("[data-fav-count]").forEach((el) => { el.textContent = favs.size; el.hidden = !favs.size; });
		};
		syncFilter();
		onFavChange.push(syncFilter);
		$$("[data-fav-top]").forEach((b) => b.addEventListener("click", () => { if (!favs.size) toast("Sevimlilar bo‘sh — kartadagi ♥ ni bosing"); }));
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
		const state = { group: "", q: "", min: 0, max: Infinity, sort: "new", instock: false };

		function matchesGroup(card) {
			switch (state.group) {
				case "": return true;
				case "__fav": return favs.has(card.dataset.code);
				case "__new": return !!card.dataset.new;
				case "__sale": return !!card.dataset.sale;
				// Ustma-ust: "Telefonlar" tanlansa — Telefonlar › Xiaomi, Telefonlar › Apple ham
				default: return (card.dataset.groups || card.dataset.group || "").split("|").includes(state.group);
			}
		}

		function apply() {
			let shown = 0;
			for (const card of cards) {
				const price = +card.dataset.price;
				const ok =
					matchesGroup(card) &&
					(!state.q || card.dataset.name.includes(state.q)) &&
					price >= state.min && price <= state.max &&
					(!state.instock || card.dataset.instock === "1");
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
			const filters = (state.min > 0 || state.max !== Infinity ? 1 : 0) + (state.instock ? 1 : 0);
			const active = state.group || state.q || filters;
			$$("[data-reset-filters]").forEach((b) => (b.hidden = !active));
			// Katalog: "Filtr" tugmasidagi raqam — nechta filtr yoqilgan
			const badge = $("[data-filter-count]");
			if (badge) { badge.hidden = !filters; badge.textContent = filters; }
		}

		onFavChange.push(() => {
			if (state.group === "__fav" && !favs.size) setGroup("");
			else if (state.group === "__fav") apply();
		});

		// Ustma-ust kategoriyalar: {papka: [ichidagilar]} (storefront._category_tree)
		const cats = SF.cats || {};
		const parentOf = {};
		Object.entries(cats).forEach(([p, kids]) => kids.forEach((k) => (parentOf[k] = p)));
		const pathOf = (g) => { const path = []; for (let x = g; x; x = parentOf[x]) path.unshift(x); return path; };
		// Bosh kategoriyalar tugmalari ostida: yo'l (Telefonlar › Xiaomi) va ichki kategoriyalar
		const sub = document.createElement("nav");
		sub.className = "sf-subcats";
		sub.setAttribute("aria-label", "Ichki kategoriyalar");
		sub.hidden = true;
		const anchor = $(".sf-main .sf-chips") || $(".st-highlights") || $(".kt-tabs") || grid;
		anchor.parentNode.insertBefore(sub, anchor.nextSibling);

		function renderSub(group) {
			const path = group && !group.startsWith("__") ? pathOf(group) : [];
			// Papka tanlangan bo'lsa — uning ichidagilar; oxirgi kategoriya bo'lsa — qo'shnilari
			const folder = cats[group] ? group : parentOf[group];
			const kids = folder ? cats[folder] || [] : [];
			if (!kids.length && path.length < 2) { sub.hidden = true; sub.innerHTML = ""; return; }
			const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
			const crumbs = path.map((p, i) => i < path.length - 1
				? `<button type="button" data-subgroup="${esc(p)}">${esc(p)}</button><span>›</span>`
				: `<b>${esc(p)}</b>`).join("");
			const chips = kids.length
				? `<div class="sf-subcats__chips"><button type="button" class="${group === folder ? "is-active" : ""}" data-subgroup="${esc(folder)}">Hammasi</button>${
					kids.map((k) => `<button type="button" class="${k === group ? "is-active" : ""}" data-subgroup="${esc(k)}">${esc(k)}${cats[k] ? " ›" : ""}</button>`).join("")}</div>`
				: "";
			sub.innerHTML = `<div class="sf-subcats__path">${crumbs}</div>${chips}`;
			sub.hidden = false;
			sub.querySelectorAll("[data-subgroup]").forEach((b) => b.addEventListener("click", () => setGroup(b.dataset.subgroup)));
		}

		function setGroup(group) {
			state.group = group;
			const top = group && !group.startsWith("__") ? pathOf(group)[0] : group;
			$$("button[data-group]").forEach((b) => b.classList.toggle("is-active", b.dataset.group === top));
			renderSub(group);
			apply();
		}

		$$("button[data-group]").forEach((b) => b.addEventListener("click", () => setGroup(b.dataset.group)));
		$$("[data-group-jump]").forEach((b) =>
			b.addEventListener("click", (e) => {
				e.preventDefault(); // karusel rasmi <a href="#"> — sahifa sakramasin
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
		const instock = $("[data-instock]");
		instock?.addEventListener("change", () => { state.instock = instock.checked; apply(); });
		const filterBtn = $("[data-filter-toggle]"), filterPanel = $("[data-filter-panel]");
		filterBtn?.addEventListener("click", () => {
			filterPanel.hidden = !filterPanel.hidden;
			filterBtn.setAttribute("aria-expanded", String(!filterPanel.hidden));
		});
		// Narx, kategoriya ("Hammasi"), qidiruv va sevimlilar filtri — hammasi boshlang'ich holatga
		$$("[data-reset-filters]").forEach((b) =>
			b.addEventListener("click", () => {
				Object.assign(state, { q: "", min: 0, max: Infinity, instock: false });
				if (instock) instock.checked = false;
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

	// ---------- Rasmni to'liq ekranda ko'rish ----------
	function initLightbox(getImgs, getIndex, onClose) {
		const box = $("[data-lightbox]");
		const track = $("[data-lightbox-track]");
		if (!box || !getImgs().length) return;
		const count = $("[data-lightbox-count]");
		const index = () => Math.round(track.scrollLeft / (track.clientWidth || 1));
		const step = (d) => {
			const n = track.children.length;
			track.scrollTo({ left: ((index() + d + n) % n) * track.clientWidth, behavior: "smooth" });
		};
		const update = () => { count.textContent = `${index() + 1} / ${track.children.length}`; };
		track.addEventListener("scroll", update, { passive: true });

		// Kattalashtirish: ikki barmoq (pinch), ikki marta bosish, kattalashganda bir barmoq bilan surish.
		// Brauzerning o'z zoom'i o'chirilgan (CSS touch-action: pan-x) — u sahifani chap burchakka surib qo'yardi.
		const zoom = { img: null, s: 1, x: 0, y: 0 };
		const pointers = new Map();
		let pinch = null, pan = null, lastTap = 0;
		const clampPos = () => {
			const maxX = ((zoom.s - 1) * zoom.img.clientWidth) / 2, maxY = ((zoom.s - 1) * zoom.img.clientHeight) / 2;
			zoom.x = Math.max(-maxX, Math.min(maxX, zoom.x));
			zoom.y = Math.max(-maxY, Math.min(maxY, zoom.y));
		};
		const render = () => {
			if (!zoom.img) return;
			clampPos();
			const on = zoom.s > 1.01;
			zoom.img.style.transform = on ? `translate(${zoom.x}px, ${zoom.y}px) scale(${zoom.s})` : "";
			zoom.img.classList.toggle("is-zoomed", on);
			// Kattalashganda slaydlar surilmaydi — barmoq rasmni suradi
			track.style.touchAction = on ? "none" : "";
			track.style.overflow = on ? "hidden" : "";
		};
		const resetZoom = () => { if (zoom.img) { zoom.s = 1; zoom.x = zoom.y = 0; render(); } zoom.img = null; };
		// Ekrandagi (cx, cy) nuqta rasmning qaysi nuqtasi — scale o'zgarganda o'sha nuqta joyida qolsin
		const scaleAt = (s, cx, cy, from = zoom) => {
			const r = zoom.img.getBoundingClientRect();
			const mx = r.left + r.width / 2, my = r.top + r.height / 2;
			const ux = (cx - mx - from.x) / from.s, uy = (cy - my - from.y) / from.s;
			zoom.s = Math.max(1, Math.min(4, s));
			zoom.x = cx - mx - zoom.s * ux;
			zoom.y = cy - my - zoom.s * uy;
			render();
		};
		const dist = () => { const [a, b] = [...pointers.values()]; return Math.hypot(a.x - b.x, a.y - b.y); };
		const mid = () => { const [a, b] = [...pointers.values()]; return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; };
		track.addEventListener("pointerdown", (e) => {
			if (e.target.tagName !== "IMG") return;
			if (zoom.img !== e.target) resetZoom(), (zoom.img = e.target);
			pointers.set(e.pointerId, { x: e.clientX, y: e.clientY, t: Date.now(), moved: false });
			if (pointers.size === 2) pinch = { d: dist(), s: zoom.s, x: zoom.x, y: zoom.y, m: mid() };
			else if (zoom.s > 1) pan = { x: zoom.x, y: zoom.y, px: e.clientX, py: e.clientY };
		});
		track.addEventListener("pointermove", (e) => {
			const p = pointers.get(e.pointerId);
			if (!p) return;
			if (Math.abs(e.clientX - p.x) > 8 || Math.abs(e.clientY - p.y) > 8) p.moved = true;
			p.x = e.clientX; p.y = e.clientY;
			if (pinch && pointers.size === 2) {
				const m = mid();
				scaleAt((pinch.s * dist()) / pinch.d, m.x, m.y, pinch);
				pinch.m = m;
			} else if (pan && pointers.size === 1) {
				zoom.x = pan.x + e.clientX - pan.px;
				zoom.y = pan.y + e.clientY - pan.py;
				render();
			}
		});
		const lift = (e) => {
			const p = pointers.get(e.pointerId);
			pointers.delete(e.pointerId);
			if (pointers.size < 2) pinch = null;
			if (!pointers.size) pan = null;
			if (!p || p.moved || e.type !== "pointerup") return;
			// Ikki marta tez bosish: 2.5× yoki qaytarish
			const now = Date.now();
			if (now - lastTap < 320) scaleAt(zoom.s > 1 ? 1 : 2.5, e.clientX, e.clientY), (lastTap = 0);
			else lastTap = now;
		};
		track.addEventListener("pointerup", lift);
		track.addEventListener("pointercancel", lift);
		track.addEventListener("scroll", () => { if (zoom.img && zoom.s > 1 && zoom.img !== track.children[index()]?.firstElementChild) resetZoom(); }, { passive: true });

		function open(start) {
			resetZoom();
			const imgs = getImgs();
			track.innerHTML = imgs
				.map((i) => `<figure><img src="${i.dataset.full || i.getAttribute("src")}" alt="${i.alt.replace(/"/g, "&quot;")}" decoding="async" draggable="false"></figure>`)
				.join("");
			box.hidden = false;
			box.classList.toggle("is-single", imgs.length < 2);
			document.documentElement.classList.add("sf-noscroll");
			track.scrollLeft = start * track.clientWidth;
			update();
			// Telefondagi "orqaga" tugmasi sahifadan chiqib ketmasin — avval rasmni yopadi
			history.pushState({ sfLightbox: 1 }, "");
		}
		function close() {
			if (box.hidden) return;
			const i = index();
			resetZoom();
			box.hidden = true;
			document.documentElement.classList.remove("sf-noscroll");
			onClose(i);
		}
		const closeByUser = () => (history.state?.sfLightbox ? history.back() : close());

		$("[data-gallery]").addEventListener("click", (e) => {
			if (e.target.tagName === "IMG") open(getImgs().indexOf(e.target));
		});
		$("[data-lightbox-close]").addEventListener("click", closeByUser);
		$$("[data-lightbox-step]").forEach((b) => b.addEventListener("click", () => step(+b.dataset.lightboxStep)));
		// Rasm atrofidagi bo'sh joy bosilsa ham yopiladi
		track.addEventListener("click", (e) => { if (e.target.tagName !== "IMG") closeByUser(); });
		window.addEventListener("popstate", close);
		document.addEventListener("keydown", (e) => {
			if (box.hidden) return;
			if (e.key === "Escape") closeByUser();
			if (e.key === "ArrowRight") step(1);
			if (e.key === "ArrowLeft") step(-1);
		});
	}

	// ---------- Mahsulot sahifasi ----------
	function initProduct() {
		const track = $("[data-gallery]");
		const dotsBox = $("[data-dots]");
		// Slaydlar: rasm yoki video (Uzum'dagidek video birinchi); to'liq ekran faqat rasmlar uchun
		const slides = track ? [...track.children].filter((el) => el.matches("img, video")) : [];
		const thumbs = $$("[data-thumbs] button");
		const shownSlides = () => slides.filter((s) => !s.hidden);
		const shownImgs = () => shownSlides().filter((s) => s.tagName === "IMG");
		const currentIndex = () => (track ? Math.round(track.scrollLeft / (track.clientWidth || 1)) : 0);
		const goTo = (i, smooth = true) => {
			const n = shownSlides().length;
			if (!n) return;
			track.scrollTo({ left: ((i + n) % n) * track.clientWidth, behavior: smooth ? "smooth" : "auto" });
		};
		// Nuqtalar va chapdagi kichik rasmlar joriy rasmga ergashadi
		const syncActive = () => {
			const cur = shownSlides()[currentIndex()];
			// Faqat ko'rinib turgan video ijro etiladi (batareya, trafik)
			slides.forEach((v) => {
				if (v.tagName !== "VIDEO") return;
				if (v === cur) v.play()?.catch?.(() => {});
				else v.pause();
			});
			if (dotsBox) [...dotsBox.children].forEach((d, k) => d.classList.toggle("is-active", k === currentIndex()));
			thumbs.forEach((t, k) => {
				const on = slides[k] === cur;
				t.classList.toggle("is-active", on);
				if (on) t.scrollIntoView({ block: "nearest", inline: "nearest" });
			});
		};
		if (track) track.addEventListener("scroll", syncActive, { passive: true });
		// Muqovasiz video: birinchi kadr kichik rasm va orqa fon bo'ladi (sotuvchi alohida rasm yuklamasa ham)
		slides.forEach((v, k) => {
			if (v.tagName !== "VIDEO" || v.getAttribute("poster")) return;
			const snap = () => {
				try {
					const c = document.createElement("canvas");
					c.width = v.videoWidth; c.height = v.videoHeight;
					c.getContext("2d").drawImage(v, 0, 0);
					const url = c.toDataURL("image/jpeg", .7);
					v.setAttribute("poster", url);
					if (thumbs[k]) thumbs[k].style.backgroundImage = `url("${url}")`;
					syncActive();
				} catch { /* kadr hali tayyor emas */ }
			};
			v.readyState >= 2 ? snap() : v.addEventListener("loadeddata", snap, { once: true });
		});
		thumbs.forEach((t, k) => {
			const pick = () => goTo(shownSlides().indexOf(slides[k]));
			t.addEventListener("click", pick);
			t.addEventListener("mouseenter", pick);
		});
		$$("[data-gallery-step]").forEach((b) => b.addEventListener("click", () => goTo(currentIndex() + +b.dataset.galleryStep)));
		syncActive();

		// Rang tanlansa — faqat shu rangga bog'langan rasmlar; rang tanlanmagan bo'lsa — hammasi
		const filterGallery = (color, fallback) => {
			if (!slides.length) return;
			const own = color ? slides.filter((i) => i.dataset.color === color) : [];
			slides.forEach((i, k) => {
				i.hidden = own.length > 0 && i.dataset.color !== color;
				if (thumbs[k]) thumbs[k].hidden = i.hidden;
			});
			const shown = shownSlides();
			// Rangga bog'langan rasm yo'q (eski tovarlar): rang rasmiga aylantiramiz
			const idx = own.length ? 0 : Math.max(shown.findIndex((i) => fallback && i.getAttribute("src") === fallback), 0);
			track.scrollTo({ left: idx * track.clientWidth, behavior: own.length ? "auto" : "smooth" });
			if (dotsBox) {
				dotsBox.hidden = shown.length < 2;
				dotsBox.innerHTML = shown.map((_, k) => `<span class="${k === idx ? "is-active" : ""}"></span>`).join("");
			}
			$$("[data-gallery-step]").forEach((b) => (b.hidden = shown.length < 2));
			syncActive();
		};

		initLightbox(shownImgs, () => currentIndex(), (i) => goTo(shownSlides().indexOf(shownImgs()[i]), false));

		// Telefonda — tizimning o'z "Ulashish" oynasi; bo'lmasa (kompyuter) — Telegram / WhatsApp / nusxalash
		$("[data-share]")?.addEventListener("click", async () => {
			const data = { title: document.title, url: location.href };
			if (navigator.share) {
				try { await navigator.share(data); } catch { /* foydalanuvchi bekor qildi */ }
				return;
			}
			shareSheet(data);
		});
		function shareSheet({ title, url }) {
			let box = $("[data-share-sheet]");
			if (!box) {
				const u = encodeURIComponent(url), t = encodeURIComponent(title);
				box = document.createElement("div");
				box.className = "sf-share";
				box.setAttribute("data-share-sheet", "");
				box.innerHTML = `<div class="sf-share__panel" role="dialog" aria-modal="true" aria-label="Ulashish">
					<b>Ulashish</b>
					<a href="https://t.me/share/url?url=${u}&text=${t}" target="_blank" rel="noopener"><svg><use href="#i-tg"/></svg>Telegram orqali yuborish</a>
					<a href="https://wa.me/?text=${t}%20${u}" target="_blank" rel="noopener"><svg><use href="#i-wa"/></svg>WhatsApp orqali yuborish</a>
					<button type="button" data-share-copy><svg><use href="#i-share"/></svg>Havolani nusxalash</button>
					<button type="button" class="sf-share__close" data-share-close>Yopish</button>
				</div>`;
				document.body.append(box);
				box.addEventListener("click", (e) => {
					if (e.target === box || e.target.closest("[data-share-close], a")) box.hidden = true;
				});
				$("[data-share-copy]", box).addEventListener("click", async () => {
					try { await navigator.clipboard.writeText(url); toast("Havola nusxalandi"); } catch { /* ruxsat yo'q */ }
					box.hidden = true;
				});
				document.addEventListener("keydown", (e) => { if (e.key === "Escape") box.hidden = true; });
			}
			box.hidden = false;
		}

		// Pastdagi "O'xshash mahsulotlar" kartalaridagi "+" tugmasi
		$$("[data-related] [data-add]").forEach((btn) =>
			btn.addEventListener("click", () => {
				cart.add(btn.dataset.add);
				toast(`Savatga qo‘shildi · ${cart.count()} ta mahsulot`);
			})
		);

		const buy = $("[data-buy]");
		if (!buy) return;
		const out = $("[data-qty]", buy);
		const addBtn = $("[data-buy-add]", buy);
		let max = +buy.dataset.max || 99;
		let qty = 1;
		let code = buy.dataset.code; // variantli mahsulotda: tanlangan variant kodi
		const productCode = buy.dataset.code;
		let variantLabel = "";
		let variantPrice = null;

		// ---- Rang va o'lcham (PDF 4-sahifa) ----
		const box = $("[data-variants]");
		if (box) {
			const opt = JSON.parse(box.dataset.variants);
			const hasColors = opt.colors.length > 0, hasSizes = opt.sizes.length > 0;
			const sel = { color: "", size: "" };
			const key = (c, s) => `${c}|${s}`;
			const avail = (c, s) => (opt.variants[key(c, s)]?.qty || 0) > 0;
			// Tanlov bitta bo'lsa — oldindan tanlaymiz. Ranglar ko'p bo'lsa, mijoz bosmaguncha barcha rasmlar ko'rinadi
			if (opt.colors.length === 1) sel.color = opt.colors[0].value;
			if (opt.sizes.length === 1) sel.size = opt.sizes[0];

			// Narx rang/o'lcham bo'yicha har xil bo'lishi mumkin: tanlanmaguncha "…so'mdan", tanlanganda — o'sha
			// variant narxi va chegirma foizi (eski narx shu variantnikidan katta bo'lsagina)
			const nowEl = $("[data-price-now]"), oldEl = $("[data-price-old]"), badgeEl = $("[data-price-badge]");
			const baseText = nowEl?.textContent;
			function showPrice(price) {
				if (!nowEl) return;
				nowEl.textContent = price ? fmt(price) : baseText;
				if (!oldEl) return;
				const old = +oldEl.dataset.priceOld, now = price || +nowEl.dataset.priceNow;
				oldEl.hidden = badgeEl.hidden = !(old > now);
				if (old > now) badgeEl.textContent = `−${Math.round((1 - now / old) * 100)}%`;
			}

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
				showPrice(ready && v ? v.price : null);
				const stockEl = $("[data-variant-stock]", box);
				// Tez kunda / tugagan: tugma yo'q — rang faqat rasmlarni ko'rsatadi
				if (!addBtn) { stockEl.textContent = ""; return; }
				if (!ready) { stockEl.textContent = "Rang va o‘lchamni tanlang"; addBtn.disabled = true; return; }
				if (!v || v.qty <= 0) { stockEl.textContent = "Bu variant tugagan"; addBtn.disabled = true; return; }
				code = v.code;
				variantPrice = v.price;
				max = v.qty;
				variantLabel = [hasColors && sel.color, hasSizes && sel.size].filter(Boolean).join(" · ");
				stockEl.textContent = v.qty <= 5 ? `${v.qty} ta qolgan` : "Sotuvda bor";
				addBtn.disabled = false;
				if (qty > max) { qty = max; out.textContent = qty; }
			}
			const showColor = (color) => filterGallery(color, opt.colors.find((c) => c.value === color)?.image);
			// Tanlangan rangni yana bossa — tanlov olinadi va yana barcha ranglar rasmi chiqadi
			$$("[data-color]", box).forEach((b) => b.addEventListener("click", () => {
				sel.color = sel.color === b.dataset.color && opt.colors.length > 1 ? "" : b.dataset.color;
				render();
				showColor(sel.color);
			}));
			$$("[data-size]", box).forEach((b) => b.addEventListener("click", () => { sel.size = b.dataset.size; render(); }));
			render();
			if (sel.color) filterGallery(sel.color);
		}

		$$("[data-step]", buy).forEach((b) =>
			b.addEventListener("click", () => {
				qty = Math.max(1, Math.min(max, qty + +b.dataset.step));
				out.textContent = qty;
			})
		);
		addBtn?.addEventListener("click", () => {
			if (code !== productCode) {
				// variant uchun savat paneli ma'lumoti (nom, rasm asosiy mahsulotdan; narx — variantning o'zi)
				meta[code] = { ...meta[productCode], variant: variantLabel, ...(variantPrice ? { price: variantPrice } : {}) };
				store.set(META_KEY, meta);
			}
			cart.add(code, qty);
			toast(`Savatga qo‘shildi${variantLabel ? ` (${variantLabel})` : ""} · ${cart.count()} ta mahsulot`);
		});
	}

	// ---------- Savat sahifasi: narxlar serverdan ----------
	// Majburiy tovar (masalan, o'qiydigan ruchka) olinmagan: savatda ogohlantirish, "To'lovga o'tish" yopiq.
	// Kirgandan keyin savat qayta tekshiriladi — mijoz uni avval olgan bo'lishi mumkin
	let mustBlock = false;
	let reloadCart = () => {};
	let flushRemovals = () => {};

	// Buyurtma yakunlandi: faqat o'sha buyurtmadagi tovarlar savatdan olinadi (keyin qo'shilganlari qoladi)
	function settleOrder(p) {
		const c = cart.all();
		for (const [code, q] of Object.entries(p?.lines || {})) {
			const left = (c[code] || 0) - q;
			if (left > 0) c[code] = left; else delete c[code];
		}
		store.set(CART_KEY, c);
		store.set(PENDING_KEY, null);
		renderCartSummary();
	}

	// Buyurtma sahifasi: yakunlangan bo'lsa savatni tozalaymiz, bekor qilingan bo'lsa — savat qoladi
	function initOrderState() {
		const el = $("[data-order-state]");
		const p = store.get(PENDING_KEY, null);
		if (!el || !p || p.order !== el.dataset.orderName) return;
		if (el.dataset.orderState === "done") settleOrder(p);
		else if (el.dataset.orderState === "cancelled") store.set(PENDING_KEY, null);
	}

	function renderMust(m) {
		const box = $("[data-must]");
		if (!box) return;
		mustBlock = !!(m && m.required);
		box.hidden = !mustBlock;
		const btn = $("[data-checkout-btn]"), hint = $("[data-checkout-hint]");
		if (btn && mustBlock) {
			btn.disabled = true;
			hint.hidden = false;
			hint.textContent = "Avval majburiy tovarni savatga qo‘shing";
		}
		if (!mustBlock) return;
		const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
		const card = (i) => `
			<div class="sf-must__item">
				${i.thumb ? `<img src="${esc(i.thumb)}" alt="">` : ""}
				<div class="sf-must__info">
					<b>${esc(i.name)}</b>
					<div class="sf-price"><span class="sf-price__now">${fmt(i.price || 0)}</span>${i.old_price ? `<s class="sf-price__old">${fmt(i.old_price)}</s>` : ""}</div>
					${i.discount ? `<span class="sf-must__deal">Siz uchun −${i.discount}% chegirma</span>` : ""}
				</div>
				${!i.in_stock ? `<span class="sf-muted">Hozircha mavjud emas</span>`
					: i.has_variants ? `<a class="sf-btn sf-btn--brand" href="${withPreview(`${SF.base}/p/${encodeURIComponent(i.code)}`)}">Tanlash</a>`
					: `<button class="sf-btn sf-btn--brand" type="button" data-must-add="${esc(i.code)}">Savatga qo‘shish</button>`}
			</div>`;
		box.innerHTML = `
			<h2>${m.items.length > 1 ? "Avval shu tovarlarni xarid qiling" : "Avval shu tovarni xarid qiling"}</h2>
			<p class="sf-muted">Bu do‘kondan buyurtma berish uchun quyidagi ${m.items.length > 1 ? "tovarlarning har biri" : "tovar"} kerak. Savatga qo‘shsangiz — buyurtma beriladi.</p>
			${m.items.map(card).join("")}
			<p class="sf-must__call">Avval boshqa raqam bilan sotib olganmisiz?${m.call_center ? ` Call-center: <a href="tel:${esc(m.call_center)}">${esc(m.call_center)}</a> — eski raqamingizni ayting, tasdiqlab beramiz.` : " Do‘konga qo‘ng‘iroq qiling — eski raqamingizni ayting."}
				${m.logged_in ? "" : " Yoki pastda raqamingizni tasdiqlang: avval olgan bo‘lsangiz, o‘zi taniydi."}</p>`;
		$$("[data-must-add]", box).forEach((b) =>
			b.addEventListener("click", () => {
				cart.add(b.dataset.mustAdd, 1);
				toast("Savatga qo‘shildi");
				reloadCart();
			})
		);
	}

	async function initCart() {
		const box = $("[data-cart-lines]");
		if (!box) return;
		const tpl = $("#sf-line-tpl");

		const pendingBox = $("[data-cart-pending]");

		async function load() {
			const lines = Object.entries(cart.all()).map(([code, qty]) => ({ code, qty }));
			if (!lines.length) return render({ lines: [], total: 0 });
			const p = store.get(PENDING_KEY, null);
			const url = `/api/method/marketplace.api.get_cart?shop=${encodeURIComponent(SF.shop)}&lines=${encodeURIComponent(JSON.stringify(lines))}`
				+ (p?.order ? `&pending=${encodeURIComponent(p.order)}` : "");
			try {
				const res = await fetch(url, { headers: { Accept: "application/json" } });
				if (!res.ok) throw new Error(res.status);
				const data = (await res.json()).message;
				// Buyurtma boshqa sahifada yakunlangan (masalan, Payme ilovasida to'langan) — o'sha tovarlar savatdan olinadi
				if (data.pending?.state === "done") { settleOrder(p); toast("Buyurtmangiz qabul qilingan"); return load(); }
				if (data.pending && data.pending.state !== "pending") store.set(PENDING_KEY, null);
				render(data);
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
				if (l.list_price > l.price) {
					const oldEl = $("[data-old]", node);
					oldEl.textContent = fmt(l.list_price);
					oldEl.hidden = false;
				}
				$("[data-qty]", node).textContent = l.qty;
				const note = $("[data-note]", node);
				if (l.max_qty < 99 && l.qty >= l.max_qty) { note.hidden = false; note.textContent = `${l.max_qty} ta qolgan`; }
				// Minus 1 dan pastga tushirmaydi: o'chirish faqat savatcha tugmasi yoki surish bilan (5 soniya qaytarish bor)
				$$("[data-line-step]", node).forEach((b) => {
					if (+b.dataset.lineStep < 0 && l.qty <= 1) b.disabled = true;
					b.addEventListener("click", () => {
						const next = l.qty + +b.dataset.lineStep;
						if (next < 1) return;
						if (next > l.max_qty) return toast(`Faqat ${l.max_qty} ta qolgan`);
						cart.set(l.code, next);
						load();
					});
				});
				const wrap = $(".sf-swipe", node);
				wrap.dataset.code = l.code;
				const remove = () => startRemoval(l.code, wrap);
				$$("[data-remove]", node).forEach((b) => b.addEventListener("click", remove));
				swipeToDelete(wrap, remove);
				if (removing.has(l.code)) showUndo(l.code, wrap);
				box.append(node);
			}
			if (pendingBox) {
				const p = data.pending?.state === "pending" ? data.pending : null;
				pendingBox.hidden = !p || !data.lines.length;
				if (p) pendingBox.innerHTML = `Bu savat bilan boshlangan buyurtma hali to‘lanmagan.
					<a class="sf-link" href="${withPreview(p.url)}">To‘lovni davom ettirish →</a>
					<small>Savatni o‘zgartirsangiz — «To‘lovga o‘tish» yangi buyurtma yaratadi, eskisi bekor bo‘ladi.</small>`;
			}
			if (removed) toast("Ba’zi tovarlar tugagani uchun savatdan olindi");

			lastData = data;
			summary();
			renderMust(data.lines.length ? data.mandatory : null);
		}

		// Jami: o'chirilayotgan (5 soniya kutilayotgan) tovar hisobga kirmaydi. Uzum'dagidek: mahsulotlar chegirmasiz
		// narxda, ostida "Chegirma: −X so'm" (aksiya va ulgurji narx farqi), keyin Jami
		let lastData = null;
		function summary() {
			const live = lastData.lines.filter((l) => !removing.has(l.code));
			const count = live.reduce((s, l) => s + l.qty, 0);
			const total = live.reduce((s, l) => s + l.amount, 0);
			const full = live.reduce((s, l) => s + Math.max(l.list_price || 0, l.price) * l.qty, 0);
			const save = Math.round(full - total);
			for (const sel of ["[data-summary]", "[data-checkout]", "[data-checkout-form]", "[data-delivery]"]) {
				const el = $(sel);
				if (el) el.hidden = !count;
			}
			$("[data-summary-label]").textContent = `Mahsulotlar (${count})`;
			$("[data-summary-amount]").textContent = fmt(save > 0 ? full : total);
			const saveRow = $("[data-summary-save]");
			if (saveRow) {
				saveRow.hidden = !(save > 0);
				$("[data-summary-save-amount]").textContent = `−${fmt(save)}`;
			}
			$("[data-summary-total]").textContent = fmt(total);
		}

		// ---- O'chirish: Uzum'dagidek 5 soniya "Qaytarish", keyin tovar savatdan ketadi ----
		const UNDO_MS = 5000;
		const removing = new Map(); // kod -> {until, timer}
		function startRemoval(code, wrap) {
			if (removing.has(code)) return;
			const until = Date.now() + UNDO_MS;
			removing.set(code, {
				until,
				timer: setTimeout(() => {
					if (!removing.has(code)) return;
					box.querySelector(`.sf-swipe[data-code="${CSS.escape(code)}"]`)?.classList.add("is-gone");
					setTimeout(() => { if (removing.has(code)) { commitRemoval(code); load(); } }, 200);
				}, UNDO_MS),
			});
			showUndo(code, wrap);
			summary();
		}
		function showUndo(code, wrap) {
			const left = Math.max(0, removing.get(code).until - Date.now());
			wrap.classList.add("is-removing");
			wrap.querySelector(".sf-undo")?.remove();
			const el = document.createElement("div");
			el.className = "sf-undo";
			el.setAttribute("role", "status");
			el.innerHTML = `<span>Savatdan olib tashlandi</span><button type="button" class="sf-undo__btn">Qaytarish</button><i class="sf-undo__bar" style="animation-duration:${left}ms"></i>`;
			el.querySelector("button").addEventListener("click", () => {
				clearTimeout(removing.get(code)?.timer);
				removing.delete(code);
				el.remove();
				wrap.classList.remove("is-removing", "is-open", "is-gone");
				const card = $("[data-swipe-card]", wrap);
				if (card) card.style.transform = "";
				summary();
			});
			wrap.append(el);
		}
		function commitRemoval(code) {
			const r = removing.get(code);
			if (!r) return;
			clearTimeout(r.timer);
			removing.delete(code);
			cart.set(code, 0);
		}
		// "To'lovga o'tish" bosilsa yoki sahifadan chiqilsa — kutilayotgan o'chirishlar darhol bajariladi
		flushRemovals = () => [...removing.keys()].forEach(commitRemoval);
		window.addEventListener("pagehide", () => flushRemovals());
		// To'lov sahifasidan "orqaga": brauzer eski sahifani xotiradan ko'rsatadi ("Buyurtma yaratilmoqda…" tugmasi
		// bilan) — yangidan yuklaymiz
		window.addEventListener("pageshow", (e) => e.persisted && location.reload());

		reloadCart = load;
		load();
	}

	// Savat qatorini chapga surish: qizil "O'chirish" ochiladi; oxirigacha surilsa — darhol o'chadi
	function swipeToDelete(wrap, onDelete) {
		const card = $("[data-swipe-card]", wrap);
		const OPEN = 88;
		let x0 = 0, y0 = 0, dx = 0, base = 0, dragging = false, decided = false;
		const move = (x, animate) => {
			card.style.transition = animate ? "" : "none";
			card.style.transform = x ? `translateX(${x}px)` : "";
			wrap.classList.toggle("is-open", x < 0);
		};
		card.addEventListener("pointerdown", (e) => {
			if (e.pointerType === "mouse" || e.target.closest("button")) return;
			x0 = e.clientX; y0 = e.clientY; dx = 0; dragging = true; decided = false;
			base = wrap.classList.contains("is-open") ? -OPEN : 0;
		});
		card.addEventListener("pointermove", (e) => {
			if (!dragging) return;
			const mx = e.clientX - x0, my = e.clientY - y0;
			if (!decided) {
				if (Math.abs(mx) < 8 && Math.abs(my) < 8) return;
				decided = true;
				if (Math.abs(my) > Math.abs(mx)) { dragging = false; return; } // sahifani aylantirish
				card.setPointerCapture(e.pointerId);
			}
			dx = Math.min(0, base + mx);
			move(dx, false);
		});
		const end = () => {
			if (!dragging) return;
			dragging = false;
			if (!decided) return;
			if (dx < -card.offsetWidth * 0.55) { move(-card.offsetWidth, true); onDelete(); }
			else move(dx < -OPEN / 2 ? -OPEN : 0, true);
		};
		card.addEventListener("pointerup", end);
		card.addEventListener("pointercancel", end);
		// Surilgandan keyingi "click" havolani ochmasin; ochiq qatorga bosilsa — yopiladi
		card.addEventListener("click", (e) => {
			if (decided || wrap.classList.contains("is-open")) {
				e.preventDefault();
				if (!decided) move(0, true);
				decided = false;
			}
		}, true);
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

	// ---------- Kirish: Telegram orqali (telefon, ism va familiya Telegram'dan keladi) ----------
	// Belgilash: macros.html auth_form(). Savat, "Buyurtmalarim" va buyurtma sahifasida ishlatiladi.
	// Tugma botni t.me/<bot>?start=l<id> bilan ochadi; botda shu sahifadagi kirish kodi va «Ha, kirish» chiqadi (Pont kabi).
	// Mijoz bosgach, shu sahifa har 2 soniyada so'rab turgan telegram_login_status sessiyani ochadi (tg_login.py).
	// onUser(me) — kirgandan/chiqqandan keyin (me = null — chiqdi). Qaytaradi: setUser (tashqaridan holatni berish uchun).
	function initAuth(root, onUser = () => {}) {
		const guest = $("[data-auth-guest]", root), user = $("[data-auth-user]", root);
		const btn = $("[data-tg-login]", root), wait = $("[data-tg-wait]", root);
		// So'rov Telegram'ga o'tib qaytganda (yoki sahifa yangilansa) ham saqlanadi: {id, secret, link, code, until, started}
		const LOGIN_KEY = `sf_tg_login:${SF.shop}`;
		let login = null, timer = null, busy = false;

		const save = () => { try { localStorage.setItem(LOGIN_KEY, JSON.stringify(login)); } catch (e) {} };
		const forget = () => { try { localStorage.removeItem(LOGIN_KEY); } catch (e) {} };
		const stop = () => { clearInterval(timer); timer = null; wait.hidden = true; };

		const setUser = (me) => {
			guest.hidden = !!me;
			user.hidden = !me;
			if (me) {
				stop();
				$("[data-me-name]", user).textContent = me.name;
				$("[data-me-phone]", user).textContent = me.phone_masked;
			} else {
				prepare();
			}
			onUser(me);
		};

		// Bot havolasi oldindan olinadi: tugma bosilganda Telegram darhol ochilsin (brauzer yangi oynani to'smasin)
		async function prepare(fresh = false) {
			let saved = null;
			try { saved = JSON.parse(localStorage.getItem(LOGIN_KEY) || "null"); } catch (e) {}
			if (!fresh && saved && saved.code && saved.until > Date.now() + 60000) {
				login = saved;
			} else {
				btn.setAttribute("aria-disabled", "true");
				try {
					const r = await api("telegram_login", { shop: SF.shop, path: location.pathname });
					login = { id: r.id, secret: r.secret, link: r.link, code: r.code, until: Date.now() + r.ttl * 1000 };
					save();
				} catch (e) {
					return toast(e.message);
				}
			}
			btn.href = login.link;
			btn.removeAttribute("aria-disabled");
			$("[data-tg-code]", root).textContent = login.code || "";
			if (login.started) poll();
		}

		function poll() {
			wait.hidden = false;
			clearInterval(timer);
			timer = setInterval(check, 2000);
			check();
		}

		async function check() {
			if (busy || !login) return;
			busy = true;
			try {
				const r = await api("telegram_login_status", { login: login.id, secret: login.secret });
				if (r.status === "ok") {
					forget();
					toast("Telefon tasdiqlandi ✓");
					setUser({ name: r.name, phone_masked: r.phone_masked });
				} else if (r.status === "expired" || r.status === "cancelled") {
					stop();
					forget();
					toast(r.status === "cancelled" ? "Kirish bekor qilindi" : "Vaqt tugadi — tugmani qaytadan bosing");
					prepare(true);
				}
			} catch (e) { /* tarmoq uzilsa — keyingi safar yana so'raladi */ } finally {
				busy = false;
			}
		}

		btn.addEventListener("click", (e) => {
			if (!login || btn.hasAttribute("aria-disabled")) return e.preventDefault();
			login.started = true;
			save();
			poll();
		});
		// Telefonda Telegram'dan qaytilganda darhol tekshiriladi (fonda taymerlar to'xtab turadi)
		document.addEventListener("visibilitychange", () => !document.hidden && timer && check());
		$("[data-logout]", root).addEventListener("click", async () => {
			await api("logout", {}).catch(() => {});
			setUser(null);
		});
		return setUser;
	}

	// ---------- Rasmiylashtirish: Telegram orqali kirish → buyurtma ----------
	function initCheckout() {
		const form = $("[data-checkout-form]");
		if (!form) return;
		const btn = $("[data-checkout-btn]"), hint = $("[data-checkout-hint]");
		const addressField = $("[data-address-field]"), address = $("[data-address]");

		let wasIn = null;
		const setUser = initAuth(form, (me) => {
			btn.disabled = !me || mustBlock;
			hint.hidden = !!me && !mustBlock;
			hint.textContent = mustBlock ? "Avval majburiy tovarni savatga qo‘shing" : "Avval telefon raqamingizni tasdiqlang";
			// Kirdi: majburiy tovarni avval olganmi — savat qayta tekshiriladi
			if (me && wasIn === false) reloadCart();
			wasIn = !!me;
		});

		// Manzil va tanlangan usul eslab qolinadi: "O'zim olaman"ga o'tib qaytsa ham, keyingi buyurtmada ham
		const pickup = $("[data-pickup]");
		const ADDRESS_KEY = "sf_delivery";
		const saved = store.get(ADDRESS_KEY, {});
		if (saved.address) address.value = saved.address;
		const radio = saved.method && $(`input[name=delivery][value="${saved.method}"]`);
		if (radio) radio.checked = true;
		const remember = () =>
			store.set(ADDRESS_KEY, { method: $("input[name=delivery]:checked").value, address: address.value });
		const showDelivery = () => {
			const courier = $("input[name=delivery]:checked").value === "Kuryer";
			addressField.hidden = !courier;
			if (pickup) pickup.hidden = courier;
		};
		$$("input[name=delivery]").forEach((r) => r.addEventListener("change", () => { showDelivery(); remember(); }));
		address.addEventListener("input", remember);
		showDelivery();

		btn.addEventListener("click", async () => {
			const delivery = $("input[name=delivery]:checked").value;
			if (delivery === "Kuryer" && address.value.trim().length < 5) {
				address.focus();
				return toast("Yetkazib berish manzilini yozing");
			}
			btn.disabled = true;
			btn.textContent = "Buyurtma yaratilmoqda…";
			try {
				flushRemovals();
				const lines = Object.entries(cart.all()).map(([code, qty]) => ({ code, qty }));
				const r = await api("place_order", { shop: SF.shop, lines, delivery_method: delivery, address: address.value });
				// Savat hozir tozalanmaydi: to'lov sahifasidan qaytsa joyida bo'lsin. Yakunlanganda — settleOrder
				store.set(PENDING_KEY, { order: r.order, lines: Object.fromEntries(lines.map((l) => [l.code, l.qty])) });
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
		if (box) initAuth(box, (me) => me && setTimeout(() => location.reload(), 400))(null);
		$("[data-orders-logout]")?.addEventListener("click", async (e) => {
			const btn = e.currentTarget;
			// Tasodifan bosilsa chiqib ketmasin — avval so'raladi
			if (!(await confirmSheet({ title: "Rostdan ham chiqasizmi?", text: "Buyurtmalaringizni ko‘rish uchun raqamingizni qayta tasdiqlashingiz kerak bo‘ladi." }))) return;
			btn.disabled = true;
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

	// To'lov sahifasida manzilni tuzatish (buyurtma hali do'konga bormagan) — keyingi buyurtma uchun ham eslab qolinadi
	function initAddressEdit() {
		const box = $("[data-addr]");
		if (!box) return;
		const view = $("[data-addr-view]", box), form = $("[data-addr-form]", box);
		const input = $("[data-addr-input]", box), save = $("[data-addr-save]", box);
		const toggle = (editing) => {
			view.hidden = editing;
			form.hidden = !editing;
			if (editing) input.focus();
		};
		$("[data-addr-edit]", box).addEventListener("click", () => toggle(true));
		$("[data-addr-cancel]", box).addEventListener("click", () => {
			input.value = $("[data-addr-text]", box).textContent;
			toggle(false);
		});
		save.addEventListener("click", async () => {
			if (input.value.trim().length < 5) {
				input.focus();
				return toast("Yetkazib berish manzilini yozing");
			}
			save.disabled = true;
			try {
				const r = await api("update_address", { order: box.dataset.order, address: input.value });
				$("[data-addr-text]", box).textContent = r.address;
				store.set("sf_delivery", { ...store.get("sf_delivery", {}), method: "Kuryer", address: r.address });
				toggle(false);
				toast("Manzil saqlandi ✓");
			} catch (e) {
				toast(e.message);
			} finally {
				save.disabled = false;
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
		const slides = [...track.children];
		const count = slides.length;
		let current = 0;
		let timer = null;
		// Slayd joyi offsetLeft'dan: banner rejimida telefonda slayd to'liq kenglikda emas (keyingisi chetdan ko'rinadi)
		const go = (i) => track.scrollTo({ left: slides[(i + count) % count].offsetLeft });
		track.addEventListener("scroll", () => {
			const x = track.scrollLeft;
			current = slides.reduce((best, s, i) => (Math.abs(s.offsetLeft - x) < Math.abs(slides[best].offsetLeft - x) ? i : best), 0);
			dots.forEach((d, i) => d.setAttribute("aria-selected", String(i === current)));
		}, { passive: true });
		dots.forEach((d) => d.addEventListener("click", () => { stop(); go(+d.dataset.carouselDot); }));
		$$("[data-carousel-step]", root).forEach((b) => b.addEventListener("click", () => { stop(); go(current + +b.dataset.carouselStep); }));
		const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
		const start = () => { if (!reduce && !timer) timer = setInterval(() => go(current + 1), 5000); };
		const stop = () => { clearInterval(timer); timer = null; };
		track.addEventListener("pointerdown", stop, { passive: true });
		track.addEventListener("touchstart", stop, { passive: true });
		document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
		start();
	}

	// Karusel rasmi slayd o'lchamiga yaqin bo'lsa — to'liq yoyiladi, aks holda butunligicha (xira fon ustida)
	function initSlideFit() {
		const imgs = $$("[data-slide-img]");
		if (!imgs.length) return;
		const fit = (img) => {
			const box = img.closest(".sf-slide");
			if (!img.naturalWidth || !box.clientHeight || box.classList.contains("sf-slide--item")) return;
			const ratio = img.naturalWidth / img.naturalHeight;
			const slot = box.clientWidth / box.clientHeight;
			box.classList.toggle("is-fill", Math.abs(ratio - slot) / slot < 0.18);
		};
		for (const img of imgs) img.complete ? fit(img) : img.addEventListener("load", () => fit(img), { once: true });
		let t;
		addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => imgs.forEach(fit), 150); }, { passive: true });
	}

	applyCartLink();
	initSlideFit();
	initCarousel();
	renderCartSummary();
	initFavorites();
	initCatalog();
	initProduct();
	initOrderState();
	initCart();
	initRowSteppers();
	initCheckout();
	initAccount();
	initPayment();
	initAddressEdit();

	// Boshqa tabda savat o'zgarsa, bu yerda ham yangilansin
	window.addEventListener("storage", (e) => e.key === CART_KEY && renderCartSummary());
})();
