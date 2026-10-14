from techniti_connect.whatsapp.party import link_existing


def execute():
	"""Link WhatsApp messages received before auto-linking existed to their Donor."""
	link_existing()
