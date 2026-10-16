"""Runs one WhatsApp linked-device task in its own process and reports events to linked.py.

Started by linked.py; it does not import Frappe. The WhatsApp library (neonize/whatsmeow, a Go
library) keeps threads running after a disconnect, so every task gets a fresh process that ends
with os._exit and leaves nothing behind.

    python linked_runner.py <session db path> <link|check|post|unlink> <timeout seconds>

For "post", stdin is {"chat_id": "...@g.us", "gap": 8, "items": [{"kind": "image" | "video" | "text",
"path": "...", "caption": "...", "text": "..."}]}.

Events are JSON lines on stdout, each starting with MARK. The library prints to stdout too (for
example the login status as a bare number), so the real stdout is kept for events only and
everything else written to stdout is sent to stderr.

    {"event": "qr", "code"}            a QR code to show (link only)
    {"event": "paired"}                the phone accepted the link (link only)
    {"event": "syncing", "parts"}      connected after linking, receiving the phone's first sync (link only)
    {"event": "connected", "number", "name"}
    {"event": "groups", "groups": [{"id", "name"}]}
    {"event": "result", "results": [null | "error", ...]}
    {"event": "error", "kind": "not_linked" | "timeout" | "banned" | "refused" | "failed", "message"}
"""

import json
import logging
import os
import sys
import threading
import time

MARK = "@@TC@@ "
SESSION_ID = "techniti-posting"
log = logging.getLogger("techniti.runner")
SYNC_WAIT = {"check": 15, "post": 10, "unlink": 5}
# After linking, the phone sends the new device its first sync (settings and a little history). If the
# device disconnects before that finishes, WhatsApp logs it out ("an unexpected issue with syncing data
# from your phone"). So stay connected until the sync goes quiet: at least LINK_STAY_MIN seconds, then
# until nothing new arrived for LINK_STAY_QUIET seconds, at most LINK_STAY_MAX seconds.
LINK_STAY_MIN, LINK_STAY_QUIET, LINK_STAY_MAX = 45, 20, 240

_events = None
_emit_lock = threading.Lock()


def emit(**event):
	# called from the main thread and from the library's callback threads
	try:
		with _emit_lock:
			_events.write(MARK + json.dumps(event) + "\n")
			_events.flush()
	except (BrokenPipeError, OSError, ValueError):
		os._exit(2)  # linked.py is gone: nobody is listening, so stop


def sqlite_name(path):
	"""neonize opens its SQLite session as "file:<name>?_foreign_keys=on". Its threads write to the file at
	the same time; with the default settings they fail with "database is locked", and every connect then
	stalled for over a minute retrying the upload of its encryption keys. WAL plus a busy timeout lets them
	share the file. The trailing "&_tc" absorbs neonize's own "?_foreign_keys=on" (unknown keys are ignored)."""
	return f"{path}?_foreign_keys=on&_journal_mode=WAL&_busy_timeout=20000&_txlock=immediate&_tc"


def _watchdog(hard_limit):
	"""Never outlive the job that started us, or the hard time limit. The library keeps a
	non-daemon thread alive, so without this an orphaned process would stay connected forever."""
	parent, end = os.getppid(), time.time() + hard_limit

	def watch():
		while True:
			if os.getppid() != parent or time.time() > end:
				os._exit(3)
			time.sleep(2)

	threading.Thread(target=watch, daemon=True).start()


def finish(code=0):
	time.sleep(0.5)  # let the library's log queue drain into stderr
	for stream in (_events, sys.stderr):
		try:
			stream.flush()
		except Exception:
			pass
	os._exit(code)


def main():
	global _events
	# keep the real stdout for events; anything else printed to stdout goes to stderr
	_events = os.fdopen(os.dup(1), "w", buffering=1)
	os.dup2(2, 1)
	sys.stdout = sys.stderr

	db, command = sys.argv[1], sys.argv[2]
	timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 60
	payload = json.loads(sys.stdin.read() or "{}")
	_watchdog(hard_limit(command, timeout, payload))
	# stderr goes to a file that linked.py keeps when a task fails, so log the library at INFO
	logging.basicConfig(level=logging.DEBUG if os.environ.get("TC_RUNNER_DEBUG") else logging.INFO, stream=sys.stderr,
						format="%(asctime)s [%(name)s %(levelname)s] %(message)s")
	logging.getLogger("neonize.utils.log").setLevel(logging.DEBUG if os.environ.get("TC_RUNNER_DEBUG") else logging.INFO)

	from neonize.client import NewClient
	from neonize.events import (
		ConnectedEv,
		ConnectFailureEv,
		HistorySyncEv,
		LoggedOutEv,
		OfflineSyncCompletedEv,
		PairStatusEv,
		StreamErrorEv,
		TemporaryBanEv,
	)
	from neonize.proto.Neonize_pb2 import ConnectFailureReason, PairStatus
	from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps
	from neonize.utils.jid import Jid2String, build_jid

	def reason(code):
		try:
			return ConnectFailureReason.Name(code).replace("_", " ").lower()
		except ValueError:
			return f"code {code}"

	# "Techniti Connect" is the name shown on the phone under Linked devices. Ask the phone for as little
	# history as it allows: this device only posts, so the first sync stays small and finishes quickly.
	props = DeviceProps(
		os="Techniti Connect",
		platformType=DeviceProps.CHROME,
		requireFullSync=False,
		historySyncConfig=DeviceProps.HistorySyncConfig(
			fullSyncDaysLimit=1, fullSyncSizeMbLimit=1, storageQuotaMb=64, recentSyncDaysLimit=1
		),
	)
	client = NewClient(sqlite_name(db), props=props, uuid=SESSION_ID)
	ready = threading.Event()
	synced = threading.Event()
	problem = {}
	activity = {"last": time.time(), "parts": 0}

	def on_history(_c, e):
		activity["last"] = time.time()
		activity["parts"] += 1
		if command == "link":
			emit(event="syncing", parts=activity["parts"])

	def on_offline_synced(_c, _e):
		activity["last"] = time.time()
		synced.set()

	def stop_with(kind, message):
		log.warning("stopping: %s: %s", kind, message)
		if not problem:
			problem.update(kind=kind, message=message)
		ready.set()

	def on_qr(_c, data):
		if command == "link":
			emit(event="qr", code=data.decode() if isinstance(data, bytes) else str(data))
		else:
			stop_with("not_linked", "The posting number is not linked")

	def on_pair(_c, e):
		if e.Status == PairStatus.SUCCESS:
			emit(event="paired")
		else:
			stop_with("refused", f"Linking failed on WhatsApp's side ({e.Error or 'no reason given'})")

	def on_logged_out(_c, e):
		when = "while connecting" if e.OnConnect else "after connecting"
		stop_with("not_linked", f"WhatsApp logged the posting number out {when} ({reason(e.Reason)})")

	def on_failure(_c, e):
		stop_with("refused", f"WhatsApp refused the connection ({reason(e.Reason)}{': ' + e.Message if e.Message else ''})")

	client.event(ConnectedEv)(lambda _c, _e: ready.set())
	client.event(OfflineSyncCompletedEv)(on_offline_synced)
	client.event(HistorySyncEv)(on_history)
	client.event(PairStatusEv)(on_pair)
	client.event(LoggedOutEv)(on_logged_out)
	client.event(StreamErrorEv)(lambda _c, e: log.warning("stream error from WhatsApp: code %s", e.Code))
	client.event(TemporaryBanEv)(lambda _c, e: stop_with("banned", f"WhatsApp temporarily banned the number ({e.Code}, {e.Expire} s)"))
	client.event(ConnectFailureEv)(on_failure)
	client.event.qr(on_qr)

	worker = threading.Thread(target=client.connect, daemon=True)
	worker.start()
	if not ready.wait(timeout):
		emit(event="error", kind="timeout", message=f"WhatsApp did not connect within {timeout} seconds")
		finish(1)
	if problem:
		emit(event="error", **problem)
		finish(1)
	if command == "link":
		# stay connected while the phone sends the new device its first sync (see LINK_STAY_*)
		emit(event="syncing", parts=activity["parts"])
		start = activity["last"] = time.time()
		while not problem:
			elapsed, quiet = time.time() - start, time.time() - activity["last"]
			if elapsed >= LINK_STAY_MAX or (elapsed >= LINK_STAY_MIN and quiet >= LINK_STAY_QUIET):
				break
			time.sleep(1)
		log.info("first sync: %s history parts in %.0f s", activity["parts"], time.time() - start)
	else:
		# let WhatsApp deliver what it queued while we were offline
		synced.wait(SYNC_WAIT.get(command, 10))
	if problem:
		emit(event="error", **problem)
		finish(1)

	try:
		if command in ("link", "check"):
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
						try:
							client.send_message(jid, item["text"], link_preview=True)
						except Exception as e:
							# the preview step downloads the page; YouTube pages are too large for it
							# ("MaximumContentSizeError"), so send the plain link instead
							log.warning("link preview failed (%s), sending without it", e.__class__.__name__)
							client.send_message(jid, item["text"], link_preview=False)
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

	# close the connection and give the library a moment to finish writing its session file
	for close in (client.disconnect, client.stop):
		try:
			close()
		except Exception:
			pass
	worker.join(5)
	time.sleep(1)
	finish(0)


def hard_limit(command, timeout, payload):
	"""Seconds after which the process ends no matter what. linked.py waits a little longer."""
	items = len((payload or {}).get("items") or [])
	stay = LINK_STAY_MAX if command == "link" else SYNC_WAIT.get(command, 10)
	return timeout + stay + 60 + items * ((payload or {}).get("gap", 8) + 60)


if __name__ == "__main__":
	try:
		main()
	except BaseException as e:
		try:
			emit(event="error", kind="failed", message=f"{e.__class__.__name__}: {e}"[:500])
		finally:
			finish(1)
