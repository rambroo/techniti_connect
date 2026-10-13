"""Thin client for the Sparklebot (WhatsMark) API.

v1  {api_base_url}/{tenant}/messages/send|template|media  — works with the tenant API token
v2  {api_v2_base_url}/messages/interactive|cta|...      — needs a separate v2 token (optional)
"""

import frappe
import requests

from techniti_connect.whatsapp.phone import normalize_phone

TIMEOUT = 30
MEDIA_TIMEOUT = 120  # Sparklebot downloads the file from us before replying


def get_settings():
	if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
		return None
	try:
		return frappe.get_cached_doc("WhatsApp Setting")
	except Exception:
		return None


def get_token(settings):
	try:
		return settings.get_password("api_token", raise_exception=False)
	except Exception:
		return settings.get("api_token")


class SendResult(dict):
	@property
	def ok(self):
		return bool(self.get("ok"))


class SparklebotClient:
	def __init__(self, settings=None):
		self.settings = settings or get_settings()
		s = self.settings
		self.token = get_token(s) if s else None
		base = ((s and s.api_base_url) or "").rstrip("/")
		slug = ((s and s.tenant_slug) or "").strip("/")
		self.v1_base = f"{base}/{slug}" if base and slug else ""
		self.v2_base = ((s and s.get("api_v2_base_url")) or "https://sparklebot.in/api/v2").rstrip("/")
		self.v2_token = None
		if s:
			try:
				self.v2_token = s.get_password("api_v2_token", raise_exception=False)
			except Exception:
				self.v2_token = None

	def is_enabled(self):
		return bool(self.settings and self.settings.enabled and self.token and self.v1_base)

	@property
	def headers(self):
		return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

	@property
	def supports_buttons(self):
		return bool(self.v2_token)

	# ------------------------------------------------------------------ v1

	def send_text(self, phone, message):
		# v1 text route is /messages/send (there is no /messages/text on this platform)
		return self._post(f"{self.v1_base}/messages/send", phone, json={"phone_number": phone, "message_body": message})

	def send_template(self, phone, template_name, language="en", fields=None, header_document_url=None,
					  header_document_name=None, header_image_url=None, header_video_url=None, buttons=None):
		fields = fields or {}
		if (header_image_url or header_video_url or buttons) and self.v2_token:
			# image/video headers and dynamic buttons are documented on v2 only
			payload = {"phone": "+" + phone, "template_name": template_name, "language": language or "en"}
			payload.update(fields)
			for key, val in (("header_image_url", header_image_url), ("header_video_url", header_video_url),
							 ("header_document_url", header_document_url), ("header_document_name", header_document_name)):
				if val:
					payload[key] = val
			for i, val in enumerate(buttons or []):
				payload[f"button_{i}"] = val
			return self._post(f"{self.v2_base}/messages/template", phone, json=payload, v2=True)

		payload = {"phone_number": phone, "template_name": template_name, "template_language": language or "en"}
		for key, val in (("header_document_url", header_document_url), ("header_image_url", header_image_url),
						 ("header_video_url", header_video_url)):
			if val:
				payload[key] = val
		payload.update(fields)
		return self._post(f"{self.v1_base}/messages/template", phone, json=payload)

	def send_media(self, phone, media_type, media_url, caption=None, filename=None):
		payload = {"phone_number": phone, "media_type": media_type, "media_url": media_url}
		if caption:
			payload["caption"] = caption[:1024]
		if filename:
			payload["filename"] = filename
		return self._post(f"{self.v1_base}/messages/media", phone, json=payload, timeout=MEDIA_TIMEOUT)

	# ------------------------------------------------------------------ v2 (separate token)

	def send_buttons(self, phone, body_text, buttons, header_text=None, footer_text=None):
		"""buttons: list of (id, title) — max 3, title max 20 chars."""
		payload = {
			"phone": "+" + phone,
			"type": "button",
			"body_text": body_text[:1024],
			"buttons": [{"id": bid, "title": title[:20]} for bid, title in buttons[:3]],
		}
		if header_text:
			payload["header_text"] = header_text[:60]
		if footer_text:
			payload["footer_text"] = footer_text[:60]
		return self._post(f"{self.v2_base}/messages/interactive", phone, json=payload, v2=True)

	def send_cta(self, phone, message, button_text, button_url, header_text=None, footer_text=None):
		payload = {"phone": "+" + phone, "message": message[:1024], "button_text": button_text[:25], "button_url": button_url}
		if header_text:
			payload["header_text"] = header_text[:60]
		if footer_text:
			payload["footer_text"] = footer_text[:60]
		return self._post(f"{self.v2_base}/messages/cta", phone, json=payload, v2=True)

	def list_messages(self, per_page=50, direction=None, page=1):
		"""Recent message history (sent and received) with delivery status."""
		params = {"per_page": per_page, "page": page, "sort": "-created_at"}
		if direction:
			params["filter[direction]"] = direction
		try:
			if not self.v2_token:
				return []
			resp = requests.get(f"{self.v2_base}/messages", params=params, headers=self._headers(True), timeout=TIMEOUT)
			return resp.json().get("data") or []
		except Exception as e:
			frappe.log_error(title="Sparklebot list_messages failed", message=str(e))
			return []

	# ------------------------------------------------------------------ internals

	def _headers(self, v2=False):
		token = self.v2_token if v2 else self.token
		return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

	def _post(self, url, phone, json=None, data=None, v2=False, timeout=TIMEOUT):
		if not self.is_enabled():
			return SendResult(ok=False, error="WhatsApp is not enabled or not configured")
		if not phone or not normalize_phone(phone):
			return SendResult(ok=False, error=f"Invalid phone number: {phone}")
		try:
			if v2 and not self.v2_token:
				return SendResult(ok=False, error="API v2 token not set")
			resp = requests.post(url, json=json, data=data, headers=self._headers(v2), timeout=timeout)
		except Exception as e:
			return SendResult(ok=False, error=f"Request failed: {e}")
		return self._parse(resp)

	@staticmethod
	def _parse(resp):
		text = (resp.text or "")[:2000]
		if resp.status_code in (200, 201) and not text.strip():
			# seen on v1 /messages/media: accepted with an empty body and no message id
			return SendResult(ok=True, status_code=resp.status_code, warning="Sparklebot accepted it but gave no confirmation")
		try:
			body = resp.json()
		except ValueError:
			return SendResult(ok=False, status_code=resp.status_code, error=f"Non-JSON response: {text[:300]}")

		if resp.status_code not in (200, 201):
			err = body.get("error") if isinstance(body, dict) else None
			if isinstance(err, dict):
				msg = f"{err.get('code')}: {err.get('message')}"
			else:
				msg = (body.get("message") if isinstance(body, dict) else None) or text[:300]
			return SendResult(ok=False, status_code=resp.status_code, error=msg, response=text)

		data = body.get("data") if isinstance(body, dict) else None
		data = data if isinstance(data, dict) else {}
		ok = (
			body.get("success") is True
			or body.get("status") in ("success", "sent")
			or bool(body.get("message_id") or data.get("message_id"))
		)
		wamid = body.get("message_id") or data.get("message_id")
		if not wamid:
			try:
				wamid = data.get("whatsapp_response", {}).get("messages", [{}])[0].get("id")
			except Exception:
				wamid = None
		return SendResult(ok=ok, wamid=wamid, status_code=resp.status_code, response=text,
						  error=None if ok else (body.get("message") or text[:300]))
