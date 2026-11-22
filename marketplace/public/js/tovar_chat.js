// Tovar murojaati chati — mijoz sahifasi (/s/<do'kon>/chat/<tovar>) va Sotuv paneli («Tovar murojaatlari») uchun bitta
// vidjet. Server: marketplace/sotuv/tovar_chat.py. Kutubxonasiz (sayt va Desk'da bir xil ishlaydi).
//
// Xabar holati (o'z xabarlarim): soat — yuborilmoqda, ✓ — serverga yetdi, ✓✓ — ikkinchi tomon o'qidi,
// qizil «!» — yuborilmadi (internet yo'q va h.k.): bosib turilsa (yoki bosilsa) — «Qayta yuborish» / «O'chirish».
// Yuborilgan xabarni bosib turish (kompyuterda o'ng tugma): matn — «Tahrirlash», hammasi — «O'chirish», «Nusxa olish».
// Har bir xabarga brauzer client_id beradi: qayta yuborilganda server ikkinchi nusxani yaratmaydi.
(function () {
	"use strict";

	const ICON = {
		clock: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.6V8l2.3 1.4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
		one: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 8.6l3.2 3.1 7.6-7.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
		two: '<svg viewBox="0 0 20 16" aria-hidden="true"><path d="M1.5 8.6l3.2 3.1 7.6-7.4M8.6 11.2l.5.5 7.6-7.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
		fail: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="9" fill="currentColor"/><path d="M10 5.2v6.2" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/><circle cx="10" cy="14.6" r="1.3" fill="#fff"/></svg>',
		smile: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.2 14.2c.9 1.3 2.2 2 3.8 2s2.9-.7 3.8-2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="9" cy="9.8" r="1.2" fill="currentColor"/><circle cx="15" cy="9.8" r="1.2" fill="currentColor"/></svg>',
		image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="15" rx="3" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="10" r="1.8" fill="currentColor"/><path d="M4 17l5-4.5 3.5 3 3-2.5L20 16.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
		send: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.4 11.1L19.2 4.3c.8-.4 1.6.4 1.2 1.2l-6.8 14.8c-.4.8-1.5.7-1.7-.1l-1.6-5.6a1 1 0 0 0-.7-.7L4 12.3c-.8-.2-.9-1.3-.1-1.7z" fill="currentColor"/></svg>',
		close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
		pen: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
		down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
	};
	const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
	const IMAGE_MAX = 10 * 1024 * 1024;
	const LONG_PRESS = 450;

	const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const pad = (n) => String(n).padStart(2, "0");
	const localStamp = (d = new Date()) =>
		`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
	const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
	// Havolalar bosiladigan bo'lsin (faqat http/https), qolgani — oddiy matn
	const linkify = (text) => esc(text).replace(/\bhttps?:\/\/[^\s<]+[^\s<.,;:!?)"'»]/g, (u) => `<a href="${u}" target="_blank" rel="noopener nofollow">${u}</a>`);

	function dayLabel(day) {
		const today = localStamp().slice(0, 10);
		const y = new Date();
		y.setDate(y.getDate() - 1);
		if (day === today) return "Bugun";
		if (day === localStamp(y).slice(0, 10)) return "Kecha";
		const [yy, mm, dd] = day.split("-").map(Number);
		return `${dd}-${MONTHS[mm - 1]}${yy !== new Date().getFullYear() ? ` ${yy}` : ""}`;
	}

	// Telefonda kamera rasmi 5–10 MB bo'ladi: yuborishdan oldin 1600px JPEG'ga kichraytiramiz (server ham shunday qiladi)
	async function shrink(file) {
		if (!window.createImageBitmap || !/^image\/(jpeg|png|webp)$/.test(file.type)) return file;
		try {
			const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
			const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
			if (k === 1 && file.size < 1.5 * 1024 * 1024) return file;
			const c = document.createElement("canvas");
			c.width = Math.round(bmp.width * k);
			c.height = Math.round(bmp.height * k);
			const g = c.getContext("2d");
			g.fillStyle = "#fff";
			g.fillRect(0, 0, c.width, c.height);
			g.drawImage(bmp, 0, 0, c.width, c.height);
			const blob = await new Promise((ok) => c.toBlob(ok, "image/jpeg", 0.85));
			return blob ? new File([blob], "rasm.jpg", { type: "image/jpeg" }) : file;
		} catch (e) {
			return file;
		}
	}

	class MpChat {
		/**
		 * @param {HTMLElement} root
		 * @param {{side: "Mijoz"|"Sotuvchi", transport: object, poll?: number, empty?: string, onChange?: Function, toast?: Function}} opts
		 * transport: open(since, read) / send(fields, file) / edit(id, matn) / remove(id) — Promise qaytaradi.
		 */
		constructor(root, opts) {
			this.root = root;
			this.o = Object.assign({ poll: 3000, empty: "Savolingizni yozing — sotuvchi shu yerda javob beradi." }, opts);
			this.t = this.o.transport;
			this.msgs = new Map(); // serverdagi xabarlar: id -> xabar
			this.local = new Map(); // hali serverga yetmagan: client_id -> {..., state: "pending" | "failed"}
			this.nodes = new Map(); // DOM: kalit -> {el, sig}
			this.since = null;
			this.editing = null;
			this.stickers = [];
			this.stick = true; // foydalanuvchi pastda turibdi — yangi xabar/rasm yuklanganda pastda qolsin
			this.build();
		}

		// ---------- Tuzilish ----------
		build() {
			this.root.classList.add("mpc");
			this.root.innerHTML = `
				<div class="mpc-scroll" data-scroll>
					<div class="mpc-list" data-list role="log" aria-live="polite" aria-label="Xabarlar"></div>
					<p class="mpc-empty" data-empty hidden>${esc(this.o.empty)}</p>
				</div>
				<button type="button" class="mpc-jump" data-jump hidden aria-label="Pastga — yangi xabarlar">${ICON.down}<span data-jump-n></span></button>
				<div class="mpc-stickers" data-stickers hidden role="listbox" aria-label="Stikerlar"></div>
				<div class="mpc-editbar" data-editbar hidden>
					${ICON.pen}<span><b>Tahrirlash</b><small data-edit-text></small></span>
					<button type="button" data-edit-cancel aria-label="Tahrirlashni bekor qilish">${ICON.close}</button>
				</div>
				<form class="mpc-compose" data-form>
					<button type="button" class="mpc-ibtn" data-sticker-btn aria-label="Stikerlar" aria-expanded="false">${ICON.smile}</button>
					<textarea data-input rows="1" maxlength="4000" placeholder="Xabar yozing…" aria-label="Xabar"></textarea>
					<label class="mpc-ibtn" aria-label="Rasm yuborish" title="Rasm yuborish">${ICON.image}<input type="file" accept="image/*" data-file hidden></label>
					<button type="submit" class="mpc-send" data-send aria-label="Yuborish" disabled>${ICON.send}</button>
				</form>
				<div class="mpc-menu" data-menu hidden role="menu"></div>
				<div class="mpc-view" data-view hidden role="dialog" aria-label="Rasm"><img alt=""><button type="button" aria-label="Yopish">${ICON.close}</button></div>`;
			const q = (s) => this.root.querySelector(s);
			Object.assign(this, {
				$scroll: q("[data-scroll]"), $list: q("[data-list]"), $empty: q("[data-empty]"), $jump: q("[data-jump]"),
				$stickers: q("[data-stickers]"), $editbar: q("[data-editbar]"), $form: q("[data-form]"), $input: q("[data-input]"),
				$file: q("[data-file]"), $send: q("[data-send]"), $menu: q("[data-menu]"), $view: q("[data-view]"),
			});
			this.bind();
		}

		bind() {
			const coarse = matchMedia("(pointer: coarse)").matches;
			this.$input.addEventListener("input", () => this.syncInput());
			this.$input.addEventListener("keydown", (e) => {
				// Kompyuterda Enter — yuborish, Shift+Enter — yangi qator; telefonda Enter — yangi qator
				if (e.key === "Enter" && !e.shiftKey && !coarse && !e.isComposing) {
					e.preventDefault();
					this.submit();
				}
				if (e.key === "Escape" && this.editing) this.cancelEdit();
			});
			this.$form.addEventListener("submit", (e) => {
				e.preventDefault();
				this.submit();
			});
			this.$file.addEventListener("change", () => {
				const f = this.$file.files[0];
				this.$file.value = "";
				if (f) this.sendImage(f);
			});
			this.root.querySelector("[data-sticker-btn]").addEventListener("click", (e) => this.toggleStickers(e.currentTarget));
			this.$stickers.addEventListener("click", (e) => {
				const b = e.target.closest("[data-st]");
				if (!b) return;
				this.toggleStickers(null, false);
				this.queue({ turi: "Stiker", stiker: b.dataset.st });
			});
			this.root.querySelector("[data-edit-cancel]").addEventListener("click", () => this.cancelEdit());
			this.$scroll.addEventListener("scroll", () => {
				this.stick = this.nearBottom();
				if (this.stick) this.setJump(0);
			}, { passive: true });
			// Rasm keyin yuklanadi va balandlik o'zgaradi: pastda turgan bo'lsa — pastda qolsin
			this.$list.addEventListener("load", () => this.stick && this.toBottom(), true);
			this.$jump.addEventListener("click", () => this.toBottom(true));
			this.$view.addEventListener("click", () => this.closeView());

			// Xabarni bosib turish (telefon) yoki o'ng tugma (kompyuter) — menyu; qizil «!» bosilsa ham
			let timer = null, start = null, fired = false;
			const cancel = () => { clearTimeout(timer); timer = null; };
			this.$list.addEventListener("pointerdown", (e) => {
				const row = e.target.closest("[data-key]");
				if (!row || e.button > 0) return;
				fired = false;
				start = [e.clientX, e.clientY];
				cancel();
				timer = setTimeout(() => { fired = true; this.openMenu(row, start); }, LONG_PRESS);
			});
			this.$list.addEventListener("pointermove", (e) => {
				if (timer && start && Math.hypot(e.clientX - start[0], e.clientY - start[1]) > 10) cancel();
			});
			["pointerup", "pointercancel", "pointerleave"].forEach((ev) => this.$list.addEventListener(ev, cancel));
			this.$list.addEventListener("contextmenu", (e) => {
				const row = e.target.closest("[data-key]");
				if (!row) return;
				e.preventDefault();
				cancel();
				if (!fired) this.openMenu(row, [e.clientX, e.clientY]);
			});
			this.$list.addEventListener("click", (e) => {
				if (fired) { fired = false; e.preventDefault(); return; }
				const fail = e.target.closest("[data-fail]");
				if (fail) return this.openMenu(fail.closest("[data-key]"), [e.clientX, e.clientY]);
				const img = e.target.closest("[data-photo]");
				if (img) this.openView(img.getAttribute("src"));
			});
			this.$menu.addEventListener("click", (e) => {
				const b = e.target.closest("[data-act]");
				if (b) this.act(b.dataset.act, this.$menu.dataset.key);
				this.closeMenu();
			});
			this._outside = (e) => {
				if (!this.$menu.hidden && !this.$menu.contains(e.target)) this.closeMenu();
				if (!this.$stickers.hidden && !this.$stickers.contains(e.target) && !e.target.closest("[data-sticker-btn]")) this.toggleStickers(null, false);
			};
			document.addEventListener("pointerdown", this._outside);
			this._keys = (e) => {
				if (e.key !== "Escape") return;
				this.closeMenu();
				this.closeView();
			};
			document.addEventListener("keydown", this._keys);
			this._vis = () => document.visibilityState === "visible" && this.poll();
			document.addEventListener("visibilitychange", this._vis);
			this._online = () => this.poll();
			window.addEventListener("online", this._online);
		}

		// ---------- Server bilan ----------
		async start() {
			await this.poll(true);
			this.toBottom();
			this.timer = setInterval(() => document.visibilityState === "visible" && this.poll(), this.o.poll);
		}

		destroy() {
			clearInterval(this.timer);
			document.removeEventListener("pointerdown", this._outside);
			document.removeEventListener("keydown", this._keys);
			document.removeEventListener("visibilitychange", this._vis);
			window.removeEventListener("online", this._online);
		}

		async poll(first = false) {
			if (this.busy) return (this.again = true);
			this.busy = true;
			try {
				const read = document.visibilityState === "visible" ? 1 : 0;
				const r = await this.t.open(first ? null : this.since, read);
				if (r.stickers) this.stickers = r.stickers;
				if (first) this.info = r;
				this.apply(r.messages || [], r.since);
				this.o.onChange?.(r);
			} catch (e) {
				if (first) this.o.toast?.(e.message);
			} finally {
				this.busy = false;
				if (this.again) {
					this.again = false;
					this.poll();
				}
			}
		}

		apply(list, since) {
			let incoming = 0;
			for (const m of list) {
				if (m.client_id) this.local.delete(m.client_id);
				if (m.ochirilgan) this.msgs.delete(m.id);
				else {
					if (!this.msgs.has(m.id) && !m.mine) incoming++;
					this.msgs.set(m.id, m);
				}
			}
			if (since && (!this.since || since > this.since)) this.since = since;
			const stick = this.stick || this.nearBottom();
			this.render();
			if (stick) this.toBottom();
			else if (incoming) this.setJump((this._jumpN || 0) + incoming);
		}

		// ---------- Yuborish ----------
		syncInput() {
			const el = this.$input;
			el.style.height = "auto";
			el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
			this.$send.disabled = !el.value.trim();
		}

		submit() {
			const text = this.$input.value.trim();
			if (!text) return;
			if (this.editing) return this.saveEdit(text);
			this.$input.value = "";
			this.syncInput();
			this.queue({ turi: "Matn", matn: text });
			this.$input.focus();
		}

		async sendImage(file) {
			if (!/^image\//.test(file.type)) return this.o.toast?.("Faqat rasm yuborish mumkin");
			const small = await shrink(file);
			if (small.size > IMAGE_MAX) return this.o.toast?.("Rasm 10 MB dan katta");
			this.queue({ turi: "Rasm", file: small, preview: URL.createObjectURL(small) });
		}

		queue(m) {
			const item = Object.assign({ client_id: newId(), vaqt: localStamp(), state: "pending", mine: true }, m);
			this.local.set(item.client_id, item);
			this.render();
			this.toBottom(true);
			this.deliver(item);
		}

		async deliver(item) {
			item.state = "pending";
			this.render();
			if (navigator.onLine === false) return this.failed(item, "Internet yo‘q");
			try {
				const r = await this.t.send({ client_id: item.client_id, turi: item.turi, matn: item.matn, stiker: item.stiker }, item.file);
				this.local.delete(item.client_id);
				if (item.preview) URL.revokeObjectURL(item.preview);
				this.msgs.set(r.message.id, r.message);
				this.render();
				this.toBottom();
				this.o.onChange?.(r);
			} catch (e) {
				this.failed(item, e.message);
			}
		}

		failed(item, why) {
			item.state = "failed";
			item.why = why || "Yuborilmadi";
			this.render();
		}

		// ---------- Menyu: qayta yuborish / tahrirlash / o'chirish / nusxa ----------
		find(key) {
			return key.startsWith("l:") ? this.local.get(key.slice(2)) : this.msgs.get(key.slice(2));
		}

		openMenu(row, [x, y]) {
			const m = row && this.find(row.dataset.key);
			if (!m || m.turi === "Tovar") return;
			const acts = [];
			if (m.state === "failed") acts.push(["retry", "Qayta yuborish"], ["drop", "O‘chirish", true]);
			else if (m.state !== "pending") {
				if (m.turi === "Matn") acts.push(["copy", "Nusxa olish"]);
				if (m.mine && m.turi === "Matn") acts.push(["edit", "Tahrirlash"]);
				if (m.mine) acts.push(["delete", "O‘chirish", true]);
			}
			if (!acts.length) return;
			navigator.vibrate?.(10);
			const head = m.state === "failed" ? `<p class="mpc-menu__why">${ICON.fail}${esc(m.why || "Yuborilmadi")}</p>` : "";
			this.$menu.innerHTML = head + acts.map(([a, l, danger]) => `<button type="button" role="menuitem" data-act="${a}" class="${danger ? "is-danger" : ""}">${l}</button>`).join("");
			this.$menu.dataset.key = row.dataset.key;
			this.$menu.hidden = false;
			const box = this.root.getBoundingClientRect(), mw = this.$menu.offsetWidth, mh = this.$menu.offsetHeight;
			this.$menu.style.left = `${Math.max(8, Math.min(x - box.left, box.width - mw - 8))}px`;
			this.$menu.style.top = `${Math.max(8, Math.min(y - box.top, box.height - mh - 8))}px`;
			this.$menu.querySelector("button")?.focus({ preventScroll: true });
			row.classList.add("is-picked");
		}

		closeMenu() {
			this.$menu.hidden = true;
			this.$list.querySelector(".is-picked")?.classList.remove("is-picked");
		}

		async act(action, key) {
			const m = this.find(key);
			if (!m) return;
			if (action === "retry") return this.deliver(m);
			if (action === "drop") {
				this.local.delete(m.client_id);
				if (m.preview) URL.revokeObjectURL(m.preview);
				return this.render();
			}
			if (action === "copy") {
				try { await navigator.clipboard.writeText(m.matn || ""); this.o.toast?.("Nusxa olindi"); } catch (e) { /* ruxsat yo'q */ }
				return;
			}
			if (action === "edit") {
				this.editing = m;
				this.$editbar.hidden = false;
				this.$editbar.querySelector("[data-edit-text]").textContent = m.matn;
				this.$input.value = m.matn;
				this.syncInput();
				this.$input.focus();
				return;
			}
			if (action === "delete") {
				const keep = this.msgs.get(m.id);
				this.msgs.delete(m.id);
				this.render();
				try {
					await this.t.remove(m.id);
				} catch (e) {
					this.msgs.set(m.id, keep);
					this.render();
					this.o.toast?.(e.message || "O‘chirilmadi");
				}
			}
		}

		cancelEdit() {
			this.editing = null;
			this.$editbar.hidden = true;
			this.$input.value = "";
			this.syncInput();
		}

		async saveEdit(text) {
			const m = this.editing;
			this.cancelEdit();
			if (text === m.matn) return;
			const before = Object.assign({}, m);
			this.msgs.set(m.id, Object.assign({}, m, { matn: text, tahrirlangan: true }));
			this.render();
			try {
				const r = await this.t.edit(m.id, text);
				this.msgs.set(r.id, r);
			} catch (e) {
				this.msgs.set(m.id, before);
				this.o.toast?.(e.message || "Saqlanmadi");
			}
			this.render();
		}

		toggleStickers(btn, show) {
			const open = show ?? this.$stickers.hidden;
			if (open && !this.$stickers.childElementCount) {
				this.$stickers.innerHTML = this.stickers.map((s) => `<button type="button" role="option" data-st="${esc(s)}" aria-label="${esc(s)}">${esc(s)}</button>`).join("");
			}
			this.$stickers.hidden = !open;
			this.root.querySelector("[data-sticker-btn]").setAttribute("aria-expanded", String(open));
		}

		openView(src) {
			this.$view.querySelector("img").src = src;
			this.$view.hidden = false;
		}

		closeView() {
			this.$view.hidden = true;
		}

		// ---------- Chizish ----------
		ordered() {
			const server = [...this.msgs.values()].filter((m) => m.turi !== "Tovar").sort((a, b) => (a.vaqt < b.vaqt ? -1 : a.vaqt > b.vaqt ? 1 : 0));
			const local = [...this.local.values()].sort((a, b) => (a.vaqt < b.vaqt ? -1 : 1));
			return [...server.map((m) => ["s:" + m.id, m]), ...local.map((m) => ["l:" + m.client_id, m])];
		}

		render() {
			// Tovar kartasi — doim tepada (mijoz hali yozmagan bo'lsa ham qaysi tovar haqida ekani ko'rinsin)
			const want = this.info && this.info.tovar ? [["card", { turi: "Tovar" }]] : [];
			let day = null;
			for (const [key, m] of this.ordered()) {
				const d = m.vaqt.slice(0, 10);
				if (d !== day) {
					day = d;
					want.push(["d:" + d, { day: d }]);
				}
				want.push([key, m]);
			}
			const keep = new Set(want.map(([k]) => k));
			for (const [k, n] of this.nodes) {
				if (!keep.has(k)) {
					n.el.remove();
					this.nodes.delete(k);
				}
			}
			let prev = null;
			for (const [key, m] of want) {
				const html = m.day ? `<span>${dayLabel(m.day)}</span>` : this.bubble(m);
				let n = this.nodes.get(key);
				if (!n) {
					const el = document.createElement("div");
					if (!m.day) el.dataset.key = key;
					n = { el, sig: null };
					this.nodes.set(key, n);
				}
				const cls = m.day ? "mpc-day" : `mpc-row ${m.turi === "Tovar" ? "mpc-row--card" : m.mine ? "mpc-row--mine" : "mpc-row--theirs"}${m.state ? ` is-${m.state}` : ""}`;
				if (n.sig !== html + cls) {
					n.el.className = cls;
					n.el.innerHTML = html;
					n.sig = html + cls;
				}
				const after = prev ? prev.nextSibling : this.$list.firstChild;
				if (after !== n.el) this.$list.insertBefore(n.el, after);
				prev = n.el;
			}
			this.$empty.hidden = want.length > (this.info && this.info.tovar ? 1 : 0);
		}

		bubble(m) {
			if (m.turi === "Tovar") {
				const p = (this.info && this.info.tovar) || {};
				return `<a class="mpc-card" href="${esc(p.url || "#")}" target="_blank" rel="noopener">
					${p.thumb ? `<img src="${esc(p.thumb)}" alt="" loading="lazy">` : `<span class="mpc-card__ph"></span>`}
					<span><small>Tovar bo‘yicha murojaat</small><b>${esc(p.name || "Tovar")}</b>${p.price_text ? `<em>${esc(p.price_text)}</em>` : ""}</span></a>`;
			}
			const time = m.vaqt.slice(11, 16);
			let status = "";
			if (m.mine) {
				if (m.state === "failed") status = `<button type="button" class="mpc-fail" data-fail aria-label="Yuborilmadi — qayta yuborish">${ICON.fail}</button>`;
				else if (m.state === "pending") status = `<span class="mpc-tick" title="Yuborilmoqda">${ICON.clock}</span>`;
				else status = `<span class="mpc-tick${m.oqilgan ? " is-read" : ""}" title="${m.oqilgan ? "O‘qildi" : "Yuborildi"}">${m.oqilgan ? ICON.two : ICON.one}</span>`;
			}
			const meta = `<span class="mpc-meta">${m.tahrirlangan ? "tahrirlangan · " : ""}<time>${time}</time>${status}</span>`;
			if (m.turi === "Stiker") return `<div class="mpc-sticker" role="img" aria-label="Stiker ${esc(m.stiker)}">${esc(m.stiker)}</div>${meta}`;
			if (m.turi === "Rasm") {
				const src = m.preview || m.rasm;
				return `<div class="mpc-bubble mpc-bubble--photo"><img src="${esc(src)}" alt="Rasm" data-photo loading="lazy">${meta}</div>`;
			}
			return `<div class="mpc-bubble"><span class="mpc-text">${linkify(m.matn)}</span>${meta}</div>`;
		}

		nearBottom() {
			const s = this.$scroll;
			return s.scrollHeight - s.scrollTop - s.clientHeight < 80;
		}

		toBottom(smooth) {
			requestAnimationFrame(() => {
				this.$scroll.scrollTo({ top: this.$scroll.scrollHeight, behavior: smooth && !matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "auto" });
				this.stick = true;
				this.setJump(0);
			});
		}

		setJump(n) {
			this._jumpN = n;
			this.$jump.hidden = !n;
			this.$jump.querySelector("[data-jump-n]").textContent = n ? String(n) : "";
		}
	}

	// ---------- Server bilan aloqa ----------
	function errorText(body, status) {
		if (status === 429) return "Juda tez yozyapsiz. Birozdan keyin qayta urinib ko‘ring.";
		try {
			return JSON.parse(JSON.parse(body._server_messages)[0]).message.replace(/<[^>]+>/g, "");
		} catch (e) {
			return status >= 500 ? "Serverda xatolik. Qayta urinib ko‘ring." : "Yuborilmadi";
		}
	}

	// Desk'da ham, saytda ham: JSON yoki (rasm bo'lsa) FormData
	MpChat.call = async function (method, data, file, csrf) {
		const opts = { method: "POST", headers: { Accept: "application/json" }, credentials: "same-origin" };
		if (csrf) opts.headers["X-Frappe-CSRF-Token"] = csrf;
		if (file) {
			const fd = new FormData();
			Object.entries(data || {}).forEach(([k, v]) => v != null && fd.append(k, v));
			fd.append("rasm", file, file.name || "rasm.jpg");
			opts.body = fd;
		} else {
			opts.headers["Content-Type"] = "application/json";
			opts.body = JSON.stringify(data || {});
		}
		let res;
		try {
			res = await fetch(`/api/method/marketplace.sotuv.tovar_chat.${method}`, opts);
		} catch (e) {
			throw new Error("Internet yo‘q");
		}
		const body = await res.json().catch(() => ({}));
		if (!res.ok) {
			const err = new Error(errorText(body, res.status));
			err.status = res.status;
			throw err;
		}
		return body.message;
	};

	MpChat.ICON = ICON;
	window.MpChat = MpChat;

	// ---------- Mijoz sahifasi: /s/<do'kon>/chat/<tovar> ----------
	function toast(text) {
		const el = document.getElementById("sf-toast");
		if (!el || !text) return;
		el.textContent = text;
		el.classList.add("is-on");
		clearTimeout(toast.t);
		toast.t = setTimeout(() => el.classList.remove("is-on"), 2600);
	}

	document.querySelectorAll("[data-tovar-chat]").forEach((el) => {
		const shop = el.dataset.shop, tovar = el.dataset.tovar, csrf = (window.SF && window.SF.csrf) || "";
		const call = (m, d, f) => MpChat.call(m, Object.assign({ shop, tovar }, d), f, csrf).catch((e) => {
			if (e.status === 401 || e.status === 403) setTimeout(() => location.reload(), 800); // sessiya tugagan
			throw e;
		});
		const chat = new MpChat(el, {
			side: "Mijoz",
			toast,
			transport: {
				open: (since, read) => call("mijoz_ochish", { since, oqidi: read }),
				send: (fields, file) => call("mijoz_yuborish", fields, file),
				edit: (xabar, matn) => call("mijoz_tahrirlash", { xabar, matn }),
				remove: (xabar) => call("mijoz_ochirish", { xabar }),
			},
		});
		chat.start();
	});
})();
