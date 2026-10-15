"""Group posting number: a separate WhatsApp number linked to this site as a WhatsApp "linked device".

It runs inside our own system on Frappe Cloud, with no extra server and nothing running all the time:
a background job starts linked_runner.py (neonize, a Python binding of the whatsmeow library) in a
short-lived process that connects, does one task (link the number, post into a group, list groups,
check the link) and exits. Used only to post approved content into WhatsApp groups. Donor messages
always use the official number (Sparklebot).
"""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

import frappe
from frappe.utils import now_datetime

SETTING = "Group Posting Setting"
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linked_runner.py")
CONNECT_TIMEOUT = 60
LINK_TIMEOUT = 180
POST_GAP_SECONDS = 8


class LinkedError(Exception):
	def __init__(self, message, kind="failed"):
		super().__init__(message)
		self.kind = kind


def _key(name):
	return f"techniti_connect:{frappe.local.site}:{name}"


def db_path():
	folder = os.path.abspath(frappe.get_site_path("private", "techniti_connect"))
	os.makedirs(folder, exist_ok=True)
	return os.path.join(folder, "posting-number.db")


def is_linked():
	return frappe.db.get_single_value(SETTING, "status") == "Linked"


# --------------------------------------------------------------------------- state shown in /connect

def linking_state():
	raw = frappe.cache.get(_key("linking"))
	return json.loads(raw) if raw else None


def _set_linking(state, **extra):
	frappe.cache.set(_key("linking"), json.dumps({"state": state, **extra}), ex=LINK_TIMEOUT + 300)


def _save(**values):
	doc = frappe.get_doc(SETTING)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()


# --------------------------------------------------------------------------- running a task

def _run(command, timeout, payload=None, on_event=None):
	"""Run one task in its own process. Returns the events it reported; raises LinkedError on failure."""
	if not frappe.cache.set(_key("lock"), "1", nx=True, ex=timeout + 120):
		raise LinkedError("Another WhatsApp task for the posting number is still running", "busy")
	events, lines = [], queue.Queue()
	err = tempfile.TemporaryFile(mode="w+")
	try:
		proc = subprocess.Popen([sys.executable, RUNNER, db_path(), command, str(timeout)], stdin=subprocess.PIPE,
								stdout=subprocess.PIPE, stderr=err, text=True)
		proc.stdin.write(json.dumps(payload or {}))
		proc.stdin.close()

		def read():
			for ln in proc.stdout:
				lines.put(ln)

		threading.Thread(target=read, daemon=True).start()
		deadline = time.time() + timeout + 120 + (len((payload or {}).get("items", [])) * (POST_GAP_SECONDS + 60))
		while time.time() < deadline:
			try:
				line = lines.get(timeout=1)
			except queue.Empty:
				if proc.poll() is not None and lines.empty():
					break
				continue
			try:
				event = json.loads(line)
			except ValueError:
				continue
			events.append(event)
			if on_event:
				on_event(event)
		if proc.poll() is None:
			proc.kill()
			raise LinkedError("The WhatsApp task took too long and was stopped", "timeout")
		error = next((e for e in events if e.get("event") == "error"), None)
		if error:
			if error.get("kind") == "not_linked":
				_mark_unlinked(error.get("message"))
			raise LinkedError(error.get("message") or "WhatsApp task failed", error.get("kind") or "failed")
		if proc.returncode:
			err.seek(0)
			frappe.log_error(title=f"Posting number task '{command}' failed", message=err.read()[-4000:])
			raise LinkedError("The WhatsApp task stopped unexpectedly")
		return events
	finally:
		err.close()
		frappe.cache.delete(_key("lock"))


def _groups_json(events):
	return json.dumps(next((e["groups"] for e in events if e.get("event") == "groups"), []))


def _mark_unlinked(reason):
	if is_linked():
		_save(status="Not linked", last_checked=now_datetime(), last_error=reason)
		_alert(f"The group posting number was unlinked from WhatsApp ({reason}). Posts go to the group admins to "
			   "forward until it is linked again in /connect > Groups.")


def _alert(text):
	from techniti_connect.whatsapp import outbox

	phones = {}
	for g in frappe.get_all("WhatsApp Group", filters={"enabled": 1, "posting_method": "Post Directly"},
							fields=["approver_phone", "approver_name"]):
		if g.approver_phone:
			phones[g.approver_phone] = g.approver_name
	for phone, name in phones.items():
		outbox.send(phone, "text", text=text, contact_name=name, reference=(SETTING, SETTING))


# --------------------------------------------------------------------------- jobs

def link_job():
	"""Background job: show a QR code in /connect until the posting phone scans it."""
	_set_linking("starting")
	if os.path.exists(db_path()):
		os.remove(db_path())

	def on_event(event):
		if event.get("event") == "qr":
			_set_linking("qr", qr=event["code"])

	try:
		events = _run("link", LINK_TIMEOUT, on_event=on_event)
		me = next(e for e in events if e.get("event") == "connected")
		_save(status="Linked", linked_number=me.get("number"), linked_name=me.get("name"), linked_on=now_datetime(),
			  last_checked=now_datetime(), last_error=None, groups_json=_groups_json(events))
		_set_linking("done")
	except LinkedError as e:
		_set_linking("failed", error="The QR code was not scanned in time" if e.kind == "timeout" else str(e))
	except Exception as e:
		frappe.log_error(title="Link posting number failed", message=frappe.get_traceback())
		_set_linking("failed", error=f"Could not link ({e.__class__.__name__})")


def check_job():
	"""Background job (daily, and Refresh groups in /connect): keep the link fresh, refresh the group list."""
	if not is_linked():
		return
	try:
		events = _run("check", CONNECT_TIMEOUT)
		_save(last_checked=now_datetime(), last_error=None, groups_json=_groups_json(events))
	except LinkedError as e:
		if is_linked():
			_save(last_checked=now_datetime(), last_error=str(e)[:500])


def daily_check():
	if is_linked():
		frappe.enqueue("techniti_connect.whatsapp.linked.check_job", queue="long", timeout=600,
					   job_id=f"tc-linked-check-{frappe.local.site}", deduplicate=True)


def unlink_job():
	try:
		if is_linked():
			_run("unlink", CONNECT_TIMEOUT)
	except Exception:
		frappe.log_error(title="Unlink posting number", message=frappe.get_traceback())
	if os.path.exists(db_path()):
		os.remove(db_path())
	_save(status="Not linked", linked_number=None, linked_name=None, groups_json=None, last_error=None)
	_set_linking("unlinked")


# --------------------------------------------------------------------------- posting

def post_many(chat_id, items):
	"""items: [{"kind": "image" | "video", "path": "..."} or {"kind": "text", "text": "..."}, with "caption"].
	Returns one error message (or None) per item. Raises LinkedError if it cannot connect at all."""
	events = _run("post", CONNECT_TIMEOUT, payload={"chat_id": chat_id, "items": items, "gap": POST_GAP_SECONDS})
	result = next((e for e in events if e.get("event") == "result"), None)
	if not result:
		raise LinkedError("WhatsApp did not report the result")
	_save(last_checked=now_datetime(), last_error=None)
	return result["results"]
