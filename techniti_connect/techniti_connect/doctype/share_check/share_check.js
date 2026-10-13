// Copyright (c) 2026, Rohan Rambhiya and contributors
// For license information, please see license.txt

frappe.ui.form.on("Share Check", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status === "Shared") return;
		frm.add_custom_button(__("Mark Shared"), () =>
			frappe
				.call({ method: "techniti_connect.share_check.shared", args: { check_name: frm.doc.name } })
				.then(() => frm.reload_doc())
		);
	},
});
