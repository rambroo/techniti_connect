frappe.listview_settings["Share Check"] = {
	get_indicator(doc) {
		const colors = {
			"Waiting for Message": "orange",
			Received: "blue",
			"Sent to Admin": "purple",
			Shared: "green",
			Missed: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
