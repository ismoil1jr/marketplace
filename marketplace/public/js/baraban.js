// Chegirma barabani: do'konga kirgan har bir mijoz barabanni aylantiradi (yopib bo'lmaydi), admin belgilagan
// soatga tushadi, tovar chegirma narxida savatga qo'shiladi. Taymer har sahifa tepasida (savatda ham) va faqat
// mijoz saytda turganda (tab ko'rinib turganda) yuradi. Haqiqiy qolgan vaqt va narx serverda (cookie bo'yicha).
(() => {
	const SF = window.SF;
	if (!SF || !SF.shop) return;

	const TICK_EVERY = 15; // soniya: serverga "saytdaman" signali
	const SPIN_MS = 4500;
	const reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

	const fmt = (n) => Math.round(n || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so‘m";
	const pad = (n) => String(n).padStart(2, "0");
	const hms = (s) => `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
	const el = (tag, cls, text) => {
		const n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text != null) n.textContent = text;
		return n;
	};

	async function api(method, data, keepalive = false) {
		try {
			const headers = { Accept: "application/json", "Content-Type": "application/json" };
			if (SF.csrf) headers["X-Frappe-CSRF-Token"] = SF.csrf;
			const r = await fetch(`/api/method/marketplace.baraban.${method}`, {
				method: "POST",
				headers,
				credentials: "same-origin",
				keepalive,
				body: JSON.stringify(data),
			});
			if (!r.ok) return null;
			const body = await r.json();
			return body.message || null;
		} catch (e) {
			return null;
		}
	}

	let st = null; // serverdan kelgan holat
	let remaining = 0;

	// ---------- Chegirma narxi: yon savat jami va sahifadagi narxlar ----------
	// Sahifadagi har bir o'zgarish yozib boriladi — muddat tugaganda hammasi asl holiga qaytariladi
	const undo = [];
	const setText = (node, text) => {
		const prev = node.textContent;
		undo.push(() => (node.textContent = prev));
		node.textContent = text;
	};
	const setData = (node, key, val) => {
		const had = key in node.dataset;
		const prev = node.dataset[key];
		undo.push(() => (had ? (node.dataset[key] = prev) : delete node.dataset[key]));
		node.dataset[key] = val;
	};
	const show = (node) => {
		const prev = node.hidden;
		undo.push(() => (node.hidden = prev));
		node.hidden = false;
	};
	const insertAfter = (ref, ...nodes) => {
		ref.after(...nodes);
		undo.push(() => nodes.forEach((n) => n.remove()));
	};

	function applyPrices() {
		if (!st) return;
		const codes = st.product.codes || [st.product.code];
		const on = remaining > 0;
		const old = st.old_price;
		SF.promoPrice = on ? (c) => (codes.includes(c) ? st.price : 0) : null;
		// Narxlar faqat haqiqiy chegirma bo'lsa almashadi (oddiy narx chegirma narxidan qimmat — server ham shunday)
		if (on && old && !undo.length) {
			// Katalog kartalari: oddiy (sf-price), "story" (st-card) va ro'yxat (kt-row) ko'rinishlari
			document.querySelectorAll(".sf-card[data-code]").forEach((card) => {
				if (!codes.includes(card.dataset.code)) return;
				const nowEl = card.querySelector(".sf-price__now, .st-card__price strong, .kt-price [data-retail]");
				if (!nowEl) return;
				setText(nowEl, fmt(st.price));
				let oldEl = card.querySelector(".sf-price__old, .st-card__price s, .kt-price s");
				if (!oldEl) {
					oldEl = el("s", nowEl.classList.contains("sf-price__now") ? "sf-price__old" : "");
					insertAfter(nowEl, oldEl);
				}
				setText(oldEl, fmt(old));
				const badge = card.querySelector(".sf-badge:not(.sf-badge--soon):not(.sf-badge--muted)");
				if (badge) setText(badge, `−${Math.round((1 - st.price / old) * 100)}%`);
			});
			// Mahsulot sahifasi (rang tanlanganda storefront.js ham SF.promoPrice'ni hisobga oladi)
			const buy = document.querySelector(".sf-buy[data-code]");
			const nowEl = document.querySelector("[data-price-now]");
			if (buy && nowEl && codes.includes(buy.dataset.code)) {
				setText(nowEl, fmt(st.price));
				setData(nowEl, "priceNow", st.price);
				setData(nowEl, "promoText", fmt(st.price));
				let oldEl = document.querySelector("[data-price-old]");
				let badge = document.querySelector("[data-price-badge]");
				if (!oldEl) {
					oldEl = el("s");
					badge = el("span", "sf-badge sf-badge--inline");
					badge.setAttribute("data-price-badge", "");
					insertAfter(nowEl, oldEl, badge);
				}
				setData(oldEl, "priceOld", old);
				setText(oldEl, fmt(old));
				show(oldEl);
				if (badge) {
					setText(badge, `−${Math.round((1 - st.price / old) * 100)}%`);
					show(badge);
				}
			}
		}
		if (!on) while (undo.length) undo.pop()();
		if (SF.cart && SF.cart.refresh) SF.cart.refresh();
	}

	// ---------- Taymer: sahifa tepasida ----------
	let bar = null;
	let timeEl = null;
	let countdown = null;
	let sinceTick = 0;

	function placeBar() {
		document.body.classList.add("has-bb-bar");
		// Panel ikki qatorga tushsa (tor ekran) — sahifa ham shuncha pastga tushsin
		const h = bar.offsetHeight;
		document.body.style.paddingTop = `${h}px`;
		document.querySelectorAll(".sf-top, .kt-head").forEach((n) => (n.style.top = `${h}px`));
	}

	function showBar() {
		if (bar) return;
		bar = el("div", "bb-bar");
		bar.setAttribute("role", "status");
		bar.append(el("span", "", "⏳ Chegirma tugashiga:"));
		timeEl = el("b", "bb-bar__time", hms(remaining));
		bar.append(timeEl);
		const deal = el("span", "bb-bar__deal", `· ${st.product.name} — ${fmt(st.price)}`);
		bar.append(deal);
		document.body.prepend(bar);
		placeBar();
		window.addEventListener("resize", placeBar, { passive: true });

		countdown = setInterval(() => {
			if (document.visibilityState !== "visible") return;
			remaining = Math.max(0, remaining - 1);
			timeEl.textContent = hms(remaining);
			if (++sinceTick >= TICK_EVERY) tick();
			if (remaining <= 0) expire();
		}, 1000);
		document.addEventListener("visibilitychange", () => {
			// Ketayotganda oxirgi soniyalar yoziladi; qaytganda hisob shu daqiqadan boshlanadi (yo'q vaqt hisoblanmaydi)
			if (remaining > 0) tick(document.visibilityState === "visible");
		});
	}

	async function tick(resume = false) {
		sinceTick = 0;
		// keepalive: boshqa sahifaga o'tayotganda ham so'rov uzilmaydi (oxirgi soniyalar yo'qolmasin)
		const data = { shop: SF.shop };
		if (resume) data.resume = 1;
		const r = await api("tick", data, document.visibilityState !== "visible");
		if (!r || typeof r.remaining !== "number" || remaining <= 0) return;
		remaining = r.remaining;
		if (timeEl) timeEl.textContent = hms(remaining);
		if (remaining <= 0) expire();
	}

	let ending = false;
	async function expire() {
		if (!bar || ending || bar.classList.contains("bb-bar--done")) return;
		// Server hakam: oxirgi soniyalarni yozdirib, tugaganini tasdiqlatamiz — aks holda savat chegirma narxida qoladi
		ending = true;
		const r = await api("tick", { shop: SF.shop });
		ending = false;
		if (r && r.remaining > 0) {
			remaining = r.remaining;
			timeEl.textContent = hms(remaining);
			return;
		}
		clearInterval(countdown);
		remaining = 0;
		bar.classList.add("bb-bar--done");
		bar.replaceChildren(el("span", "", "Chegirma muddati tugadi"));
		applyPrices();
		if (SF.reloadCart) SF.reloadCart();
		setTimeout(() => {
			bar.remove();
			window.removeEventListener("resize", placeBar);
			document.body.classList.remove("has-bb-bar");
			document.body.style.paddingTop = "";
			document.querySelectorAll(".sf-top, .kt-head").forEach((n) => (n.style.top = ""));
		}, 4000);
	}

	// ---------- Baraban ----------
	function wheelSvg(variants) {
		const NS = "http://www.w3.org/2000/svg";
		const svg = document.createElementNS(NS, "svg");
		svg.setAttribute("viewBox", "0 0 300 300");
		svg.setAttribute("class", "bb-wheel");
		svg.setAttribute("aria-hidden", "true");
		const g = document.createElementNS(NS, "g");
		const c = 150;
		const r = 142;
		const seg = 360 / variants.length;
		// Burchak soat mili bo'yicha, tepadan (ko'rsatkich tepada)
		const pt = (deg, rad) => {
			const a = (deg * Math.PI) / 180;
			return [c + rad * Math.sin(a), c - rad * Math.cos(a)];
		};
		variants.forEach((h, i) => {
			const kind = variants.length % 2 && i === variants.length - 1 && i ? "c" : i % 2 ? "b" : "a";
			const [x1, y1] = pt((i - 0.5) * seg, r);
			const [x2, y2] = pt((i + 0.5) * seg, r);
			const path = document.createElementNS(NS, "path");
			path.setAttribute("d", `M${c},${c} L${x1},${y1} A${r},${r} 0 ${seg > 180 ? 1 : 0} 1 ${x2},${y2} Z`);
			path.setAttribute("class", `bb-seg bb-seg--${kind === "c" ? "b" : kind} bb-seg-line`);
			if (kind === "c") path.style.fill = "#ffe2bf"; // toq sonli bo'lsa oxirgi bo'lak qo'shnisidan farq qilsin
			g.append(path);
			const [tx, ty] = pt(i * seg, r * 0.66);
			const text = document.createElementNS(NS, "text");
			text.setAttribute("x", tx);
			text.setAttribute("y", ty);
			text.setAttribute("transform", `rotate(${i * seg} ${tx} ${ty})`);
			text.setAttribute("class", `bb-label bb-label--${kind === "a" ? "a" : "b"}`);
			text.textContent = `${h} soat`;
			g.append(text);
		});
		const rim = document.createElementNS(NS, "circle");
		rim.setAttribute("cx", c);
		rim.setAttribute("cy", c);
		rim.setAttribute("r", r);
		rim.setAttribute("class", "bb-rim");
		svg.append(g, rim);
		return { svg, g, seg };
	}

	function showWheel() {
		const root = document.documentElement;
		root.classList.add("bb-lock");
		document.body.classList.add("bb-lock");

		const overlay = el("div", "bb-overlay");
		const card = el("div", "bb-card");
		card.setAttribute("role", "dialog");
		card.setAttribute("aria-modal", "true");
		card.setAttribute("aria-labelledby", "bb-title");
		const title = el("h2", "bb-title", "Chegirma barabani");
		title.id = "bb-title";
		const sub = el("p", "bb-sub", "Barabanni aylantiring va chegirma vaqtingizni oling");

		const wrap = el("div", "bb-wheel-wrap");
		const { svg, g, seg } = wheelSvg(st.variants);
		const spinBtn = el("button", "bb-spin", "Aylantirish");
		spinBtn.type = "button";
		wrap.append(el("div", "bb-pointer"), svg, spinBtn);

		const result = el("div", "bb-result");
		result.hidden = true;
		result.setAttribute("aria-live", "polite");

		card.append(title, sub, wrap, result);
		overlay.append(card);
		document.body.append(overlay);
		spinBtn.focus();

		// Yopib bo'lmaydi: Esc ishlamaydi, fokus oyna ichida qoladi
		const trap = (e) => {
			if (e.key === "Escape") {
				e.preventDefault();
				e.stopPropagation();
			} else if (e.key === "Tab") {
				const f = [...card.querySelectorAll("button:not([disabled]), a[href]")].filter((n) => n.offsetParent);
				if (!f.length) return e.preventDefault();
				const first = f[0];
				const last = f[f.length - 1];
				if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
				else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
				else if (!card.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
			}
		};
		document.addEventListener("keydown", trap, true);

		const close = () => {
			document.removeEventListener("keydown", trap, true);
			overlay.remove();
			root.classList.remove("bb-lock");
			document.body.classList.remove("bb-lock");
		};

		let busy = false;
		spinBtn.addEventListener("click", async () => {
			if (busy) return;
			busy = true;
			spinBtn.disabled = true;
			const r = await api("spin", { shop: SF.shop });
			if (!r || !r.enabled) {
				// Server javob bermadi yoki aksiya o'chirildi: mijozni qamab qo'ymaymiz — sayt ishlayveradi
				if (r && !r.enabled) return close();
				busy = false;
				spinBtn.disabled = false;
				sub.textContent = "Hozircha aylanmadi. Qayta bosing yoki xaridni davom ettiring.";
				if (!card.querySelector(".bb-later")) {
					const skip = el("button", "bb-later", "Xaridni davom ettirish");
					skip.type = "button";
					skip.addEventListener("click", close);
					card.append(skip);
				}
				return;
			}
			st = r;
			remaining = r.remaining;
			let idx = st.variants.indexOf(st.win);
			if (idx < 0) idx = 0;
			const jitter = (Math.random() - 0.5) * seg * 0.5; // bo'lak ichida, chetga tegmasdan
			const turns = reduceMotion ? 1 : 6;
			const angle = turns * 360 - idx * seg + jitter;
			const ms = reduceMotion ? 600 : SPIN_MS;
			g.style.transformOrigin = "150px 150px";
			g.style.transition = `transform ${ms}ms cubic-bezier(.17,.67,.12,1)`;
			// Keyingi kadrda — brauzer boshlang'ich holatni ko'rib olsin, aks holda animatsiya bo'lmaydi
			requestAnimationFrame(() => requestAnimationFrame(() => (g.style.transform = `rotate(${angle}deg)`)));
			setTimeout(() => showResult(result, sub, close), ms + 300);
		});
	}

	function showResult(result, sub, close) {
		const p = st.product;
		const code = p.add || p.code;
		// Variantli tovar: shu tovarning biror varianti savatda bo'lsa, yana qo'shilmaydi
		const inCart = SF.cart && (p.codes || [code]).some((c) => SF.cart.qty(c) > 0);
		if (SF.cart && !inCart) {
			SF.cart.remember(code, { name: p.name, variant: p.variant || "", thumb: p.thumb || "" });
			SF.cart.add(code, 1);
		}
		sub.hidden = true;
		result.replaceChildren();
		result.append(el("p", "bb-win", "🎉 Tabriklaymiz!"));
		const winSub = el("p", "bb-win-sub", "Sizga ");
		winSub.append(el("b", "", `${st.win} soatlik`), document.createTextNode(" chegirma"));
		result.append(winSub);

		const prod = el("div", "bb-product");
		if (p.thumb) {
			const img = el("img");
			img.src = p.thumb;
			img.alt = "";
			prod.append(img);
		}
		const info = el("div");
		info.append(el("div", "bb-product__name", p.variant ? `${p.name} (${p.variant})` : p.name));
		const price = el("div", "bb-product__price", fmt(st.price));
		if (st.old_price) price.append(el("s", "", fmt(st.old_price)));
		info.append(price);
		prod.append(info);
		result.append(prod);
		result.append(el("p", "bb-sub", "Tovar savatingizga qo‘shildi"));

		const go = el("button", "bb-go", "Savatga o‘tish");
		go.type = "button";
		go.addEventListener("click", () => {
			location.href = `${SF.base}/savat${SF.preview ? `?layout=${encodeURIComponent(SF.preview)}` : ""}`;
		});
		const later = el("button", "bb-later", "Xaridni davom ettirish");
		later.type = "button";
		later.addEventListener("click", close);
		result.append(go, later);
		result.hidden = false;
		go.focus();

		applyPrices();
		showBar();
	}

	// ---------- Ishga tushirish ----------
	async function init() {
		if (/\bpage-(privacy|order)\b/.test(document.body.className)) return;
		const r = await api("state", { shop: SF.shop });
		if (!r || !r.enabled) return;
		st = r;
		remaining = r.remaining || 0;
		if (!r.spun) return showWheel();
		if (remaining > 0) {
			applyPrices();
			showBar();
		}
	}

	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
	else init();
})();
