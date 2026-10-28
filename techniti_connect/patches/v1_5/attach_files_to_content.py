import frappe


def execute():
	"""Generated cards and clips were attached to the WhatsApp Group; deleting a group deleted them.
	Attach them to their Group Content item instead."""
	from techniti_connect.content.autofill import attach_to_content

	for doc in frappe.get_all("Group Content", filters={"file": ["is", "set"]}, fields=["name", "file"]):
		attach_to_content(doc)
