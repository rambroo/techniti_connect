// WhatsApp section on the Donor / Website Donor form.
// Loaded for every desk page via app_include_js: Frappe skips app form scripts on custom
// DocTypes (Donor is one), so the handler is registered here instead.

const TC_WA_DOCTYPES = ["Donor", "Website Donor"];
const TC_WA_ROLES = ["WhatsApp Manager", "WhatsApp Agent", "System Manager"];

TC_WA_DOCTYPES.forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			tc_render_whatsapp(frm);
		},
	});
});

function tc_inject_style() {
	if (document.getElementById("tc-wa-style")) return;
	const css = `
	.tc-wa{border:1px solid var(--border-color);border-radius:12px;margin:12px 0 4px;overflow:hidden;background:var(--card-bg)}
	.tc-wa-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:10px 14px;background:var(--subtle-fg);cursor:pointer}
	.tc-wa-head h4{margin:0;font-size:14px;font-weight:600}
	.tc-wa-chip{font-size:12px;font-weight:600;padding:2px 8px;border-radius:999px;white-space:nowrap}
	.tc-wa-open{background:#e3f2e9;color:#0a5a31}.tc-wa-closed{background:#fef3c7;color:#8a4b08}.tc-wa-none{background:#f0f0ee;color:#3d3d3d}
	.tc-wa-body{padding:12px 14px;display:flex;flex-direction:column;gap:10px}
	.tc-wa-thread{max-height:360px;overflow-y:auto;display:flex;flex-direction:column;gap:8px;padding:10px;background:#f7f7f5;border-radius:10px}
	.tc-wa-row{display:flex}.tc-wa-row.out{justify-content:flex-end}
	.tc-wa-b{max-width:75%;padding:8px 10px;border-radius:10px;font-size:13px;line-height:1.45;white-space:pre-line;word-break:break-word}
	.tc-wa-row.in .tc-wa-b{background:#fff;border:1px solid #e6e6e3}.tc-wa-row.out .tc-wa-b{background:#dcf3e5}
	.tc-wa-meta{display:block;font-size:11px;color:#5f6368;margin-top:4px;text-align:right}
	.tc-wa-reply{display:flex;gap:8px;align-items:flex-end}
	.tc-wa-reply textarea{flex:1 1 auto;min-height:40px;resize:vertical;border:1px solid var(--border-color);border-radius:8px;padding:8px}
	.tc-wa-note{font-size:12px;color:#5f6368;margin:0}
	.tc-wa-btn{background:#0f7a43;border-color:#0f7a43;color:#fff}.tc-wa-btn:hover{background:#0a5a31;color:#fff}`;
	const el = document.createElement("style");
	el.id = "tc-wa-style";
	el.textContent = css;
	document.head.appendChild(el);
}

function tc_render_whatsapp(frm) {
	const $old = frm.$wrapper.find(".tc-wa");
	if (frm.is_new() || !frappe.user.has_role(TC_WA_ROLES)) {
		$old.remove();
		return;
	}
	tc_inject_style();
	const $panel = $old.length ? $old : $(`<div class="tc-wa"></div>`).prependTo(frm.layout.wrapper);
	$panel.html(`<div class="tc-wa-head"><h4>${__("WhatsApp")}</h4><span class="text-muted small">${__("Loading…")}</span></div>`);

	frappe
		.call({
			method: "techniti_connect.api.ui.record_whatsapp",
			args: { doctype: frm.doctype, name: frm.doc.name },
		})
		.then(({ message: d }) => tc_fill_panel(frm, $panel, d))
		.catch(() => $panel.remove());
}

function tc_fill_panel(frm, $panel, d) {
	const esc = frappe.utils.escape_html;
	const collapsed = frm.__tc_wa_collapsed;
	let chip;
	if (!d.has_phone) chip = `<span class="tc-wa-chip tc-wa-none">${__("No phone number")}</span>`;
	else if (d.window_open)
		chip = `<span class="tc-wa-chip tc-wa-open">${__("Reply window open until {0}", [
			moment(d.window_closes).format("ddd HH:mm"),
		])}</span>`;
	else chip = `<span class="tc-wa-chip tc-wa-closed">${__("Template only")}</span>`;

	const rows = (d.messages || [])
		.map((m) => {
			const when = frappe.datetime.str_to_user(m.at);
			let text = m.text ? esc(m.text) : "";
			if (m.message_type === "template") text = `<b>${esc(m.template_name || "Template")}</b>${text ? "<br>" + text : ""}`;
			if (!text && m.media_url) text = `[${esc(m.message_type)}]`;
			const status = m.direction === "Out" ? ` · ${esc(m.status || "")}` : "";
			return `<div class="tc-wa-row ${m.direction === "In" ? "in" : "out"}"><div class="tc-wa-b">${text}<span class="tc-wa-meta">${when}${status}</span></div></div>`;
		})
		.join("");

	const reply = d.can_reply
		? `<div class="tc-wa-reply"><textarea aria-label="${__("Reply")}" placeholder="${__("Type a reply…")}"></textarea><button class="btn btn-sm tc-wa-btn tc-wa-send">${__("Send")}</button></div>`
		: d.has_phone
			? `<p class="tc-wa-note">${__("More than 24 hours since their last message: WhatsApp only allows an approved template now.")}</p>`
			: "";

	$panel.html(`
		<div class="tc-wa-head" role="button" tabindex="0" aria-expanded="${!collapsed}">
			<h4>${__("WhatsApp")}</h4>
			<span class="text-muted small">${esc(d.phone ? "+" + d.phone : "")}</span>
			${chip}
			<span style="flex-grow:1"></span>
			<a class="small tc-wa-all" href="/app/whatsapp-message?party_name=${encodeURIComponent(frm.doc.name)}">${__("All messages")}</a>
		</div>
		<div class="tc-wa-body" style="${collapsed ? "display:none" : ""}">
			${d.shared_note ? `<p class="tc-wa-note">${esc(d.shared_note)}</p>` : ""}
			${rows ? `<div class="tc-wa-thread">${rows}</div>` : `<p class="tc-wa-note">${__("No WhatsApp messages with this number yet.")}</p>`}
			${reply}
		</div>`);

	const $thread = $panel.find(".tc-wa-thread");
	if ($thread.length) $thread.scrollTop($thread[0].scrollHeight);

	$panel.find(".tc-wa-head").on("click keydown", (e) => {
		if (e.type === "keydown" && e.key !== "Enter" && e.key !== " ") return;
		if ($(e.target).closest("a").length) return;
		frm.__tc_wa_collapsed = !frm.__tc_wa_collapsed;
		$panel.find(".tc-wa-body").toggle(!frm.__tc_wa_collapsed);
	});

	$panel.find(".tc-wa-send").on("click", () => {
		const $ta = $panel.find("textarea");
		const text = ($ta.val() || "").trim();
		if (!text) return;
		frappe
			.call({
				method: "techniti_connect.api.ui.send_reply",
				args: { doctype: frm.doctype, name: frm.doc.name, text },
				freeze: true,
			})
			.then(({ message: r }) => {
				if (r && r.status === "Failed") frappe.msgprint(r.error || __("Not sent"));
				tc_render_whatsapp(frm);
			});
	});
}
