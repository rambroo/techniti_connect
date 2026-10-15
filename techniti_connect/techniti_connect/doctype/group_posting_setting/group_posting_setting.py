# Copyright (c) 2026, Rohan Rambhiya and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GroupPostingSetting(Document):
	def validate(self):
		self.waha_url = (self.waha_url or "").strip().rstrip("/") or None
