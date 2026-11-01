// Qo'ng'iroq yozuvi — Telegram'dagi ovozli xabar kabi: ▶ tugma, to'lqin (yozuvning o'zidan), vaqt, hajm va sana.
//   mp.voice_note(url, {date, who})  — HTML (Sotuv paneli, Telefon Qongiroq formasi)
//   mp.voice_init($root)            — chizilgandan keyin: faylni yuklab to'lqin, uzunlik va hajmni hisoblaydi
// Bir vaqtda bitta yozuv o'ynaydi; to'lqinni bossa — o'sha joydan.
window.mp = window.mp || {};

const MP_VN_BARS = 42;
const MP_VN_PLAY = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M8 5.5v13l11-6.5z"/></svg>`;
const MP_VN_PAUSE = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>`;

mp.voice_note = function (url, { date = "", who = "" } = {}) {
	mp.inject_voice_style();
	const esc = frappe.utils.escape_html;
	const bars = Array.from({ length: MP_VN_BARS }, () => `<i style="height:20%"></i>`).join("");
	return `
		<div class="mp-vn" data-vn="${esc(url)}">
			<button type="button" class="mp-vn__btn" aria-label="${__("Tinglash")}">${MP_VN_PLAY}</button>
			<div class="mp-vn__body">
				<div class="mp-vn__wave">${bars}</div>
				<div class="mp-vn__meta">
					<span data-vn-time>--:--</span><span data-vn-size></span>
					<span class="mp-vn__date">${esc([date, who].filter(Boolean).join(" · "))}</span>
				</div>
			</div>
		</div>`;
};

mp.voice_init = function ($root) {
	$($root).find(".mp-vn:not([data-vn-ready])").each((_, el) => {
		el.dataset.vnReady = "1";
		mp._vn_load(el);
		$(el).find(".mp-vn__btn").on("click", () => mp._vn_toggle(el));
		$(el).find(".mp-vn__wave").on("click", (e) => {
			const rect = e.currentTarget.getBoundingClientRect();
			mp._vn_seek(el, (e.clientX - rect.left) / rect.width);
		});
	});
};

mp._vn_fmt = (sec) => {
	sec = Math.max(0, Math.round(sec || 0));
	return `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(sec % 60).padStart(2, "0")}`;
};

mp._vn_load = async function (el) {
	const st = (el._vn = { audio: null, duration: 0 });
	try {
		const res = await fetch(el.dataset.vn, { credentials: "same-origin" });
		if (!res.ok) throw new Error(res.status);
		const buf = await res.arrayBuffer();
		const kb = buf.byteLength / 1024;
		$(el).find("[data-vn-size]").text(kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb.toFixed(1)} KB`);
		st.audio = new Audio(URL.createObjectURL(new Blob([buf])));
		st.audio.preload = "metadata";
		st.audio.addEventListener("timeupdate", () => mp._vn_progress(el));
		st.audio.addEventListener("ended", () => mp._vn_stop(el, true));
		st.audio.addEventListener("loadedmetadata", () => {
			if (!st.duration && isFinite(st.audio.duration)) {
				st.duration = st.audio.duration;
				$(el).find("[data-vn-time]").text(mp._vn_fmt(st.duration));
			}
		});
		// To'lqin — avval faylning baytlaridan (siqilgan ovozda baland joy ko'proq bayt oladi), keyin brauzer
		// ovozni ochib bera olsa — haqiqiy balandlikdan
		mp._vn_draw(el, mp._vn_byte_peaks(new Uint8Array(buf)));
		const ctx = new (window.AudioContext || window.webkitAudioContext)();
		const decoded = await ctx.decodeAudioData(buf.slice(0));
		ctx.close();
		st.duration = decoded.duration;
		$(el).find("[data-vn-time]").text(mp._vn_fmt(st.duration));
		const data = decoded.getChannelData(0);
		const step = Math.floor(data.length / MP_VN_BARS) || 1;
		const peaks = [];
		for (let i = 0; i < MP_VN_BARS; i++) {
			let max = 0;
			for (let j = i * step; j < (i + 1) * step && j < data.length; j += 8) max = Math.max(max, Math.abs(data[j]));
			peaks.push(max);
		}
		mp._vn_draw(el, peaks);
		// Telefon qo'ng'iroq ovozini bermagan (Android mikrofonni yopgan): fayl bor, ichi jim
		if (Math.max(...peaks) < 0.02) {
			el.classList.add("is-silent");
			$(el).find(".mp-vn__date").before(`<span class="mp-vn__warn">${__("ovoz yozilmagan (jim)")}</span>`);
		}
	} catch (e) {
		if (!st.audio) {
			$(el).addClass("is-broken").find("[data-vn-time]").text(__("Yozuvni ochib bo‘lmadi"));
		}
	}
};

mp._vn_byte_peaks = function (bytes) {
	// Boshidagi va oxiridagi sarlavhalarni (mp4 moov/ftyp) chetlab o'tamiz
	const from = Math.floor(bytes.length * 0.03), to = Math.floor(bytes.length * 0.97);
	const step = Math.max(1, Math.floor((to - from) / MP_VN_BARS));
	const peaks = [];
	for (let i = 0; i < MP_VN_BARS; i++) {
		let sum = 0, n = 0;
		for (let j = from + i * step; j < from + (i + 1) * step && j < to; j += 4, n++) sum += Math.abs(bytes[j] - 128);
		peaks.push(n ? sum / n : 0);
	}
	const min = Math.min(...peaks);
	return peaks.map((p) => (p - min) ** 2);
};

mp._vn_draw = function (el, peaks) {
	const top = Math.max(...peaks) || 1;
	$(el).find(".mp-vn__wave i").each((i, bar) => (bar.style.height = `${Math.max(14, Math.round((peaks[i] / top) * 100))}%`));
};

mp._vn_toggle = function (el) {
	const st = el._vn;
	if (!st || !st.audio) return;
	if (st.audio.paused) {
		document.querySelectorAll(".mp-vn.is-playing").forEach((other) => other !== el && mp._vn_stop(other, false));
		st.audio.play();
		el.classList.add("is-playing");
		$(el).find(".mp-vn__btn").html(MP_VN_PAUSE);
	} else {
		mp._vn_stop(el, false);
	}
};

mp._vn_stop = function (el, ended) {
	const st = el._vn;
	if (st?.audio) {
		st.audio.pause();
		if (ended) st.audio.currentTime = 0;
	}
	el.classList.remove("is-playing");
	$(el).find(".mp-vn__btn").html(MP_VN_PLAY);
	mp._vn_progress(el);
};

mp._vn_seek = function (el, ratio) {
	const st = el._vn;
	if (!st?.audio || !st.duration) return;
	st.audio.currentTime = Math.min(Math.max(ratio, 0), 1) * st.duration;
	if (st.audio.paused) mp._vn_toggle(el);
	mp._vn_progress(el);
};

mp._vn_progress = function (el) {
	const st = el._vn;
	if (!st?.audio) return;
	const total = st.duration || st.audio.duration || 0;
	const cur = st.audio.currentTime || 0;
	const played = total ? Math.round((cur / total) * MP_VN_BARS) : 0;
	$(el).find(".mp-vn__wave i").each((i, bar) => bar.classList.toggle("is-played", i < played));
	// O'ynayotganda — o'tgan vaqt, to'xtaganda — umumiy uzunlik (Telegram kabi)
	$(el).find("[data-vn-time]").text(mp._vn_fmt(el.classList.contains("is-playing") || cur ? cur : total));
};

mp.inject_voice_style = function () {
	if (document.getElementById("mp-vn-style")) return;
	$(`<style id="mp-vn-style">
		.mp-vn { display: flex; align-items: center; gap: 10px; max-width: 380px; padding: 8px 12px 8px 8px; border-radius: 16px;
			background: var(--subtle-fg); }
		.mp-vn__btn { flex: none; width: 40px; height: 40px; border-radius: 50%; border: 0; display: grid; place-items: center;
			background: var(--primary, #2490ef); color: #fff; cursor: pointer; }
		.mp-vn__btn svg { margin-left: 1px; }
		.mp-vn.is-playing .mp-vn__btn svg { margin-left: 0; }
		.mp-vn__body { flex: 1; min-width: 0; }
		.mp-vn__wave { display: flex; align-items: center; gap: 2px; height: 26px; cursor: pointer; }
		.mp-vn__wave i { flex: 1; min-width: 2px; border-radius: 2px; background: var(--gray-400, #a3a3a3); transition: background .1s; }
		.mp-vn__wave i.is-played { background: var(--primary, #2490ef); }
		.mp-vn__meta { display: flex; gap: 6px; margin-top: 3px; font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }
		.mp-vn__meta [data-vn-size]:not(:empty)::before { content: "·"; margin-right: 6px; }
		.mp-vn__date { margin-left: auto; overflow: hidden; text-overflow: ellipsis; }
		.mp-vn.is-broken .mp-vn__btn, .mp-vn.is-silent .mp-vn__btn { background: var(--gray-400, #a3a3a3); }
		.mp-vn__warn { color: var(--red-600, #dc2626); font-weight: 600; }
	</style>`).appendTo(document.head);
};
