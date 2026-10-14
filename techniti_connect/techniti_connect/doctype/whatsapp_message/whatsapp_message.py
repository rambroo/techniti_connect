# Copyright (c) 2026, Rohan Rambhiya and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from techniti_connect.whatsapp import party


class WhatsAppMessage(Document):
	def before_insert(self):
		if not self.party_name and self.phone:
			self.update(party.resolve(self.phone))
		if self.direction == "In" and not self.contact_name and self.party_label:
			self.contact_name = self.party_label
