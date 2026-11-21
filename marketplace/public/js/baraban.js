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

	// ---------- Rang: do'kon brend rangidan och/to'q tuslar (CSS color-mix eski Safari'da yo'q) ----------
	function brandTones() {
		const raw = getComputedStyle(document.documentElement).getPropertyValue("--brand").trim() || "#1F5C4A";
		let r = 31, g = 92, b = 74;
		const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
		const rgb = raw.match(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i);
		if (hex) {
			const h = hex[1].length === 3 ? hex[1].replace(/./g, "$&$&") : hex[1];
			[r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
		} else if (rgb) [r, g, b] = rgb.slice(1, 4).map(Number);
		const mix = (t, to) => `rgb(${[r, g, b].map((c) => Math.round(c + (to - c) * t)).join(",")})`;
		return { base: `rgb(${r},${g},${b})`, light: mix(0.35, 255), pale: mix(0.82, 255), dark: mix(0.35, 0), rgb: `${r},${g},${b}` };
	}
	function setTones(node) {
		const t = brandTones();
		node.style.setProperty("--bb-brand", t.base);
		node.style.setProperty("--bb-brand-light", t.light);
		node.style.setProperty("--bb-brand-pale", t.pale);
		node.style.setProperty("--bb-brand-dark", t.dark);
		node.style.setProperty("--bb-brand-rgb", t.rgb);
		return t;
	}

	// ---------- Soat: HH:MM:SS katakchalari (tepadagi panel va natija oynasida bir xil) ----------
	const clocks = [];
	function clock(cls) {
		const box = el("span", `bb-clock ${cls || ""}`);
		box.setAttribute("aria-label", "Qolgan vaqt");
		const cells = [el("b"), el("b"), el("b")];
		box.append(cells[0], el("i", "", ":"), cells[1], el("i", "", ":"), cells[2]);
		clocks.push(cells);
		paint();
		return box;
	}
	function paint() {
		const s = Math.max(0, remaining);
		const parts = [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60].map(pad);
		clocks.forEach((cells) => cells.forEach((c, i) => c.textContent !== parts[i] && (c.textContent = parts[i])));
		if (bar) bar.classList.toggle("bb-bar--hurry", s > 0 && s <= 600);
	}

	// ---------- Taymer: sahifa tepasida ----------
	let bar = null;
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
		setTones(bar);
		bar.append(el("span", "bb-bar__icon", "⏳"), el("span", "bb-bar__label", "Chegirma tugashiga"), clock());
		bar.append(el("span", "bb-bar__deal", fmt(st.price)));
		document.body.prepend(bar);
		placeBar();
		window.addEventListener("resize", placeBar, { passive: true });

		countdown = setInterval(() => {
			if (document.visibilityState !== "visible") return;
			remaining = Math.max(0, remaining - 1);
			paint();
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
		paint();
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
			paint();
			return;
		}
		clearInterval(countdown);
		remaining = 0;
		paint();
		bar.classList.add("bb-bar--done");
		bar.replaceChildren(el("span", "bb-bar__label", "Chegirma muddati tugadi"));
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
	const NS = "http://www.w3.org/2000/svg";
	const svgEl = (tag, attrs) => {
		const n = document.createElementNS(NS, tag);
		for (const k in attrs) n.setAttribute(k, attrs[k]);
		return n;
	};
	function gradient(id, stops, kind = "linearGradient", attrs = {}) {
		const gr = svgEl(kind, { id, ...attrs });
		stops.forEach(([offset, color, opacity = 1]) =>
			gr.append(svgEl("stop", { offset, "stop-color": color, "stop-opacity": opacity }))
		);
		return gr;
	}

	function wheelSvg(variants, tones) {
		const svg = svgEl("svg", { viewBox: "0 0 320 320", class: "bb-wheel", "aria-hidden": "true" });
		const c = 160;
		const R = 150; // oltin hoshiya
		const r = 138; // bo'laklar
		const seg = 360 / variants.length;
		const pt = (deg, rad) => {
			// Burchak soat mili bo'yicha, tepadan (ko'rsatkich tepada)
			const a = (deg * Math.PI) / 180;
			return [c + rad * Math.sin(a), c - rad * Math.cos(a)];
		};
		const defs = svgEl("defs", {});
		defs.append(
			gradient("bb-g-a", [["0%", tones.light], ["55%", tones.base], ["100%", tones.dark]], "radialGradient", { cx: "50%", cy: "50%", r: "62%" }),
			gradient("bb-g-b", [["0%", "#ffffff"], ["100%", tones.pale]], "radialGradient", { cx: "50%", cy: "50%", r: "60%" }),
			gradient("bb-g-c", [["0%", "#ffe58a"], ["100%", "#ff9a1f"]], "radialGradient", { cx: "50%", cy: "50%", r: "60%" }),
			gradient("bb-g-rim", [["0%", "#fff6c9"], ["30%", "#f7c948"], ["55%", "#b9801a"], ["80%", "#ffe28a"], ["100%", "#c8901f"]], "linearGradient", { x1: "0", y1: "0", x2: "1", y2: "1" }),
			gradient("bb-g-gloss", [["0%", "#ffffff", 0.55], ["100%", "#ffffff", 0]], "linearGradient", { x1: "0", y1: "0", x2: "0", y2: "1" })
		);
		svg.append(defs);

		svg.append(svgEl("circle", { cx: c, cy: c, r: R + 6, class: "bb-halo" }));
		svg.append(svgEl("circle", { cx: c, cy: c, r: R, fill: "none", stroke: "url(#bb-g-rim)", "stroke-width": 20 }));

		const g = svgEl("g", { class: "bb-rotor" });
		const kinds = ["a", "b", "c"];
		variants.forEach((h, i) => {
			let k = kinds[i % 3];
			if (i === variants.length - 1 && i > 0 && k === kinds[0]) k = kinds[(i + 1) % 3]; // yonma-yon bir xil rang bo'lmasin
			const [x1, y1] = pt((i - 0.5) * seg, r);
			const [x2, y2] = pt((i + 0.5) * seg, r);
			g.append(svgEl("path", {
				d: `M${c},${c} L${x1},${y1} A${r},${r} 0 ${seg > 180 ? 1 : 0} 1 ${x2},${y2} Z`,
				fill: `url(#bb-g-${k})`,
				class: "bb-seg",
			}));
			const [tx, ty] = pt(i * seg, r * 0.64);
			const text = svgEl("text", { x: tx, y: ty, transform: `rotate(${i * seg} ${tx} ${ty})`, class: `bb-label bb-label--${k}` });
			const num = svgEl("tspan", { x: tx, class: "bb-label__num" });
			num.textContent = h;
			const unit = svgEl("tspan", { x: tx, dy: "1.25em", class: "bb-label__unit" });
			unit.textContent = "soat";
			text.append(num, unit);
			g.append(text);
		});
		g.append(svgEl("circle", { cx: c, cy: c, r, fill: "none", class: "bb-inner-ring" }));
		svg.append(g);

		// Hoshiyadagi lampochkalar (aylanmaydi — yugurib yonadi)
		const bulbs = svgEl("g", { class: "bb-bulbs" });
		const N = 24;
		for (let i = 0; i < N; i++) {
			const [bx, by] = pt((i * 360) / N, R);
			bulbs.append(svgEl("circle", { cx: bx, cy: by, r: 4.2, class: `bb-bulb${i % 2 ? " bb-bulb--odd" : ""}` }));
		}
		svg.append(bulbs);
		// Shisha gumbaz yaltirog'i
		svg.append(svgEl("path", {
			d: `M${c - r + 14},${c - 8} A${r - 14},${r - 14} 0 0 1 ${c + r - 14},${c - 8} Q${c},${c - 40} ${c - r + 14},${c - 8} Z`,
			fill: "url(#bb-g-gloss)",
			class: "bb-gloss",
		}));
		return { svg, g, seg };
	}

	function pointerSvg() {
		const svg = svgEl("svg", { viewBox: "0 0 40 52", class: "bb-pointer", "aria-hidden": "true" });
		const defs = svgEl("defs", {});
		defs.append(gradient("bb-g-pin", [["0%", "#ff6b6b"], ["100%", "#c9184a"]], "linearGradient", { x1: "0", y1: "0", x2: "1", y2: "1" }));
		svg.append(defs);
		svg.append(svgEl("path", { d: "M20 50 C14 38 4 30 4 19 a16 16 0 0 1 32 0 c0 11 -10 19 -16 31z", fill: "url(#bb-g-pin)", stroke: "#fff", "stroke-width": 2.5 }));
		svg.append(svgEl("circle", { cx: 20, cy: 19, r: 6, fill: "#fff" }));
		svg.append(svgEl("ellipse", { cx: 14, cy: 12, rx: 4, ry: 2.5, fill: "#fff", opacity: 0.55, transform: "rotate(-35 14 12)" }));
		return svg;
	}

	// ---------- Konfetti (yengil, kutubxonasiz) ----------
	function confetti(colors) {
		if (reduceMotion) return;
		const cv = el("canvas", "bb-confetti");
		const dpr = Math.min(window.devicePixelRatio || 1, 2);
		cv.width = innerWidth * dpr;
		cv.height = innerHeight * dpr;
		document.body.append(cv);
		const ctx = cv.getContext("2d");
		ctx.scale(dpr, dpr);
		const ox = innerWidth / 2;
		const oy = innerHeight * 0.38;
		const parts = Array.from({ length: 170 }, () => {
			const a = Math.random() * Math.PI * 2;
			const v = 5 + Math.random() * 9;
			return {
				x: ox, y: oy, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 6,
				w: 6 + Math.random() * 6, h: 4 + Math.random() * 6,
				rot: Math.random() * 6, vr: (Math.random() - 0.5) * 0.4,
				color: colors[(Math.random() * colors.length) | 0],
			};
		});
		const t0 = performance.now();
		const frame = (t) => {
			const life = (t - t0) / 2600;
			ctx.clearRect(0, 0, innerWidth, innerHeight);
			ctx.globalAlpha = Math.max(0, 1 - Math.max(0, life - 0.6) / 0.4);
			parts.forEach((p) => {
				p.vy += 0.28;
				p.vx *= 0.985;
				p.x += p.vx;
				p.y += p.vy;
				p.rot += p.vr;
				ctx.save();
				ctx.translate(p.x, p.y);
				ctx.rotate(p.rot);
				ctx.fillStyle = p.color;
				ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h * Math.abs(Math.cos(p.rot * 2)));
				ctx.restore();
			});
			if (life < 1) requestAnimationFrame(frame);
			else cv.remove();
		};
		requestAnimationFrame(frame);
	}

	function showWheel() {
		const root = document.documentElement;
		root.classList.add("bb-lock");
		document.body.classList.add("bb-lock");

		const overlay = el("div", "bb-overlay");
		const tones = setTones(overlay);
		overlay.append(el("span", "bb-orb bb-orb--1"), el("span", "bb-orb bb-orb--2"), el("span", "bb-orb bb-orb--3"));
		const card = el("div", "bb-card");
		card.setAttribute("role", "dialog");
		card.setAttribute("aria-modal", "true");
		card.setAttribute("aria-labelledby", "bb-title");
		const eyebrow = el("p", "bb-eyebrow", "Faqat siz uchun");
		const title = el("h2", "bb-title", "Omadingizni sinang!");
		title.id = "bb-title";
		const sub = el("p", "bb-sub", "Aylantiring va chegirma vaqtini yutib oling");

		const wrap = el("div", "bb-wheel-wrap");
		const { svg, g, seg } = wheelSvg(st.variants, tones);
		const spinBtn = el("button", "bb-spin");
		spinBtn.type = "button";
		spinBtn.append(el("span", "bb-spin__text", "Aylantirish"));
		const pin = pointerSvg();
		wrap.append(svg, pin, spinBtn);

		const result = el("div", "bb-result");
		result.hidden = true;
		result.setAttribute("aria-live", "polite");

		card.append(eyebrow, title, sub, wrap, result);
		overlay.append(card);
		document.body.append(overlay);
		spinBtn.focus({ preventScroll: true });

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
			overlay.classList.add("is-leaving");
			setTimeout(() => overlay.remove(), reduceMotion ? 0 : 260);
			root.classList.remove("bb-lock");
			document.body.classList.remove("bb-lock");
		};

		let busy = false;
		spinBtn.addEventListener("click", async () => {
			if (busy) return;
			busy = true;
			spinBtn.disabled = true;
			wrap.classList.add("is-spinning");
			const r = await api("spin", { shop: SF.shop });
			if (!r || !r.enabled) {
				// Server javob bermadi yoki aksiya o'chirildi: mijozni qamab qo'ymaymiz — sayt ishlayveradi
				if (r && !r.enabled) return close();
				busy = false;
				spinBtn.disabled = false;
				wrap.classList.remove("is-spinning");
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
			const turns = reduceMotion ? 1 : 7;
			const angle = turns * 360 - idx * seg + jitter;
			const ms = reduceMotion ? 600 : SPIN_MS;
			g.style.transformOrigin = "160px 160px";
			g.style.transition = `transform ${ms}ms cubic-bezier(.12,.72,.08,1)`;
			// Keyingi kadrda — brauzer boshlang'ich holatni ko'rib olsin, aks holda animatsiya bo'lmaydi
			requestAnimationFrame(() => requestAnimationFrame(() => (g.style.transform = `rotate(${angle}deg)`)));
			setTimeout(() => {
				wrap.classList.remove("is-spinning");
				wrap.classList.add("is-won");
				if (navigator.vibrate) navigator.vibrate([30, 40, 60]);
			}, ms);
			setTimeout(() => showResult({ card, wrap, result, eyebrow, title, sub, close, tones }), ms + 700);
		});
	}

	function showResult({ card, wrap, result, eyebrow, title, sub, close, tones }) {
		const p = st.product;
		const code = p.add || p.code;
		// Variantli tovar: shu tovarning biror varianti savatda bo'lsa, yana qo'shilmaydi
		const inCart = SF.cart && (p.codes || [code]).some((c) => SF.cart.qty(c) > 0);
		if (SF.cart && !inCart) {
			SF.cart.remember(code, { name: p.name, variant: p.variant || "", thumb: p.thumb || "", price: p.add_price || 0 });
			SF.cart.add(code, 1);
		}

		confetti([tones.base, tones.light, "#ffd23f", "#ff4d6d", "#3ddc97", "#4cc9f0", "#ffffff"]);
		// Baraban yig'iladi, o'rnida natija ochiladi
		wrap.style.height = `${wrap.offsetHeight}px`;
		requestAnimationFrame(() => wrap.classList.add("is-done"));
		eyebrow.textContent = "Yutuq";
		title.textContent = "Tabriklaymiz! 🎉";
		sub.hidden = true;

		result.replaceChildren();
		const prize = el("div", "bb-prize");
		prize.append(el("b", "bb-prize__num", String(st.win)), el("span", "bb-prize__text", "soatlik chegirma yutdingiz"));
		result.append(prize);

		const prod = el("div", "bb-product");
		const media = el("div", "bb-product__media");
		if (p.thumb) {
			const img = el("img");
			img.src = p.thumb;
			img.alt = "";
			media.append(img);
		}
		const off = st.old_price ? Math.round((1 - st.price / st.old_price) * 100) : 0;
		if (off > 0) media.append(el("span", "bb-product__off", `−${off}%`));
		const info = el("div", "bb-product__info");
		info.append(el("div", "bb-product__name", p.variant ? `${p.name} · ${p.variant}` : p.name));
		const price = el("div", "bb-product__price");
		price.append(el("b", "", fmt(st.price)));
		if (st.old_price) price.append(el("s", "", fmt(st.old_price)));
		info.append(price);
		const added = el("span", "bb-product__added", "✓ Savatga qo‘shildi");
		info.append(added);
		prod.append(media, info);
		result.append(prod);

		const timer = el("div", "bb-timer");
		timer.append(el("span", "bb-timer__label", "Chegirma tugashiga"), clock("bb-clock--lg"));
		result.append(timer);

		const go = el("button", "bb-go");
		go.type = "button";
		go.append(el("span", "", "Savatga o‘tish"));
		go.addEventListener("click", () => {
			location.href = `${SF.base}/savat${SF.preview ? `?layout=${encodeURIComponent(SF.preview)}` : ""}`;
		});
		const later = el("button", "bb-later", "Xaridni davom ettirish");
		later.type = "button";
		later.addEventListener("click", close);
		result.append(go, later);
		result.hidden = false;
		card.classList.add("is-result");
		// Fokus natijaga (ekran o'quvchi uchun), tugmada ramka chiqmasin
		result.tabIndex = -1;
		result.focus({ preventScroll: true });

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
