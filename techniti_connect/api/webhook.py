"""Endpoint Sparklebot forwards WhatsApp events to.

URL (shown on WhatsApp Setting):
    https://<site>/api/method/techniti_connect.api.webhook.receive?token=<webhook_secret>
"""

import hmac
import json

import frappe

from techniti_connect.whatsapp import inbound


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def receive(token=None, **kwargs):
	# With a JSON body Frappe only passes the body's keys, so read the token from the URL itself
	token = frappe.request.args.get("token") or token or frappe.get_request_header("X-Webhook-Token")
	if not _token_ok(token):
		frappe.local.response["http_status_code"] = 403
		return {"ok": False}

	if frappe.request.method == "GET":
		# Meta-style verification handshake, harmless otherwise
		return frappe.request.args.get("hub.challenge") or "ok"

	data = _read_body()
	if not data:
		return {"ok": True, "stored": 0}

	settings = frappe.get_cached_doc("WhatsApp Setting")
	names = inbound.store_events(data, keep_raw=bool(settings.get("log_incoming_raw")))
	frappe.db.commit()
	for name in names:
		frappe.enqueue("techniti_connect.whatsapp.inbound.process", queue="short", timeout=120,
					   message_name=name, enqueue_after_commit=True)
	return {"ok": True, "stored": len(names)}


def _token_ok(token):
	if not token:
		return False
	try:
		secret = frappe.get_cached_doc("WhatsApp Setting").get_password("webhook_secret", raise_exception=False)
	except Exception:
		secret = None
	return bool(secret) and hmac.compare_digest(str(token), str(secret))


def _read_body():
	try:
		data = frappe.request.get_json(silent=True)
	except Exception:
		data = None
	if data:
		return data
	raw = frappe.request.get_data(as_text=True)
	if raw:
		try:
			return json.loads(raw)
		except ValueError:
			pass
	form = frappe.request.form.to_dict() if frappe.request.form else {}
	for key in ("payload", "data", "body"):
		if form.get(key):
			try:
				return json.loads(form[key])
			except ValueError:
				pass
	return form or None
