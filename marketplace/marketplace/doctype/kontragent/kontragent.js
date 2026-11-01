// Kontragent formasi: pastida "Xaridlar" — undan nima, qachon, nechta va necha puldan olganmiz (kontragent.get_purchases).
// Har bir kirim — sana va jami summa, ostida tovarlar: rang · o'lcham, nechta olingani, 1 donasi narxi, summasi.
frappe.ui.form.on("Kontragent", {
	async refresh(frm) {
		const $box = frm.fields_dict.xaridlar_html?.$wrapper;
		if (!$box) return;
		if (frm.is_new()) {
			$box.html(`<div class="text-muted small">Saqlangandan keyin bu yerda undan olingan tovarlar chiqadi.</div>`);
			return;
		}
		$box.html(`<div class="text-muted small">Yuklanmoqda…</div>`);
		const name = frm.doc.name;
		const d = await frappe.xcall("marketplace.marketplace.doctype.kontragent.kontragent.get_purchases", { kontragent: name });
		if (frm.doc.name !== name) return;
		$box.html(purchases_html(d));
	},
});

function purchases_html(d) {
	const esc = frappe.utils.escape_html;
	const n = (x) => format_number(x || 0, null, 0);
	const money = (x) => `${n(x)} so‘m`;
	const date = (x) => (x ? frappe.datetime.str_to_user(x) : "—");
	const tile = (label, value, hint = "") =>
		`<div class="mp-kt__tile"><div class="mp-kt__label">${label}</div><div class="mp-kt__value">${value}</div>${hint ? `<div class="mp-kt__hint">${hint}</div>` : ""}</div>`;
	const receipt = (g) => `
		<div class="mp-kt__rc">
			<div class="mp-kt__rchead">
				<span><b>${esc(date(g.date))}</b>${g.time ? ` <span class="text-muted">${esc(g.time)}</span>` : ""}</span>
				<span><span class="text-muted">${n(g.qty)} dona ·</span> <b>${money(g.amount)}</b></span>
			</div>
			<div class="mp-kt__line mp-kt__line--head">
				<span>Tovar</span><span>Rang · o‘lcham</span><span class="mp-kt__r">Soni</span><span class="mp-kt__r">Narxi</span><span class="mp-kt__r">Summa</span>
			</div>
			${g.rows.map((r) => `
				<div class="mp-kt__line">
					<span class="mp-kt__name">${esc(r.name)}</span>
					<span class="mp-kt__var">${esc(r.variant || "—")}</span>
					<span class="mp-kt__r mp-kt__qty">${n(r.qty)} ta</span>
					<span class="mp-kt__r" data-label="Narxi">${money(r.rate)}</span>
					<span class="mp-kt__r mp-kt__sum">${money(r.rate * r.qty)}</span>
				</div>`).join("")}
			${g.note ? `<div class="mp-kt__note">Izoh: ${esc(g.note)}</div>` : ""}
		</div>`;
	return `
		<style>
			.mp-kt__tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-bottom: 16px; }
			.mp-kt__tile { padding: 10px 14px; border-radius: var(--border-radius-md); background: var(--subtle-fg); }
			.mp-kt__label { font-size: var(--text-xs); font-weight: 600; color: var(--text-muted); text-transform: uppercase; }
			.mp-kt__value { margin-top: 2px; font-size: var(--text-xl); font-weight: 700; color: var(--heading-color); }
			.mp-kt__hint { font-size: var(--text-xs); color: var(--text-muted); }
			.mp-kt__list { display: grid; gap: 12px; }
			.mp-kt__rc { border: 1px solid var(--border-color); border-radius: var(--border-radius-lg); overflow: hidden; }
			.mp-kt__rchead { display: flex; justify-content: space-between; gap: 10px; padding: 10px 14px; background: var(--subtle-fg); }
			.mp-kt__line { display: grid; grid-template-columns: minmax(140px, 1.6fr) minmax(110px, 1.2fr) 70px 140px 150px; gap: 12px;
				align-items: baseline; padding: 9px 14px; border-top: 1px solid var(--border-color); font-variant-numeric: tabular-nums; }
			.mp-kt__line--head { padding-block: 6px; font-size: var(--text-xs); font-weight: 600; text-transform: uppercase;
				letter-spacing: .03em; color: var(--text-muted); }
			.mp-kt__r { text-align: right; white-space: nowrap; }
			.mp-kt__name { font-weight: 600; color: var(--heading-color); }
			.mp-kt__var { color: var(--text-muted); }
			.mp-kt__qty { font-weight: 600; }
			.mp-kt__sum { font-weight: 600; }
			.mp-kt__note { padding: 8px 14px; border-top: 1px solid var(--border-color); font-size: var(--text-sm); color: var(--text-muted); }
			.mp-kt__empty { padding: 16px 0; color: var(--text-muted); }
			@media (max-width: 640px) {
				.mp-kt__line--head { display: none; }
				.mp-kt__line { grid-template-columns: 1fr auto; gap: 2px 12px; }
				.mp-kt__var { grid-column: 1; grid-row: 2; }
				.mp-kt__qty { grid-column: 2; grid-row: 1; }
				.mp-kt__line > [data-label] { display: none; }
				.mp-kt__sum { grid-column: 2; grid-row: 2; }
			}
		</style>
		<div class="mp-kt__tiles">
			${tile("Jami xarid", money(d.amount))}
			${tile("Kirimlar", `${n(d.receipts)} ta`, `${n(d.qty)} dona tovar`)}
			${tile("Oxirgi xarid", date(d.last), d.first && d.first !== d.last ? `birinchisi: ${date(d.first)}` : "")}
		</div>
		${d.journal.length
			? `<div class="mp-kt__list">${d.journal.map(receipt).join("")}</div>`
			: `<div class="mp-kt__empty">Hali bu kontragentdan kirim qilinmagan. Kirim — tovar formasining Ombor tabida.</div>`}`;
}
