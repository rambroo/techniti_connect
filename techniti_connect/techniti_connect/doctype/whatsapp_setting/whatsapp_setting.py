import secrets

import frappe
from frappe.model.document import Document


class WhatsAppSetting(Document):
	def validate(self):
		if not self.get_password("webhook_secret", raise_exception=False):
			self.webhook_secret = secrets.token_urlsafe(32)
		self.webhook_url = get_webhook_url(self.webhook_secret if self.webhook_secret and "*" not in self.webhook_secret
										   else self.get_password("webhook_secret", raise_exception=False))

	def on_update(self):
		frappe.clear_document_cache("WhatsApp Setting", "WhatsApp Setting")


def get_webhook_url(secret):
	if not secret:
		return None
	return frappe.utils.get_url(f"/api/method/techniti_connect.api.webhook.receive?token={secret}")
