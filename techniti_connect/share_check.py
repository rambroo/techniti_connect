"""Share check: a message that arrives on set days (e.g. Hitesh sir on Tue/Thu/Sat) must be shared in a
group the next day.

Flow: the source (or a volunteer) sends/forwards the message to the foundation's WhatsApp number ->
captured here -> next day at forward_time the group admin gets it ready to forward with a "Shared"
button -> alerts if no message arrives, escalation if not shared in time.
"""

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, getdate, now_datetime, nowdate

from techniti_connect.whatsapp import outbox
from techniti_connect.whatsapp.phone import phone_key, split_phones

DAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def is_source_day(rule, date):
	return bool(rule.get(DAY_FIELDS[getdate(date).weekday()]))


def hhmm(value):
	"""'9:00:00' / timedelta / time -> '09:00'."""
	parts = str(value or "").split(":")
	return f"{int(parts[0]):02d}:{parts[1]}" if len(parts) >= 2 and parts[0].isdigit() else str(value)


def at(date, time):
	return get_datetime(f"{date} {time}")


def ensure_check(rule, source_date):
	name = frappe.db.get_value("Share Check", {"rule": rule.name, "source_date": source_date})
	if name:
		return frappe.get_doc("Share Check", name)
	return frappe.get_doc({
		"doctype": "Share Check",
		"rule": rule.name,
		"source_date": source_date,
		"share_date": add_days(source_date, 1),
		"status": "Waiting for Message",
	}).insert(ignore_permissions=True)


# --------------------------------------------------------------------------- capture

def capture(msg):
	"""Called for every incoming message that is not a button tap."""
	sender = phone_key(msg.phone)
	if not sender:
		return
	today = getdate(nowdate())
	for rule in frappe.get_all("Share Check Rule", filters={"enabled": 1}, fields=["*"]):
		if sender not in split_phones(rule.source_phones):
			continue
		check = None
		if is_source_day(rule, today):
			check = ensure_check(rule, today)
		else:
			# late forward after midnight: attach to yesterday's check if still open
			name = frappe.db.get_value("Share Check", {"rule": rule.name, "source_date": add_days(today, -1),
								"status": ["in", ["Waiting for Message", "Received"]]})
			check = frappe.get_doc("Share Check", name) if name else None
		if not check or check.status not in ("Waiting for Message", "Received"):
			continue
		check.db_set({
			"status": "Received",
			"message_type": msg.message_type,
			"message_text": msg.text,
			"media_url": msg.media_url,
			"inbound_message": msg.name,
			"received_on": now_datetime(),
		})
		group = rule.whatsapp_group
		outbox.send(msg.phone, "text", hold_if_closed=False, contact_name=msg.contact_name, reference=("Share Check", check.name),
					text=f"Received ✅ It will be sent to the {group} admin on {getdate(check.share_date).strftime('%A')} "
					f"at {hhmm(rule.forward_time)} to share.")


# --------------------------------------------------------------------------- scheduler

def tick():
	"""Every 15 minutes."""
	now = now_datetime()
	today = getdate(nowdate())
	for rule in frappe.get_all("Share Check Rule", filters={"enabled": 1}, fields=["*"]):
		try:
			_tick_rule(rule, now, today)
		except Exception:
			frappe.log_error(title=f"Share check tick failed: {rule.name}", message=frappe.get_traceback())
	frappe.db.commit()


def _tick_rule(rule, now, today):
	group = frappe.get_cached_doc("WhatsApp Group", rule.whatsapp_group)

	if is_source_day(rule, today):
		check = ensure_check(rule, today)
		if check.status == "Waiting for Message" and not check.missing_alert_sent and now >= at(today, rule.missing_alert_time):
			_alert(rule, group, check, f"No message from {rule.source_name or 'the source'} has reached the foundation's "
						   f"WhatsApp today ({today.strftime('%A')}). Please forward it to this number.")
			check.db_set("missing_alert_sent", 1)

	for name in frappe.get_all("Share Check", filters={"rule": rule.name, "share_date": today,
							   "status": ["in", ["Waiting for Message", "Received", "Sent to Admin"]]}, pluck="name"):
		check = frappe.get_doc("Share Check", name)
		if check.status == "Received" and now >= at(today, rule.forward_time):
			send_to_admin(rule, group, check)
		if not check.escalated and now >= at(today, rule.escalate_time) and check.status != "Shared":
			state = {"Waiting for Message": "was never received", "Received": "was not sent",
					 "Sent to Admin": "is not marked as shared yet"}.get(check.status, check.status)
			_alert(rule, group, check, f"{rule.source_name or 'The'} message from {getdate(check.source_date).strftime('%A')} "
						   f"{state} for {group.name}.", escalate=True)
			check.db_set("escalated", 1)

	# day over: anything not shared is Missed
	for name in frappe.get_all("Share Check", filters={"rule": rule.name, "share_date": ["<", today],
							   "status": ["in", ["Waiting for Message", "Received", "Sent to Admin"]]}, pluck="name"):
		frappe.db.set_value("Share Check", name, "status", "Missed")


def send_to_admin(rule, group, check):
	ref = ("Share Check", check.name)
	who = rule.source_name or "the source"
	outbox.send(group.admin_phone, "text", contact_name=group.admin_name, reference=ref,
				nudge_text=f"{who}'s message is ready to share in {group.name}",
				text=f"Please share {who}'s message in *{group.name}* today. It is in the next message.")
	media = check.media_url or ""
	if media.startswith("http"):
		kind = check.message_type if check.message_type in ("image", "video", "document", "audio") else "document"
		outbox.send(group.admin_phone, "media", media_type=kind, media_url=media, caption=check.message_text,
					contact_name=group.admin_name, reference=ref)
	elif check.message_text:
		outbox.send(group.admin_phone, "text", text=check.message_text, contact_name=group.admin_name, reference=ref)
	if media.startswith("media:"):
		outbox.send(group.admin_phone, "text", contact_name=group.admin_name, reference=ref,
					text=f"Note: it was a {check.message_type}. WhatsApp does not let us re-send received media, "
					"so please forward it from the foundation's chat (Sparklebot > Chat).")
	outbox.send(group.admin_phone, "buttons", contact_name=group.admin_name, reference=ref,
				text=f"Once you have shared it in {group.name}, confirm here.", buttons=[[f"sc:shared:{check.name}", "Shared"]])
	check.db_set({"status": "Sent to Admin", "sent_to_admin_on": now_datetime()})


def _alert(rule, group, check, text, escalate=False):
	targets = [(group.admin_phone, group.admin_name)]
	if escalate and rule.escalate_phone:
		targets.append((rule.escalate_phone, rule.escalate_name))
	seen = set()
	for phone, name in targets:
		if not phone or phone_key(phone) in seen:
			continue
		seen.add(phone_key(phone))
		outbox.send(phone, "text", text=text, contact_name=name, reference=("Share Check", check.name), nudge_text=text[:200])


# --------------------------------------------------------------------------- confirmation

def mark_shared(check_name):
	check = frappe.get_doc("Share Check", check_name)
	if check.status == "Shared":
		return
	now = now_datetime()
	check.db_set({"status": "Shared", "shared_on": now, "shared_on_time": int(now.date() <= getdate(check.share_date))})


def handle_button(msg, action, check_name):
	if action != "shared" or not frappe.db.exists("Share Check", check_name):
		return
	check = frappe.get_doc("Share Check", check_name)
	rule = frappe.get_cached_doc("Share Check Rule", check.rule)
	group = frappe.get_cached_doc("WhatsApp Group", rule.whatsapp_group)
	allowed = {phone_key(group.admin_phone), phone_key(rule.escalate_phone), phone_key(group.approver_phone)}
	if phone_key(msg.phone) not in allowed:
		outbox.send(msg.phone, "text", text="This button is not meant for your number.", hold_if_closed=False)
		return
	mark_shared(check_name)
	outbox.send(msg.phone, "text", text=f"Thanks! Marked as shared in {group.name}.", hold_if_closed=False)


@frappe.whitelist()
def shared(check_name):
	if not frappe.has_permission("Share Check", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	mark_shared(check_name)
