"""Outgoing messages: one entry point that logs, respects the 24-hour window, and holds when needed.

Free-form messages (text, media, buttons, CTA) only reach a person within 24 hours of their last
message to us. For staff (approvers, group admins) we hold such messages and send the configured
staff alert template instead; when they reply, the held messages go out (see flush_held).
"""

import json
import re

import frappe
from frappe.utils import add_to_date, now_datetime

from techniti_connect.whatsapp.client import SparklebotClient, get_settings
from techniti_connect.whatsapp.phone import normalize_phone, phone_key

WINDOW_HOURS = 24
WINDOW_SAFETY_MINUTES = 10
NUDGE_COOLDOWN_HOURS = 6
HOLD_MAX_DAYS = 3


def is_window_open(phone):
	key = phone_key(phone)
	if not key:
		return False
	since = add_to_date(now_datetime(), hours=-WINDOW_HOURS, minutes=WINDOW_SAFETY_MINUTES)
	return bool(
		frappe.db.exists(
			"WhatsApp Message",
			{"direction": "In", "phone": ["like", f"%{key}"], "sent_or_received_at": [">", since]},
		)
	)


def send(phone, kind, *, text=None, media_type=None, media_url=None, caption=None, filename=None,
		 buttons=None, header_text=None, footer_text=None, button_text=None, button_url=None,
		 template_name=None, language="en", fields=None, header_document_url=None,
		 reference=None, contact_name=None, hold_if_closed=True, nudge_text=None, redact=False):
	"""Send one message. kind: text | media | buttons | cta | template.

	Returns the WhatsApp Message document (status Sent / Held / Failed).
	reference: (doctype, name) to link the message to.
	redact: keep the content out of the log (e.g. OTP codes).
	"""
	number = normalize_phone(phone)
	payload = {k: v for k, v in dict(
		text=text, media_type=media_type, media_url=media_url, caption=caption, filename=filename,
		buttons=buttons, header_text=header_text, footer_text=footer_text, button_text=button_text,
		button_url=button_url, template_name=template_name, language=language, fields=fields,
		header_document_url=header_document_url,
	).items() if v}

	msg = frappe.get_doc({
		"doctype": "WhatsApp Message",
		"direction": "Out",
		"status": "Queued",
		"phone": number or str(phone or ""),
		"contact_name": contact_name,
		"message_type": {"media": media_type or "image", "buttons": "interactive"}.get(kind, kind),
		"template_name": template_name,
		"text": "(hidden)" if redact else (text or caption or (fields and json.dumps(fields, ensure_ascii=False))),
		"media_url": media_url,
		"payload": json.dumps({"kind": kind, **payload}, ensure_ascii=False, default=str),
		"raw": None,
		"reference_doctype": reference[0] if reference else None,
		"reference_name": reference[1] if reference else None,
	}).insert(ignore_permissions=True)

	if not number:
		_fail(msg, f"Invalid phone number: {phone}")
		return msg

	if kind != "template" and not is_window_open(number):
		if hold_if_closed:
			msg.db_set("status", "Held")
			nudge(number, contact_name, nudge_text or "you have a new message from the foundation")
			return msg
		_fail(msg, "24-hour window closed and no template given")
		return msg

	dispatch(msg)
	return msg


def dispatch(msg):
	"""Actually call Sparklebot for a logged message."""
	data = json.loads(msg.payload or "{}")
	kind = data.pop("kind", msg.message_type)
	client = SparklebotClient()
	phone = msg.phone

	if kind == "text":
		res = client.send_text(phone, data.get("text") or "")
	elif kind == "media":
		res = client.send_media(phone, data.get("media_type"), data.get("media_url"),
								caption=data.get("caption"), filename=data.get("filename"))
	elif kind == "buttons" and client.supports_buttons:
		res = client.send_buttons(phone, data.get("text") or "", [tuple(b) for b in data.get("buttons") or []],
								  header_text=data.get("header_text"), footer_text=data.get("footer_text"))
	elif kind == "buttons":
		res = client.send_text(phone, reply_menu(data.get("text") or "", data.get("buttons") or []))
	elif kind == "cta" and client.supports_buttons:
		res = client.send_cta(phone, data.get("text") or "", data.get("button_text"), data.get("button_url"),
							  header_text=data.get("header_text"), footer_text=data.get("footer_text"))
	elif kind == "cta":
		res = client.send_text(phone, f"{data.get('text') or ''}\n\n{data.get('button_text') or 'Open'}: {data.get('button_url')}")
	elif kind == "template":
		res = client.send_template(phone, data.get("template_name"), data.get("language") or "en",
								   fields=data.get("fields") or {},
								   header_document_url=data.get("header_document_url"))
	else:
		res = {"ok": False, "error": f"Unknown message kind: {kind}"}

	if res.get("ok"):
		msg.db_set({"status": "Sent", "wamid": res.get("wamid"), "sent_or_received_at": now_datetime(),
					"error": res.get("warning")})
	else:
		_fail(msg, res.get("error") or "Send failed")
	if msg.text == "(hidden)":
		msg.db_set("payload", None)
	return res


# --------------------------------------------------------------------------- reply codes
# Without tap buttons (API v2), a button becomes a short code the person types back, e.g.
# "gp:approve:GP-2026-00012" -> "A12". Letters are unique per action, numbers come from the document.

ACTION_LETTERS = {"approve": "A", "swap": "S", "skip": "K", "posted": "P", "shared": "D"}
CODE_RE = re.compile(r"^\s*\*?([A-Za-z])\s*-?\s*(\d{1,7})\*?\s*[.!]?\s*$")


def reply_code(button_id):
	parts = (button_id or "").split(":", 2)
	if len(parts) != 3:
		return None
	letter = ACTION_LETTERS.get(parts[1])
	digits = re.findall(r"\d+", parts[2])
	return f"{letter}{int(digits[-1])}" if letter and digits else None


def reply_menu(body, buttons):
	lines = [body.strip(), ""]
	for button_id, title in buttons:
		code = reply_code(button_id)
		if code:
			lines.append(f"Reply *{code}* = {title}")
	return "\n".join(lines).strip()


def resolve_reply_code(phone, text):
	"""Map a typed code (e.g. "a12") back to the button id it stands for, using recent menus sent to this number."""
	m = CODE_RE.match(text or "")
	key = phone_key(phone)
	if not m or not key:
		return None
	code = f"{m.group(1).upper()}{int(m.group(2))}"
	since = add_to_date(now_datetime(), days=-HOLD_MAX_DAYS - 4)
	for payload in frappe.get_all("WhatsApp Message", filters={"direction": "Out", "phone": ["like", f"%{key}"],
								  "payload": ["like", "%\"buttons\"%"], "creation": [">", since]},
								  pluck="payload", order_by="creation desc", limit=50):
		try:
			buttons = json.loads(payload or "{}").get("buttons") or []
		except ValueError:
			continue
		for button_id, _title in buttons:
			if reply_code(button_id) == code:
				return button_id
	return None


def nudge(phone, contact_name, summary):
	"""Send the staff alert template so the person replies and opens the 24-hour window."""
	settings = get_settings()
	template = settings and settings.get("staff_alert_template")
	if not template:
		return None
	since = add_to_date(now_datetime(), hours=-NUDGE_COOLDOWN_HOURS)
	if frappe.db.exists("WhatsApp Message", {"direction": "Out", "phone": phone, "template_name": template,
											 "status": ["in", ["Sent", "Delivered", "Read"]], "creation": [">", since]}):
		return None
	return send(phone, "template", template_name=template, language=settings.get("staff_alert_language") or "en",
				fields={"field_1": contact_name or "there", "field_2": summary[:900]}, contact_name=contact_name)


def flush_held(phone):
	"""Send everything held for this number (called when they message us)."""
	key = phone_key(phone)
	if not key:
		return 0
	since = add_to_date(now_datetime(), days=-HOLD_MAX_DAYS)
	held = frappe.get_all("WhatsApp Message", filters={"direction": "Out", "status": "Held",
						  "phone": ["like", f"%{key}"], "creation": [">", since]}, pluck="name", order_by="creation asc")
	for name in held:
		dispatch(frappe.get_doc("WhatsApp Message", name))
	return len(held)


def expire_held():
	"""Daily: give up on held messages older than HOLD_MAX_DAYS."""
	cutoff = add_to_date(now_datetime(), days=-HOLD_MAX_DAYS)
	for name in frappe.get_all("WhatsApp Message", filters={"status": "Held", "creation": ["<", cutoff]}, pluck="name"):
		frappe.db.set_value("WhatsApp Message", name, {"status": "Failed",
							"error": "Expired: the person did not reply within 3 days, so the 24-hour window never opened"})


def _fail(msg, error):
	msg.db_set({"status": "Failed", "error": str(error)[:2000]})
	frappe.log_error(title=f"WhatsApp send failed ({msg.phone})", message=f"{msg.name}\n{error}")


def public_url(file_url):
	"""Absolute URL for a /files/... path (WhatsApp must be able to download it)."""
	if not file_url:
		return None
	if file_url.startswith("http"):
		return file_url
	return frappe.utils.get_url(file_url)
