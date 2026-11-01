/* Sotuvchi paneli: tovarlar ro'yxati va tovar formasi (rasm, narx, rang/o'lcham, qoldiq — faqat ko'rish).
   Kirim (kimdan olindi, nechta, necha puldan) — Desk'dagi tovar formasining Ombor tabida.
   Kutubxonasiz. Server: marketplace.panel.* */
(() => {
	"use strict";

	const P = window.PANEL;
	const app = document.getElementById("app");
	const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const fmt = (n) => (n == null ? "—" : Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so‘m");
	const num = (v) => +String(v ?? "").replace(/\D/g, "") || 0;
	let boot = null;
	let filter = "all", query = "";

	function toast(text, bad = false) {
		const el = document.getElementById("toast");
		el.textContent = text;
		el.className = `p-toast is-on${bad ? " is-bad" : ""}`;
		clearTimeout(toast.t);
		toast.t = setTimeout(() => (el.className = "p-toast"), 2600);
	}

	async function api(method, args = {}, post = false) {
		const url = `/api/method/marketplace.panel.${method}`;
		const withShop = { ...args, shop: P.shop };
		const opts = post
			? { method: "POST", headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": P.csrf, Accept: "application/json" }, body: JSON.stringify(withShop) }
			: { headers: { Accept: "application/json" } };
		const res = await fetch(post ? url : `${url}?${new URLSearchParams(withShop)}`, opts);
		const body = await res.json().catch(() => ({}));
		if (!res.ok) {
			let msg = "Xatolik yuz berdi";
			try { msg = JSON.parse(JSON.parse(body._server_messages)[0]).message.replace(/<[^>]+>/g, ""); } catch { /* */ }
			throw new Error(msg);
		}
		return body.message;
	}

	async function upload(file) {
		const fd = new FormData();
		fd.append("file", file, file.name);
		fd.append("is_private", "1");
		fd.append("folder", "Home");
		const res = await fetch("/api/method/upload_file", { method: "POST", headers: { "X-Frappe-CSRF-Token": P.csrf }, body: fd });
		if (!res.ok) throw new Error("Rasm yuklanmadi");
		return (await res.json()).message.file_url;
	}

	// ================= Ro'yxat =================
	async function showList() {
		history.replaceState(null, "", location.pathname + location.search);
		const items = await api("list_products");
		const counts = {
			all: items.length,
			out: items.filter((i) => i.status === "out").length,
			low: items.filter((i) => i.status === "low").length,
			hidden: items.filter((i) => !i.published).length,
		};
		const s = boot.shop;
		app.innerHTML = `
			<header class="p-head">
				<span class="p-avatar" style="background:${esc(s.brand_color || "#1F5C4A")}">${s.logo ? `<img src="${esc(s.logo)}" alt="">` : esc(s.initials)}</span>
				<div class="p-head__t"><b>${esc(s.shop_name)}</b><small>Do‘kon paneli · ${esc(P.user)}</small></div>
				<a class="p-btn p-btn--ghost" href="${esc(s.url)}" target="_blank" rel="noopener">Saytni ko‘rish ↗</a>
			</header>
			${boot.is_manager ? `<label class="p-shopsel">Do‘kon: <select data-shop>${boot.shops.map((x) => `<option value="${esc(x.name)}" ${x.name === s.name ? "selected" : ""}>${esc(x.shop_name)}</option>`).join("")}</select></label>` : ""}
			<div class="p-stats">
				${[["all", "Tovarlar"], ["out", "Tugagan"], ["low", "Kam qolgan"], ["hidden", "Saytda emas"]]
					.map(([k, l]) => `<button class="p-stat p-stat--${k} ${filter === k ? "is-active" : ""}" data-filter="${k}"><b>${counts[k]}</b><span>${l}</span></button>`).join("")}
			</div>
			<label class="p-search"><svg><use href="#i-search"/></svg><input type="search" placeholder="Tovar nomi…" value="${esc(query)}" data-q></label>
			<div class="p-list" data-list></div>
			<button class="p-fab" data-new><svg><use href="#i-plus"/></svg>Tovar qo‘shish</button>`;

		const list = app.querySelector("[data-list]");
		const render = () => {
			const shown = items.filter((i) =>
				(filter === "all" || (filter === "hidden" ? !i.published : i.status === filter)) &&
				(!query || i.name.toLowerCase().includes(query.toLowerCase())));
			list.innerHTML = shown.length ? shown.map(row).join("") : `<p class="p-empty">${items.length ? "Mos tovar yo‘q" : "Hali tovar yo‘q. Pastdagi «Tovar qo‘shish» tugmasini bosing."}</p>`;
		};
		const row = (i) => {
			const stock = i.status === "out" ? `<span class="p-pill p-pill--out">Tugagan</span>`
				: i.status === "low" ? `<span class="p-pill p-pill--low">Kam: ${i.free} ta</span>`
				: `<span class="p-pill p-pill--ok">Omborda ${i.free} ta</span>`;
			return `
			<article class="p-item" data-open="${esc(i.code)}">
				<span class="p-item__img">${i.thumb ? `<img src="${esc(i.thumb)}" alt="" loading="lazy">` : `<svg><use href="#i-image"/></svg>`}</span>
				<div class="p-item__body">
					<b>${esc(i.name)}</b>
					<span class="p-item__meta">${fmt(i.price)}${i.variants ? ` · ${i.variants} variant` : ""}</span>
					<span class="p-item__tags">${stock}${i.reserved ? `<span class="p-pill">${i.reserved} ta buyurtmada</span>` : ""}${i.problems.map((p) => `<span class="p-pill p-pill--warn">${esc(p)}</span>`).join("")}</span>
				</div>
				<label class="p-switch" title="Saytda ko‘rsatish" data-stop><input type="checkbox" data-pub="${esc(i.code)}" ${i.published ? "checked" : ""}><span></span></label>
			</article>`;
		};
		render();

		app.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => { filter = b.dataset.filter; showList(); }));
		app.querySelector("[data-q]").addEventListener("input", (e) => { query = e.target.value; render(); });
		app.querySelector("[data-new]").addEventListener("click", () => showForm(null));
		app.querySelector("[data-shop]")?.addEventListener("change", (e) => { location.search = `?shop=${encodeURIComponent(e.target.value)}`; });
		list.addEventListener("click", (e) => {
			if (e.target.closest("[data-stop]")) return;
			const card = e.target.closest("[data-open]");
			if (card) showForm(card.dataset.open);
		});
		list.addEventListener("change", async (e) => {
			const cb = e.target.closest("[data-pub]");
			if (!cb) return;
			try {
				await api("set_published", { code: cb.dataset.pub, published: cb.checked ? 1 : 0 }, true);
				toast(cb.checked ? "Saytga chiqarildi" : "Saytdan olindi");
			} catch (err) { cb.checked = !cb.checked; toast(err.message, true); }
		});
	}

	// ================= Forma =================
	async function showForm(code) {
		const d = code ? await api("get_product", { code }) : {
			name: "", group: "", price: null, old_price: null, wholesale_price: null, wholesale_min: 10, spec: "",
			description: "", mxik: "", package_code: "", published: 1, images: [], has_variants: 0, colors: [], sizes: [], stock: { "|": { actual: 0, reserved: 0 } },
		};
		history.pushState({ form: true }, "", `#tovar${code ? "=" + encodeURIComponent(code) : ""}`);
		const locked = !!code; // variant turini saqlangandan keyin o'zgartirib bo'lmaydi
		const state = {
			images: [...d.images],
			useColors: d.colors.length > 0 || !!d.dims?.color,
			useSizes: d.sizes.length > 0 || !!d.dims?.size,
			colors: [...d.colors],
			sizes: [...d.sizes],
			stock: Object.fromEntries(Object.entries(d.stock).map(([k, v]) => [k, v.actual])),
			reserved: Object.fromEntries(Object.entries(d.stock).map(([k, v]) => [k, v.reserved])),
		};
		const groups = boot.groups.reduce((acc, g) => ((acc[g.parent_item_group] ||= []).push(g.name), acc), {});

		app.innerHTML = `
			<header class="p-formhead">
				<button class="p-round" data-back aria-label="Orqaga"><svg><use href="#i-back"/></svg></button>
				<h1>${code ? "Tovarni tahrirlash" : "Yangi tovar"}</h1>
			</header>

			<section class="p-card">
				<h2>Rasmlar <small>birinchisi — asosiy, 10 tagacha</small></h2>
				<div class="p-photos" data-photos></div>
			</section>

			<section class="p-card">
				<h2>Asosiy</h2>
				<label class="p-f"><span>Nomi *</span><input data-k="name" value="${esc(d.name)}" placeholder="Masalan: Zig‘ir ko‘ylak" maxlength="140"></label>
				<label class="p-f"><span>Kategoriya *</span><select data-k="group"><option value="">Tanlang…</option>
					${Object.entries(groups).map(([parent, list]) => `<optgroup label="${esc(parent)}">${list.map((g) => `<option ${g === d.group ? "selected" : ""}>${esc(g)}</option>`).join("")}</optgroup>`).join("")}
				</select></label>
				<div class="p-2">
					<label class="p-f"><span>Narx, so‘m *</span><input data-k="price" data-money inputmode="numeric" value="${d.price ? Math.round(d.price) : ""}" placeholder="189 000"></label>
					<label class="p-f"><span>Eski narx <small>(chegirma)</small></span><input data-k="old_price" data-money inputmode="numeric" value="${d.old_price ? Math.round(d.old_price) : ""}" placeholder="—"></label>
				</div>
				<label class="p-f"><span>Qisqa xususiyat</span><input data-k="spec" value="${esc(d.spec)}" placeholder="Masalan: 100% zig‘ir, erkin bichim" maxlength="140"></label>
				<label class="p-f"><span>Tavsif</span><textarea data-k="description" rows="3" placeholder="Mato, o‘lcham bo‘yicha maslahat, parvarish…">${esc(d.description)}</textarea></label>
			</section>

			<section class="p-card">
				<h2>Rang va o‘lcham</h2>
				${locked ? `<p class="p-hint">Rang/o‘lcham turi saqlangandan keyin o‘zgarmaydi, lekin yangi rang yoki o‘lcham qo‘shish mumkin.</p>` : ""}
				<label class="p-toggle"><input type="checkbox" data-use="colors" ${state.useColors ? "checked" : ""} ${locked ? "disabled" : ""}><span></span>Ranglari bor</label>
				<div class="p-colors" data-colors ${state.useColors ? "" : "hidden"}></div>
				<label class="p-toggle"><input type="checkbox" data-use="sizes" ${state.useSizes ? "checked" : ""} ${locked ? "disabled" : ""}><span></span>O‘lchamlari bor</label>
				<div data-sizes-box ${state.useSizes ? "" : "hidden"}>
					<div class="p-sizes" data-sizes></div>
					<div class="p-addsize"><input placeholder="Boshqa o‘lcham: 42, 98, 3XL…" maxlength="10" data-newsize><button class="p-btn p-btn--ghost" data-addsize>Qo‘shish</button></div>
				</div>
			</section>

			<section class="p-card">
				<h2>Omborda hozir <small data-total></small></h2>
				<div data-stock></div>
			</section>

			<details class="p-card" ${d.wholesale_price ? "open" : ""}>
				<summary><h2>Ulgurji narx</h2></summary>
				<div class="p-2">
					<label class="p-f"><span>Ulgurji narx, so‘m</span><input data-k="wholesale_price" data-money inputmode="numeric" value="${d.wholesale_price ? Math.round(d.wholesale_price) : ""}" placeholder="—"></label>
					<label class="p-f"><span>Kamida, dona</span><input data-k="wholesale_min" inputmode="numeric" value="${d.wholesale_min || 10}"></label>
				</div>
			</details>

			<section class="p-card">
				<h2>Fiskal chek</h2>
				<label class="p-f"><span>MXIK kodi * <a href="https://tasnif.soliq.uz" target="_blank" rel="noopener">topish ↗</a></span><input data-k="mxik" inputmode="numeric" value="${esc(d.mxik)}" placeholder="17 ta raqam" maxlength="20"></label>
				<label class="p-f"><span>Qadoq kodi</span><input data-k="package_code" value="${esc(d.package_code)}" placeholder="tasnif.soliq.uz dagi qadoq kodi"></label>
				<label class="p-toggle"><input type="checkbox" data-k="published" ${d.published ? "checked" : ""}><span></span>Saytda ko‘rsatish</label>
			</section>

			${code ? `<button class="p-link-danger" data-archive>Tovarni arxivlash</button>` : ""}
			<div class="p-savebar"><button class="p-btn p-btn--brand" data-save>Saqlash</button></div>`;

		const $ = (s) => app.querySelector(s);

		// ---- rasmlar ----
		const photos = $("[data-photos]");
		function renderPhotos() {
			photos.innerHTML = state.images.map((img, i) => `
				<div class="p-photo">
					<img src="${esc(img.thumb || img.image)}" alt="">
					${i === 0 ? `<span class="p-photo__main">Asosiy</span>` : `<button class="p-photo__left" data-left="${i}" aria-label="Oldinga">‹</button>`}
					<button class="p-photo__x" data-x="${i}" aria-label="O‘chirish">×</button>
				</div>`).join("") +
				(state.images.length < 10 ? `<label class="p-photo p-photo--add"><input type="file" accept="image/*" multiple hidden data-file><svg><use href="#i-plus"/></svg><span>Rasm</span></label>` : "");
		}
		photos.addEventListener("click", (e) => {
			const x = e.target.closest("[data-x]"), l = e.target.closest("[data-left]");
			if (x) { state.images.splice(+x.dataset.x, 1); renderPhotos(); }
			if (l) { const i = +l.dataset.left; [state.images[i - 1], state.images[i]] = [state.images[i], state.images[i - 1]]; renderPhotos(); }
		});
		photos.addEventListener("change", async (e) => {
			const input = e.target.closest("[data-file]");
			if (!input) return;
			const files = [...input.files].slice(0, 10 - state.images.length);
			for (const f of files) {
				if (f.size > 15 * 1024 * 1024) { toast(`${f.name}: 15 MB dan katta`, true); continue; }
				const preview = URL.createObjectURL(f);
				const slot = { image: null, thumb: preview, uploading: true };
				state.images.push(slot); renderPhotos();
				try { slot.image = await upload(f); slot.uploading = false; }
				catch (err) { state.images.splice(state.images.indexOf(slot), 1); toast(err.message, true); }
				renderPhotos();
			}
		});
		renderPhotos();

		// ---- ranglar va o'lchamlar ----
		const colorBox = $("[data-colors]"), sizeBox = $("[data-sizes]");
		const hexOf = Object.fromEntries(boot.colors.map((c) => [c.value, c.hex]));
		function renderVariants() {
			colorBox.innerHTML = boot.colors.map((c) => `
				<button class="p-chip ${state.colors.includes(c.value) ? "is-on" : ""}" data-color="${esc(c.value)}">
					<i style="background:${esc(c.hex || "#ccc")}"></i>${esc(c.value)}</button>`).join("");
			const allSizes = [...new Set([...boot.sizes, ...state.sizes])];
			sizeBox.innerHTML = allSizes.map((s) => `<button class="p-chip p-chip--size ${state.sizes.includes(s) ? "is-on" : ""}" data-size="${esc(s)}">${esc(s)}</button>`).join("");
			renderStock();
		}
		const toggle = (arr, v) => (arr.includes(v) ? arr.splice(arr.indexOf(v), 1) : arr.push(v));
		colorBox.addEventListener("click", (e) => { const b = e.target.closest("[data-color]"); if (b) { toggle(state.colors, b.dataset.color); renderVariants(); } });
		sizeBox.addEventListener("click", (e) => { const b = e.target.closest("[data-size]"); if (b) { toggle(state.sizes, b.dataset.size); renderVariants(); } });
		$("[data-addsize]").addEventListener("click", () => {
			const v = $("[data-newsize]").value.trim().toUpperCase();
			if (!/^[\w\-/.]{1,10}$/.test(v)) return toast("O‘lcham: 1–10 belgi", true);
			if (!state.sizes.includes(v)) state.sizes.push(v);
			$("[data-newsize]").value = "";
			renderVariants();
		});
		app.querySelectorAll("[data-use]").forEach((cb) => cb.addEventListener("change", () => {
			if (cb.dataset.use === "colors") { state.useColors = cb.checked; colorBox.hidden = !cb.checked; if (!cb.checked) state.colors = []; }
			else { state.useSizes = cb.checked; $("[data-sizes-box]").hidden = !cb.checked; if (!cb.checked) state.sizes = []; }
			renderVariants();
		}));

		// ---- qoldiq (faqat ko'rish): oddiy tovar — bitta son; variantli — rang × o'lcham jadvali ----
		const stockBox = $("[data-stock]");
		const KIRIM_HINT = "Yangi tovar kelsa — kompyuterda tovarni oching, <b>Ombor</b> tabida kimdan olganingizni, nechta kelganini va necha puldan olganingizni yozing. Sotilganda qoldiq o‘zi kamayadi.";
		function renderStock() {
			const cols = state.useSizes ? state.sizes : [""];
			const rows = state.useColors ? state.colors : [""];
			const variant = state.useColors || state.useSizes;
			const cell = (r, c) => {
				const k = `${r}|${c}`;
				const res = state.reserved[k] || 0;
				return `<span class="p-cell"><input value="${state.stock[k] ?? 0}" readonly tabindex="-1">${res ? `<small>${res} band</small>` : ""}</span>`;
			};
			if (!variant) {
				const res = state.reserved["|"] || 0;
				stockBox.innerHTML = `<div class="p-qty"><input value="${state.stock["|"] ?? 0}" readonly tabindex="-1"></div>
					<p class="p-hint">${res ? `Shundan ${res} tasi mijozlar buyurtmasida (band). ` : ""}${KIRIM_HINT}</p>`;
			} else if ((state.useColors && !rows.length) || (state.useSizes && !cols.length)) {
				stockBox.innerHTML = `<p class="p-hint">Avval ${state.useColors && !rows.length ? "rang" : "o‘lcham"}ni tanlang.</p>`;
			} else {
				stockBox.innerHTML = `
					<div class="p-gridwrap"><table class="p-grid">
						${state.useSizes ? `<tr><th></th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>` : ""}
						${rows.map((r) => `<tr><th>${r ? `<i style="background:${esc(hexOf[r] || "#ccc")}"></i>${esc(r)}` : "Soni"}</th>${cols.map((c) => `<td>${cell(r, c)}</td>`).join("")}</tr>`).join("")}
					</table></div>
					<p class="p-hint">Har bir katakda — shu rang va o‘lchamdan omborda nechta bor. 0 — tugagan, yangi rang/o‘lcham — hali kelmagan. ${KIRIM_HINT}</p>`;
			}
			updateTotal();
		}
		function updateTotal() {
			const cols = state.useSizes ? state.sizes : [""], rows = state.useColors ? state.colors : [""];
			let total = 0;
			for (const r of rows) for (const c of cols) total += +(state.stock[`${r}|${c}`] || 0);
			$("[data-total]").textContent = `· jami ${total} ta`;
		}
		renderVariants();

		// pul maydonlari: "189000" -> "189 000"
		app.querySelectorAll("[data-money]").forEach((inp) => {
			const f = () => { const n = num(inp.value); inp.value = n ? n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") : ""; };
			f(); inp.addEventListener("input", f);
		});

		$("[data-back]").addEventListener("click", () => history.back());
		$("[data-archive]")?.addEventListener("click", async () => {
			if (!confirm("Tovar saytdan olinadi va ro‘yxatda ko‘rinmaydi. Buyurtmalar tarixi saqlanadi. Davom etilsinmi?")) return;
			try { await api("archive_product", { code }, true); toast("Arxivlandi"); showList(); } catch (err) { toast(err.message, true); }
		});

		$("[data-save]").addEventListener("click", async () => {
			if (state.images.some((i) => i.uploading)) return toast("Rasmlar yuklanmoqda, biroz kuting", true);
			const val = (k) => app.querySelector(`[data-k="${k}"]`);
			const payload = {
				code,
				name: val("name").value, group: val("group").value,
				price: num(val("price").value), old_price: num(val("old_price").value),
				wholesale_price: num(val("wholesale_price").value), wholesale_min: num(val("wholesale_min").value) || 10,
				spec: val("spec").value, description: val("description").value,
				mxik: val("mxik").value, package_code: val("package_code").value,
				published: val("published").checked ? 1 : 0,
				images: state.images.map((i) => ({ image: i.image })),
				colors: state.useColors ? state.colors : [], sizes: state.useSizes ? state.sizes : [],
			};
			if (state.useColors && !payload.colors.length) return toast("Kamida bitta rang tanlang", true);
			if (state.useSizes && !payload.sizes.length) return toast("Kamida bitta o‘lcham tanlang", true);
			const btn = $("[data-save]");
			btn.disabled = true; btn.textContent = "Saqlanmoqda…";
			try {
				await api("save_product", { data: payload }, true);
				toast("Saqlandi ✓");
				history.back();
			} catch (err) {
				toast(err.message, true);
				btn.disabled = false; btn.textContent = "Saqlash";
			}
		});
	}

	window.addEventListener("popstate", () => { if (!location.hash.startsWith("#tovar")) showList(); });

	(async () => {
		try {
			boot = await api("bootstrap");
			P.shop = boot.shop.name;
			const m = location.hash.match(/^#tovar(?:=(.+))?$/);
			if (m) showForm(m[1] ? decodeURIComponent(m[1]) : null); else showList();
		} catch (err) {
			app.innerHTML = `<p class="p-empty">${esc(err.message)}</p>`;
		}
	})();
})();
