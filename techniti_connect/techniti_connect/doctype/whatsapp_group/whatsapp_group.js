// Copyright (c) 2026, Rohan Rambhiya and contributors
// For license information, please see license.txt

frappe.ui.form.on("WhatsApp Group", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Plan Next Post Now"), () => {
			frappe
				.call({ method: "techniti_connect.groups.plan_now", args: { group_name: frm.doc.name } })
				.then((r) => {
					const n = (r.message || []).length;
					frappe.msgprint(
						n
							? __("{0} post(s) proposed and sent to the approver.", [n])
							: __("Nothing new to plan: posts for the next date already exist, or its time has passed.")
					);
				});
		});
		frm.add_custom_button(__("Posts"), () =>
			frappe.set_route("List", "Group Post", { whatsapp_group: frm.doc.name })
		);
	},
});
