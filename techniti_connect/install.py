import secrets

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password

MODULE = "Techniti Connect"
# DocTypes that lived in the techniti app before; their tables and data are kept as-is
MOVED_DOCTYPES = [
	"WhatsApp Setting", "WhatsApp Queue", "WhatsApp Notification", "WhatsApp Message Template",
	"WhatsApp Template Parameter", "WhatsApp Notification Recipient", "WhatsApp Linked Document",
]
ROLES = ["WhatsApp Manager", "WhatsApp Agent"]


def before_install():
	"""Re-home the WhatsApp DocTypes from techniti so syncing this app updates them instead of clashing.
	(The installer creates the Module Def itself right after this hook.)"""
	for dt in MOVED_DOCTYPES:
		if frappe.db.exists("DocType", dt):
			frappe.db.set_value("DocType", dt, "module", MODULE, update_modified=False)
	frappe.db.commit()


def after_install():
	ensure_roles()
	secure_settings()
	create_starting_records()


def after_migrate():
	ensure_roles()
	secure_settings()


def ensure_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)


def secure_settings():
	"""api_token used to be a plain Data field: move any plain value into encrypted storage, and
	make sure an incoming-webhook secret exists."""
	dt = "WhatsApp Setting"
	raw = _single_raw(dt, "api_token")
	if raw and set(raw) != {"*"}:
		set_encrypted_password(dt, dt, raw, "api_token")
		frappe.db.set_single_value(dt, "api_token", "*" * len(raw))

	secret = get_decrypted_password(dt, dt, "webhook_secret", raise_exception=False)
	if not secret:
		secret = secrets.token_urlsafe(32)
		set_encrypted_password(dt, dt, secret, "webhook_secret")
		frappe.db.set_single_value(dt, "webhook_secret", "*" * len(secret))
	from techniti_connect.techniti_connect.doctype.whatsapp_setting.whatsapp_setting import get_webhook_url

	frappe.db.set_single_value(dt, "webhook_url", get_webhook_url(secret))
	if not frappe.db.get_single_value(dt, "api_v2_base_url"):
		frappe.db.set_single_value(dt, "api_v2_base_url", "https://sparklebot.in/api/v2")
	frappe.db.commit()


def create_starting_records():
	"""The three requested flows, created disabled with blank numbers so nothing is sent until set up."""
	groups = [
		("Stand Firm in the Faith", "Weekly motivational video, photo and reel", "Sunday", "07:00:00",
		 [("Video", 1), ("Photo", 1), ("Reel", 1)]),
		("Students Group", "One photo a week", "Monday", "08:00:00", [("Photo", 1)]),
		("Hitesh Sir Group", "Receives Hitesh sir's Tue/Thu/Sat message the next day", "Sunday", "09:00:00", []),
	]
	for name, purpose, weekday, time, slots in groups:
		if frappe.db.exists("WhatsApp Group", name):
			continue
		doc = frappe.get_doc({
			"doctype": "WhatsApp Group", "group_name": name, "enabled": 0, "purpose": purpose,
			"post_weekday": weekday, "post_time": time, "plan_days_before": 2,
			"slots": [{"content_type": t, "qty": q} for t, q in slots],
		})
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)

	if not frappe.db.exists("Share Check Rule", "Hitesh Sir"):
		rule = frappe.get_doc({
			"doctype": "Share Check Rule", "rule_name": "Hitesh Sir", "enabled": 0, "source_name": "Hitesh Sir",
			"source_phones": "", "whatsapp_group": "Hitesh Sir Group",
			"tuesday": 1, "thursday": 1, "saturday": 1,
			"forward_time": "09:00:00", "escalate_time": "18:00:00", "missing_alert_time": "21:00:00",
		})
		rule.flags.ignore_mandatory = True
		rule.flags.ignore_validate = True
		rule.insert(ignore_permissions=True)
	frappe.db.commit()


def _single_raw(doctype, field):
	rows = frappe.db.sql("select value from `tabSingles` where doctype=%s and field=%s", (doctype, field))
	return rows[0][0] if rows else None
