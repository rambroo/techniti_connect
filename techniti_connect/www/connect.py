import frappe
from frappe import _

from techniti_connect.api.ui import WA_ROLES

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/connect"
		raise frappe.Redirect
	if not WA_ROLES & set(frappe.get_roles()):
		frappe.throw(_("You need the WhatsApp Agent or WhatsApp Manager role to open Techniti Connect."),
					 frappe.PermissionError)
	context.csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # get_csrf_token may write to the session
	context.no_cache = 1
	return context
