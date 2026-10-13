"""Incoming WhatsApp events: parse, store, route."""

import datetime
import json

import frappe
from frappe.utils import now_datetime

from techniti_connect.whatsapp import outbox
from techniti_connect.whatsapp.phone import normalize_phone

STATUS_MAP = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}
STATUS_RANK = {"Queued": 0, "Held": 0, "Sent": 1, "Delivered": 2, "Read": 3, "Failed": 4}

# button id prefix -> "module.function(message_doc, action, docname)"
BUTTON_ROUTES = {
	"gp": "techniti_connect.groups.handle_button",
	"sc": "techniti_connect.share_check.handle_button",
}


# --------------------------------------------------------------------------- parsing

def _meta_payloads(data):
	"""Yield Meta 'value' objects from either Meta's raw format or Sparklebot's wrapper."""
	if not isinstance(data, dict):
		return
	candidates = [data]
	wa = data.get("whatsapp")
	if isinstance(wa, dict):
		candidates.append(wa.get("original_payload") or wa)
	for c in candidates:
		if isinstance(c, str):
			try:
				c = json.loads(c)
			except ValueError:
				continue
		for entry in (c or {}).get("entry") or []:
			for change in entry.get("changes") or []:
				value = change.get("value")
				if isinstance(value, dict):
					yield value


def _parse_meta_message(m, names):
	mtype = m.get("type") or "unknown"
	text, button_id, media = None, None, None
	if mtype == "text":
		text = (m.get("text") or {}).get("body")
	elif mtype == "button":
		b = m.get("button") or {}
		text, button_id = b.get("text"), b.get("payload")
	elif mtype == "interactive":
		i = m.get("interactive") or {}
		reply = i.get("button_reply") or i.get("list_reply") or {}
		text, button_id = reply.get("title"), reply.get("id")
	elif mtype in ("image", "video", "document", "audio", "sticker"):
		obj = m.get(mtype) or {}
		text = obj.get("caption") or obj.get("filename")
		media = obj.get("link") or obj.get("url") or (obj.get("id") and f"media:{obj.get('id')}")
	elif mtype == "reaction":
		text = (m.get("reaction") or {}).get("emoji")
	elif mtype == "location":
		loc = m.get("location") or {}
		text = f"{loc.get('latitude')},{loc.get('longitude')} {loc.get('name') or ''}".strip()
	ts = m.get("timestamp")
	return {
		"wamid": m.get("id"),
		"phone": m.get("from"),
		"contact_name": names.get(m.get("from")),
		"message_type": mtype,
		"text": text,
		"button_id": button_id,
		"media_url": media,
		"context_wamid": (m.get("context") or {}).get("id"),
		"at": datetime.datetime.fromtimestamp(int(ts)) if ts and str(ts).isdigit() else now_datetime(),
	}


def _parse_wrapper(data):
	"""Sparklebot/WhatsMark wrapper: {event:{type}, data:{resource:{type, attributes}, relationships:{contact}}}."""
	res = ((data.get("data") or {}).get("resource") or {}) if isinstance(data.get("data"), dict) else {}
	attrs = res.get("attributes") or {}
	if res.get("type") == "status":
		return [], [{"wamid": attrs.get("message_id") or attrs.get("id"), "status": attrs.get("status")}]
	if res.get("type") != "message":
		return [], []
	contact = ((data.get("data") or {}).get("relationships") or {}).get("contact") or {}
	text = attrs.get("text")
	if isinstance(text, dict):
		text = text.get("body")
	ts = attrs.get("timestamp")
	return [{
		"wamid": attrs.get("message_id"),
		"phone": attrs.get("from") or contact.get("wa_id"),
		"contact_name": contact.get("name"),
		"message_type": attrs.get("type") or "unknown",
		"text": text,
		"button_id": attrs.get("button_id") or attrs.get("payload"),
		"media_url": attrs.get("media_url"),
		"context_wamid": (attrs.get("context") or {}).get("id") if isinstance(attrs.get("context"), dict) else None,
		"at": datetime.datetime.fromtimestamp(int(ts)) if ts and str(ts).isdigit() else now_datetime(),
	}], []


def parse(data):
	"""Return (messages, statuses)."""
	messages, statuses = [], []
	found_meta = False
	for value in _meta_payloads(data):
		found_meta = True
		names = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []}
		for m in value.get("messages") or []:
			messages.append(_parse_meta_message(m, names))
		for s in value.get("statuses") or []:
			statuses.append({"wamid": s.get("id"), "status": s.get("status"),
							 "error": json.dumps(s.get("errors")) if s.get("errors") else None})
	if not found_meta and isinstance(data, dict):
		messages, statuses = _parse_wrapper(data)
	return messages, statuses


# --------------------------------------------------------------------------- storing

def store_events(data, keep_raw=False):
	messages, statuses = parse(data)
	raw = json.dumps(data, ensure_ascii=False, default=str)[:60000] if keep_raw else None

	for s in statuses:
		_apply_status(s)

	names = []
	for m in messages:
		if not m.get("phone"):
			continue
		if m.get("wamid") and frappe.db.exists("WhatsApp Message", {"wamid": m["wamid"], "direction": "In"}):
			continue  # Sparklebot retried
		doc = frappe.get_doc({
			"doctype": "WhatsApp Message",
			"direction": "In",
			"status": "Received",
			"phone": normalize_phone("+" + str(m["phone"]).lstrip("+")) or m["phone"],
			"contact_name": m.get("contact_name"),
			"message_type": m["message_type"] if m["message_type"] in _types() else "unknown",
			"text": m.get("text"),
			"button_id": m.get("button_id"),
			"media_url": m.get("media_url"),
			"wamid": m.get("wamid"),
			"context_wamid": m.get("context_wamid"),
			"sent_or_received_at": m.get("at"),
			"raw": raw,
		}).insert(ignore_permissions=True)
		names.append(doc.name)
	return names


def _types():
	return frappe.get_meta("WhatsApp Message").get_field("message_type").options.split("\n")


def _apply_status(s):
	if not s.get("wamid"):
		return
	new = STATUS_MAP.get(s.get("status"))
	name = frappe.db.get_value("WhatsApp Message", {"wamid": s["wamid"], "direction": "Out"}, ["name", "status"], as_dict=True)
	if not new or not name:
		return
	if STATUS_RANK.get(new, 0) >= STATUS_RANK.get(name.status, 0):
		values = {"status": new}
		if new == "Failed" and s.get("error"):
			values["error"] = s["error"][:2000]
		frappe.db.set_value("WhatsApp Message", name.name, values, update_modified=False)


# --------------------------------------------------------------------------- routing

def process(message_name):
	msg = frappe.get_doc("WhatsApp Message", message_name)
	if msg.processed:
		return
	try:
		# 1. they wrote to us, so the 24-hour window is open: send anything we were holding
		outbox.flush_held(msg.phone)

		# 2. button taps from staff (approve / swap / skip / posted / shared), or the typed reply code
		#    ("A12") used when tap buttons are not available
		button_id = msg.button_id
		if not button_id and msg.message_type == "text":
			button_id = outbox.resolve_reply_code(msg.phone, msg.text)
			if button_id:
				msg.db_set("button_id", button_id)
		if button_id and ":" in button_id:
			prefix, action, docname = (button_id.split(":", 2) + ["", ""])[:3]
			route = BUTTON_ROUTES.get(prefix)
			if route:
				frappe.get_attr(route)(msg, action, docname)

		# 3. message from a share-check source (e.g. Hitesh sir) on a message day
		else:
			from techniti_connect import share_check

			share_check.capture(msg)

		msg.db_set("processed", 1)
	except Exception:
		msg.db_set("error", frappe.get_traceback()[-2000:])
		frappe.log_error(title="WhatsApp inbound processing failed", message=f"{message_name}\n{frappe.get_traceback()}")
