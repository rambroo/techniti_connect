"""Endpoints for the desk widgets and the /connect app."""

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from techniti_connect.whatsapp import outbox, party
from techniti_connect.whatsapp.phone import normalize_phone

WA_ROLES = {"WhatsApp Manager", "WhatsApp Agent", "System Manager"}
PANEL_LIMIT = 40


def _require_wa_role():
	if not WA_ROLES & set(frappe.get_roles()):
		frappe.throw(_("You need the WhatsApp Agent or WhatsApp Manager role."), frappe.PermissionError)


def _record_phones(doctype, name):
	if not frappe.has_permission(doctype, "read", doc=name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return party.phones_of(doctype, name)


@frappe.whitelist()
def record_whatsapp(doctype, name):
	"""WhatsApp history for a Donor / Website Donor form: messages linked to it or sent from its number."""
	_require_wa_role()
	keys = _record_phones(doctype, name)
	conditions = ["(party_doctype = %(dt)s and party_name = %(dn)s)"]
	values = {"dt": doctype, "dn": name}
	for i, key in enumerate(sorted(keys)):
		conditions.append(f"phone like %(k{i})s")
		values[f"k{i}"] = f"%{key}"
	rows = frappe.db.sql(
		f"""select name, direction, status, message_type, text, template_name, media_url, error,
			coalesce(sent_or_received_at, creation) as at, link_note
		from `tabWhatsApp Message` where {" or ".join(conditions)}
		order by coalesce(sent_or_received_at, creation) desc limit {PANEL_LIMIT}""",
		values,
		as_dict=True,
	)
	rows.reverse()
	phone = next(iter(sorted(keys)), None)
	last_in = next((r.at for r in reversed(rows) if r.direction == "In"), None)
	window_open = bool(last_in and last_in > add_to_date(now_datetime(), hours=-24))
	return {
		"phone": normalize_phone(phone) if phone else None,
		"has_phone": bool(keys),
		"messages": rows,
		"window_open": window_open,
		"window_closes": add_to_date(last_in, hours=24) if window_open else None,
		"shared_note": party.resolve(phone)["link_note"] if phone else None,
		"can_reply": window_open,
	}


@frappe.whitelist(methods=["POST"])
def send_reply(doctype, name, text):
	"""Free-text reply from the record's form (only while the 24-hour window is open)."""
	_require_wa_role()
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Type a message first."))
	keys = _record_phones(doctype, name)
	if not keys:
		frappe.throw(_("This record has no phone number."))
	phone = sorted(keys)[0]
	if not outbox.is_window_open(phone):
		frappe.throw(_("More than 24 hours since their last message. Only an approved template can be sent now."))
	msg = outbox.send(phone, "text", text=text[:4000], reference=(doctype, name), hold_if_closed=False)
	return {"status": msg.status, "error": msg.error}
