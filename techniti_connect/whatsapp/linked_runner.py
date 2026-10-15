"""Runs one WhatsApp linked-device task in its own process and reports JSON lines on stdout.

Started by linked.py; it does not import Frappe. The WhatsApp library (neonize/whatsmeow, a Go
library) keeps threads running after a disconnect, so every task gets a fresh process that ends
with os._exit and leaves nothing behind.

    python linked_runner.py <session db path> <link|check|post|unlink> <timeout seconds>

For "post", stdin is {"chat_id": "...@g.us", "gap": 8, "items": [{"kind": "image" | "video" | "text",
"path": "...", "caption": "...", "text": "..."}]}.

Events: {"event": "qr", "code"}, {"event": "connected", "number", "name"}, {"event": "groups", "groups"},
{"event": "result", "results"}, {"event": "error", "kind": "not_linked" | "timeout" | "banned" | "refused" | "failed", "message"}
"""

import json
import logging
import os
import sys
import threading
import time

SESSION_ID = "techniti-posting"


def emit(**event):
	sys.stdout.write(json.dumps(event) + "\n")
	sys.stdout.flush()


def finish(code=0):
	sys.stdout.flush()
	sys.stderr.flush()
	os._exit(code)


def main():
	db, command = sys.argv[1], sys.argv[2]
	timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 60
	payload = json.loads(sys.stdin.read() or "{}") if command == "post" else {}
	logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

	from neonize.client import NewClient
	from neonize.events import ConnectedEv, ConnectFailureEv, LoggedOutEv, TemporaryBanEv
	from neonize.utils.jid import Jid2String, build_jid

	client = NewClient(db, uuid=SESSION_ID)
	ready = threading.Event()
	problem = {}

	def stop_with(kind, message):
		problem.update(kind=kind, message=message)
		ready.set()

	def on_qr(_c, data):
		if command == "link":
			emit(event="qr", code=data.decode() if isinstance(data, bytes) else str(data))
		else:
			stop_with("not_linked", "The posting number is not linked")

	client.event(ConnectedEv)(lambda _c, _e: ready.set())
	client.event(LoggedOutEv)(lambda _c, _e: stop_with("not_linked", "WhatsApp logged the posting number out"))
	client.event(TemporaryBanEv)(lambda _c, e: stop_with("banned", f"WhatsApp temporarily banned the number ({e})"))
	client.event(ConnectFailureEv)(lambda _c, e: stop_with("refused", f"WhatsApp refused the connection ({e})"))
	client.event.qr(on_qr)

	threading.Thread(target=client.connect, daemon=True).start()
	if not ready.wait(timeout):
		emit(event="error", kind="timeout", message=f"WhatsApp did not connect within {timeout} seconds")
		finish(1)
	if problem:
		emit(event="error", **problem)
		finish(1)

	try:
		if command in ("link", "check"):
			if command == "link":
				time.sleep(3)  # let WhatsApp finish its first sync
			me = client.get_me()
			emit(event="connected", number="+" + Jid2String(me.JID).split("@")[0].split(":")[0].split(".")[0],
				 name=me.PushName or None)
			groups = []
			for g in client.get_joined_groups():
				jid = Jid2String(g.JID)
				if jid.endswith("@g.us"):
					groups.append({"id": jid, "name": g.GroupName.Name or jid})
			emit(event="groups", groups=sorted(groups, key=lambda r: r["name"].lower()))
		elif command == "post":
			user, _, server = payload["chat_id"].partition("@")
			jid = build_jid(user, server or "g.us")
			results = []
			for i, item in enumerate(payload["items"]):
				if i:
					time.sleep(payload.get("gap", 8))
				try:
					if item["kind"] in ("image", "video"):
						with open(item["path"], "rb") as f:
							data = f.read()
						send = client.send_image if item["kind"] == "image" else client.send_video
						send(jid, data, caption=item.get("caption") or None)
					else:
						client.send_message(jid, item["text"], link_preview=True)
					results.append(None)
				except Exception as e:
					results.append(f"{e.__class__.__name__}: {e}"[:300])
			emit(event="result", results=results)
		elif command == "unlink":
			client.logout()
			emit(event="result", results=[])
	except Exception as e:
		emit(event="error", kind="failed", message=f"{e.__class__.__name__}: {e}"[:500])
		finish(1)

	try:
		client.disconnect()
	except Exception:
		pass
	time.sleep(1)
	finish(0)


if __name__ == "__main__":
	main()
