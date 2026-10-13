# Copyright (c) 2026, Rohan Rambhiya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from techniti_connect.share_check import DAY_FIELDS
from techniti_connect.whatsapp.phone import split_phones


class ShareCheckRule(Document):
	def validate(self):
		if not any(self.get(d) for d in DAY_FIELDS):
			frappe.throw(_("Tick at least one message day"))
		if not split_phones(self.source_phones):
			frappe.throw(_("Enter at least one valid number to accept the message from"))
