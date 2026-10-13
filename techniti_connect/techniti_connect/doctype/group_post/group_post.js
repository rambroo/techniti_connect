// Copyright (c) 2026, Rohan Rambhiya and contributors
// For license information, please see license.txt

frappe.ui.form.on("Group Post", {
	refresh(frm) {
		render_preview(frm);
		if (frm.is_new()) return;
		const call = (method, label) =>
			frappe.call({ method: `techniti_connect.groups.${method}`, args: { post_name: frm.doc.name } }).then((r) => {
				if (r.message) frappe.show_alert({ message: `${label}: ${r.message}`, indicator: "green" });
				frm.reload_doc();
			});
		if (["Proposed", "Skipped"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Approve"), () => call("approve", __("Approved"))).addClass("btn-primary");
		}
		if (["Proposed", "Approved"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Swap"), () => call("swap", __("Swap")));
			frm.add_custom_button(__("Skip"), () => call("skip", __("Skipped")));
		}
		if (frm.doc.status === "Sent to Admin") {
			frm.add_custom_button(__("Mark Posted"), () => call("posted", __("Posted")));
		}
	},
	content(frm) {
		render_preview(frm);
	},
});

function render_preview(frm) {
	const wrapper = frm.get_field("preview").$wrapper;
	wrapper.empty();
	if (!frm.doc.content) return;
	frappe.db.get_value("Group Content", frm.doc.content, ["file", "link", "content_type"]).then(({ message: c }) => {
		if (!c) return;
		let html = "";
		if (c.file && c.content_type === "Photo") {
			html = `<img src="${encodeURI(c.file)}" style="max-width:320px;border-radius:8px">`;
		} else if (c.file) {
			html = `<video src="${encodeURI(c.file)}" controls style="max-width:320px;border-radius:8px"></video>`;
		}
		if (c.link) {
			const a = $("<a target='_blank' rel='noopener'>").attr("href", c.link).text(c.link);
			html += `<div style="margin-top:8px">${a.prop("outerHTML")}</div>`;
		}
		wrapper.html(html);
	});
}
