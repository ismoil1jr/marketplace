// Omborni ko'rsatish (faqat o'qish): tovar formasidagi "Ombor" tabi (item_seller.js) va Ombor sahifasi (ombor.js).
//   mp.stock_grid(data)  — rang × o'lcham jadvali, har katakda omborda nechta bor (seller_desk.get_variant_matrix)
//   mp.journal(rows)     — harakatlar tarixi: kirim / sotuv / kamomad, kim, qachon, nechta (reports.journal);
//                          kirimda yana kimdan olingani, 1 donasi narxi va jami summasi
window.mp = window.mp || {};

mp.KINDS = {
	kirim: { label: "Kirim", sign: "+", cls: "is-in" },
	sotuv: { label: "Sotildi", sign: "−", cls: "is-out" },
	kamomad: { label: "Kamomad", sign: "−", cls: "is-bad" },
};

mp.stock_grid = function (data) {
	mp.inject_stock_style();
	const esc = frappe.utils.escape_html;
	const n = (x) => format_number(x || 0, null, 0);
	const { colors = [], sizes = [], cells = {} } = data || {};
	if (!Object.keys(cells).length) {
		return `<div class="mp-sg__empty text-muted">Hali kirim bo'lmagan — pastdagi jadvalga nechta kelganini yozib, Saqlash bosing</div>`;
	}
	const qty = (c, s) => cells[`${c}|${s}`]?.qty;
	const cell = (c, s) => {
		const q = qty(c, s);
		if (q === undefined) return `<td class="is-none">—</td>`;
		return `<td class="${q > 0 ? "" : "is-zero"}">${n(q)}</td>`;
	};
	const row_sum = (c) => sizes.reduce((a, s) => a + Math.max(qty(c, s) || 0, 0), 0);
	const col_sum = (s) => colors.reduce((a, c) => a + Math.max(qty(c.value, s) || 0, 0), 0);
	const total = colors.reduce((a, c) => a + row_sum(c.value), 0);
	const name = (c) => (c.value ? `<i style="background:${esc(c.hex || "#ccc")}"></i>${esc(c.value)}` : "Soni");
	const multi_size = sizes.length > 1 || sizes[0];
	return `
		<div class="mp-sg">
			<div class="mp-sg__total">Omborda hozir: <b>${n(total)}</b> dona</div>
			<div class="mp-sg__scroll"><table>
				<thead><tr><th></th>${sizes.map((s) => `<th>${esc(s || "Soni")}</th>`).join("")}${multi_size ? "<th>Jami</th>" : ""}</tr></thead>
				<tbody>${colors
					.map((c) => `<tr><th class="mp-sg__color">${name(c)}</th>${sizes.map((s) => cell(c.value, s)).join("")}${multi_size ? `<td class="mp-sg__sum">${n(row_sum(c.value))}</td>` : ""}</tr>`)
					.join("")}</tbody>
				${colors.length > 1 ? `<tfoot><tr><th>Jami</th>${sizes.map((s) => `<td>${n(col_sum(s))}</td>`).join("")}${multi_size ? `<td>${n(total)}</td>` : ""}</tr></tfoot>` : ""}
			</table></div>
			<div class="mp-sg__legend text-muted">0 — tugagan · «—» — bu rang/o'lcham hali kelmagan</div>
		</div>`;
};

// show_item: Ombor sahifasida (bir nechta tovar) tovar nomini ham ko'rsatish.
// show_supplier: false — Kontragent formasida ("kimdan" o'sha kontragentning o'zi)
mp.journal = function (rows, { show_item = false, show_supplier = true, empty = "Hali harakat yo'q" } = {}) {
	mp.inject_stock_style();
	const esc = frappe.utils.escape_html;
	const n = (x) => format_number(x || 0, null, 0);
	const money = (x) => `${n(x)} so‘m`;
	if (!rows || !rows.length) return `<div class="mp-sg__empty text-muted">${esc(empty)}</div>`;
	const doc_url = (r) => `/desk/${frappe.router.slug(r.voucher_type)}/${encodeURIComponent(r.voucher_no)}`;
	const date = (r) => `${frappe.datetime.str_to_user(r.date)}<br><span class="text-muted">${esc(r.time)}</span>`;
	return `
		<div class="mp-jr">${rows
			.map((r) => {
				const k = mp.KINDS[r.kind] || mp.KINDS.kirim;
				const note = r.note ? ` · <span class="text-muted">${esc(r.note)}</span>` : "";
				const supplier = r.supplier_id
					? `<a href="/desk/kontragent/${encodeURIComponent(r.supplier_id)}"><b>${esc(r.supplier)}</b></a>`
					: `<b>${esc(r.supplier)}</b>`;
				const who =
					r.kind === "sotuv"
						? `Mijoz: ${esc(r.note || "—")}`
						: `${r.supplier && show_supplier ? `Kimdan: ${supplier} · kiritdi: ` : r.supplier ? "Kiritdi: " : ""}${esc(r.user || "")}${note}`;
				const priced = r.rows.some((x) => x.rate);
				const lines = r.rows
					.map((x) => {
						const label = [show_item ? x.name : "", x.variant].filter(Boolean).join(" · ") || x.name;
						const rate = priced ? `<i class="mp-jr__rate">${x.rate ? `× ${money(x.rate)}` : ""}</i>` : "";
						return `<li><span>${esc(label)}</span><b class="${k.cls}">${k.sign}${n(x.qty)}</b>${rate}<em>qoldi ${n(x.after)}</em></li>`;
					})
					.join("");
				return `
				<div class="mp-jr__row">
					<div class="mp-jr__date">${date(r)}</div>
					<div class="mp-jr__main">
						<div class="mp-jr__head">
							<span class="mp-jr__kind ${k.cls}">${k.label}</span>
							<b class="${k.cls}">${k.sign}${n(r.qty)} dona</b>
							${r.amount ? `<b class="mp-jr__sum">${money(r.amount)}</b>` : ""}
							<a class="text-muted small" href="${doc_url(r)}">${esc(r.voucher_no)}</a>
						</div>
						<div class="mp-jr__who small">${who}</div>
						<ul class="mp-jr__lines">${lines}</ul>
					</div>
				</div>`;
			})
			.join("")}</div>`;
};

mp.inject_stock_style = function () {
	if (document.getElementById("mp-sg-style")) return;
	$(`<style id="mp-sg-style">
		.mp-sg__empty { padding: 14px 0; font-size: var(--text-sm); }
		.mp-sg__total { margin-bottom: 8px; font-size: var(--text-md); }
		.mp-sg__total b { font-size: var(--text-xl); color: var(--heading-color); }
		.mp-sg__scroll { overflow-x: auto; }
		.mp-sg table { border-collapse: collapse; }
		.mp-sg th, .mp-sg td { padding: 6px 12px; text-align: center; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
		.mp-sg thead th { font-size: var(--text-sm); color: var(--text-muted); font-weight: 600; }
		.mp-sg td { font-weight: 600; font-size: var(--text-md); color: var(--heading-color); }
		.mp-sg td.is-zero { color: var(--red-500, #ef4444); }
		.mp-sg td.is-none { color: var(--text-light, #aaa); font-weight: 400; }
		.mp-sg__sum, .mp-sg tfoot td { color: var(--text-muted) !important; }
		.mp-sg tfoot th { text-align: left; color: var(--text-muted); font-weight: 600; }
		.mp-sg__color { text-align: left !important; font-weight: 600; }
		.mp-sg__color i { display: inline-block; width: 12px; height: 12px; margin-right: 6px; border-radius: 50%; border: 1px solid var(--border-color); vertical-align: -1px; }
		.mp-sg__legend { margin-top: 6px; font-size: var(--text-xs); }
		.mp-jr { max-height: 560px; overflow: auto; }
		.mp-jr__row { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; padding: 10px 2px; border-top: 1px solid var(--border-color); font-size: var(--text-sm); }
		.mp-jr__row:first-child { border-top: 0; }
		.mp-jr__head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
		.mp-jr__kind { padding: 1px 8px; border-radius: 10px; font-size: var(--text-xs); font-weight: 600; }
		.mp-jr__kind.is-in { background: var(--bg-green); }
		.mp-jr__kind.is-out { background: var(--bg-blue); }
		.mp-jr__kind.is-bad { background: var(--bg-red); }
		b.is-in { color: var(--green-600, #16a34a); }
		b.is-out { color: var(--blue-600, #2563eb); }
		b.is-bad { color: var(--red-600, #dc2626); }
		.mp-jr__who { margin-top: 2px; }
		.mp-jr__lines { margin: 4px 0 0; padding: 0; list-style: none; }
		.mp-jr__lines li { display: flex; gap: 10px; align-items: baseline; padding: 1px 0; }
		.mp-jr__lines li span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
		.mp-jr__lines li em { flex: none; width: 80px; text-align: right; font-style: normal; color: var(--text-muted); font-size: var(--text-xs); }
		.mp-jr__lines li .mp-jr__rate { flex: none; width: 120px; text-align: right; font-style: normal; color: var(--text-muted); }
		.mp-jr__sum { color: var(--heading-color); }
		@media (max-width: 560px) { .mp-jr__row { grid-template-columns: 1fr; gap: 2px; } }
	</style>`).appendTo(document.head);
};
