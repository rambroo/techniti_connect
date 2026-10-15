"""Group posting number: a separate WhatsApp number linked to a self-hosted WAHA server.

Used only to post approved content straight into WhatsApp groups, which the official API
(Sparklebot) cannot do. Donor conversations never go through this number.
"""

import mimetypes
import os

import frappe
import requests

TIMEOUT = 30
MEDIA_TIMEOUT = 180


class WahaError(Exception):
	pass


def settings():
	s = frappe.get_cached_doc("Group Posting Setting")
	url = (s.get("waha_url") or "").strip().rstrip("/")
	key = s.get_password("waha_api_key", raise_exception=False) if s.get("waha_url") else None
	return url, key, (s.get("waha_session") or "default").strip()


def configured():
	return bool(settings()[0])


def _call(method, path, timeout=TIMEOUT, **kwargs):
	url, key, _session = settings()
	if not url:
		raise WahaError("The group posting number is not set up (Group Posting Setting)")
	headers = kwargs.pop("headers", {})
	if key:
		headers["X-Api-Key"] = key
	try:
		r = requests.request(method, url + path, headers=headers, timeout=timeout, **kwargs)
	except requests.RequestException as e:
		raise WahaError(f"Cannot reach the WAHA server: {e.__class__.__name__}") from e
	if r.status_code == 401:
		raise WahaError("The WAHA server refused the API key")
	if r.status_code >= 400:
		raise WahaError(f"WAHA {r.status_code}: {r.text[:300]}")
	return r


# --------------------------------------------------------------------------- session

def status():
	"""{"status": "WORKING" | "SCAN_QR_CODE" | "STARTING" | "STOPPED" | "FAILED" | "MISSING", "me": {...}}"""
	session = settings()[2]
	try:
		data = _call("GET", f"/api/sessions/{session}").json()
	except WahaError as e:
		if " 404:" in str(e):
			return {"status": "MISSING", "me": None}
		raise
	return {"status": data.get("status"), "me": data.get("me")}


def start():
	"""Create the session if it does not exist, otherwise start it."""
	session = settings()[2]
	if status()["status"] == "MISSING":
		_call("POST", "/api/sessions", json={"name": session, "start": True})
	else:
		_call("POST", f"/api/sessions/{session}/start")


def logout():
	session = settings()[2]
	_call("POST", f"/api/sessions/{session}/logout")


def qr_data_url():
	import base64

	session = settings()[2]
	r = _call("GET", f"/api/{session}/auth/qr", headers={"Accept": "image/png"})
	return "data:image/png;base64," + base64.b64encode(r.content).decode()


def is_working():
	try:
		return configured() and status()["status"] == "WORKING"
	except WahaError:
		return False


def groups():
	"""[{"id": "...@g.us", "name": "..."}] for the groups the posting number is in."""
	session = settings()[2]
	data = _call("GET", f"/api/{session}/groups", params={"exclude": "participants"}, timeout=60).json()
	rows = data.values() if isinstance(data, dict) else data
	out = []
	for g in rows:
		gid = g.get("id")
		if isinstance(gid, dict):
			gid = gid.get("_serialized")
		name = g.get("subject") or g.get("name") or (g.get("groupMetadata") or {}).get("subject")
		if gid and str(gid).endswith("@g.us"):
			out.append({"id": gid, "name": name or gid})
	return sorted(out, key=lambda x: (x["name"] or "").lower())


# --------------------------------------------------------------------------- sending

def send_text(chat_id, text):
	session = settings()[2]
	return _call("POST", "/api/sendText", json={"session": session, "chatId": chat_id, "text": text,
											   "linkPreview": True, "linkPreviewHighQuality": True}).json()


def send_file(chat_id, kind, url, caption=None, filename=None):
	"""kind: image | video"""
	session = settings()[2]
	filename = filename or os.path.basename(url.split("?")[0]) or ("photo.jpg" if kind == "image" else "video.mp4")
	mimetype = mimetypes.guess_type(filename)[0] or ("image/jpeg" if kind == "image" else "video/mp4")
	body = {"session": session, "chatId": chat_id, "caption": caption or "",
			"file": {"url": url, "mimetype": mimetype, "filename": filename}}
	if kind == "video":
		body.update({"asNote": False, "convert": False})
	path = "/api/sendImage" if kind == "image" else "/api/sendVideo"
	return _call("POST", path, timeout=MEDIA_TIMEOUT, json=body).json()
