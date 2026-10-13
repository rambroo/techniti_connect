frappe.listview_settings["Group Post"] = {
	get_indicator(doc) {
		const colors = {
			Proposed: "orange",
			Approved: "blue",
			Skipped: "gray",
			"Sent to Admin": "purple",
			Posted: "green",
			Missed: "red",
			Failed: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
