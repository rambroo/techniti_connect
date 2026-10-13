frappe.listview_settings["WhatsApp Message"] = {
	add_fields: ["direction", "status"],
	get_indicator(doc) {
		if (doc.direction === "In") return [__("Received"), "blue", "direction,=,In"];
		const colors = { Sent: "green", Delivered: "green", Read: "green", Held: "orange", Queued: "gray", Failed: "red" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
