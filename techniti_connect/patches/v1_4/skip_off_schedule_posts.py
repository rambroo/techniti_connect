import frappe


def execute():
	"""Pending posts planned for a day the group no longer posts on are skipped."""
	from techniti_connect.groups import cancel_off_schedule

	for name in frappe.get_all("WhatsApp Group", pluck="name"):
		cancel_off_schedule(frappe.get_doc("WhatsApp Group", name))
