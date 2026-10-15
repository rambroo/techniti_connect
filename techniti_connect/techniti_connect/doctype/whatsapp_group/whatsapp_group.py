# Copyright (c) 2026, Rohan Rambhiya and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WhatsAppGroup(Document):
	def validate(self):
		if self.posting_method == "Post Directly" and self.group_chat_id and not self.group_chat_id.endswith("@g.us"):
			frappe.throw(_("WhatsApp Group ID must end in @g.us. Choose the group in /connect > Groups."))

	def on_update(self):
		before = self.get_doc_before_save()
		if before and before.post_weekday != self.post_weekday:
			from techniti_connect.groups import cancel_off_schedule

			skipped = cancel_off_schedule(self)
			if skipped:
				frappe.msgprint(_("{0} pending post(s) planned for {1} were skipped.").format(skipped, before.post_weekday),
								alert=True)
