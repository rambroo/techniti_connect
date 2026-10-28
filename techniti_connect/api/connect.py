"""Backend for the /connect app. Every endpoint needs a WhatsApp role."""

import datetime
import json

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime, nowdate

from techniti_connect import groups as group_logic
from techniti_connect import share_check
from techniti_connect.api.ui import WA_ROLES
from techniti_connect.whatsapp import linked, outbox
from techniti_connect.whatsapp.phone import normalize_phone, phone_key


def _guard(manager=False):
	roles = set(frappe.get_roles())
	allowed = {"WhatsApp Manager", "System Manager"} if manager else WA_ROLES
	if not allowed & roles:
		frappe.throw(_("You need the WhatsApp Agent or WhatsApp Manager role."), frappe.PermissionError)


# --------------------------------------------------------------------------- boot / home

@frappe.whitelist()
def boot():
	_guard()
	user = frappe.get_cached_doc("User", frappe.session.user)
	s = frappe.get_cached_doc("WhatsApp Setting")
	return {
		"user": {"name": user.name, "full_name": user.full_name, "initials": _initials(user.full_name or user.name)},
		"is_manager": bool({"WhatsApp Manager", "System Manager"} & set(frappe.get_roles())),
		"whatsapp_enabled": bool(s.enabled),
		"counts": _counts(),
	}


def _counts():
	return {
		"approvals": frappe.db.count("Group Post", {"status": "Proposed"}),
		"unanswered": len(_unanswered_phones()),
	}


@frappe.whitelist()
def home():
	_guard()
	today = getdate(nowdate())
	start, end = today - datetime.timedelta(days=today.weekday()), today + datetime.timedelta(days=13)
	posts = frappe.get_all("Group Post", filters={"post_date": ["between", [start, end]]},
						   fields=["name", "whatsapp_group", "post_date", "content_type", "status"], order_by="post_date asc")
	week = {}
	for p in posts:
		key = (p.whatsapp_group, str(p.post_date))
		row = week.setdefault(key, {"group": p.whatsapp_group, "date": str(p.post_date), "types": [], "statuses": []})
		row["types"].append(p.content_type)
		row["statuses"].append(p.status)
	for row in week.values():
		row["time"] = str(frappe.db.get_value("WhatsApp Group", row["group"], "post_time") or "")[:5]
		row["summary"] = _summary(row["statuses"])
	checks = frappe.get_all("Share Check", filters={"source_date": [">=", today - datetime.timedelta(days=7)]},
							fields=["name", "rule", "source_date", "share_date", "status", "shared_on", "shared_on_time"],
							order_by="source_date asc")
	return {
		"counts": _counts(),
		"week": sorted(week.values(), key=lambda r: r["date"]),
		"checks": checks,
		"recent": _recent_inbound(8),
		"group_count": frappe.db.count("WhatsApp Group", {"enabled": 1}),
	}


def _summary(statuses):
	if all(s == "Posted" for s in statuses):
		return "Posted"
	if "Proposed" in statuses:
		return f"{statuses.count('Proposed')} to approve"
	for s in ("Sent to Admin", "Approved", "Missed", "Failed", "Skipped"):
		if s in statuses:
			return s
	return statuses[0] if statuses else ""


# --------------------------------------------------------------------------- approvals

@frappe.whitelist()
def approvals(status="Proposed"):
	_guard()
	if status == "Done":
		filters = {"status": ["in", ["Sent to Admin", "Posted", "Skipped", "Missed", "Failed"]],
				   "post_date": [">=", add_days(nowdate(), -21)]}
	else:
		filters = {"status": status}
	posts = frappe.get_all("Group Post", filters=filters, order_by="post_date asc, name asc",
						   fields=["name", "whatsapp_group", "post_date", "content_type", "content", "caption", "status",
								   "approved_by", "error"], limit_page_length=200)
	contents = _contents([p.content for p in posts if p.content])
	batches = {}
	for p in posts:
		key = (p.whatsapp_group, str(p.post_date))
		if key not in batches:
			g = frappe.get_cached_doc("WhatsApp Group", p.whatsapp_group)
			batches[key] = {"group": g.name, "date": str(p.post_date), "time": str(g.post_time or "")[:5],
							"approver": g.approver_name, "admin": g.admin_name, "posts": [],
							"direct": g.posting_method == "Post Directly", "target": g.group_chat_name or g.group_chat_id}
		batches[key]["posts"].append({**p, "post_date": str(p.post_date), "content_doc": contents.get(p.content)})
	return list(batches.values())


def _contents(names):
	if not names:
		return {}
	rows = frappe.get_all("Group Content", filters={"name": ["in", list(set(names))]},
						  fields=["name", "title", "content_type", "file", "link", "caption", "auto_source", "source_credit",
								  "status", "times_used"])
	return {r.name: r for r in rows}


@frappe.whitelist(methods=["POST"])
def decide(post_name, action):
	_guard()
	if action == "approve":
		group_logic.approve(post_name)
	elif action == "skip":
		group_logic.skip(post_name)
	elif action == "swap":
		if group_logic.swap(post_name) != "Swapped":
			frappe.throw(_("No other content available for this slot. Add more in the Library or turn on automatic content."))
	elif action == "posted":
		group_logic.posted(post_name)
	else:
		frappe.throw(_("Unknown action"))
	return _post(post_name)


@frappe.whitelist(methods=["POST"])
def approve_all(group, post_date):
	_guard()
	done = []
	for name in frappe.get_all("Group Post", filters={"whatsapp_group": group, "post_date": post_date,
							   "status": "Proposed", "content": ["is", "set"]}, pluck="name"):
		group_logic.approve(name)
		done.append(name)
	return done


@frappe.whitelist(methods=["POST"])
def set_caption(post_name, caption):
	_guard()
	if not frappe.has_permission("Group Post", "write", doc=post_name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	frappe.db.set_value("Group Post", post_name, "caption", (caption or "").strip()[:1024])
	return _post(post_name)


def _post(name):
	p = frappe.db.get_value("Group Post", name, ["name", "whatsapp_group", "post_date", "content_type", "content", "caption",
												  "status", "approved_by", "error"], as_dict=True)
	p["post_date"] = str(p.post_date)
	p["content_doc"] = _contents([p.content]).get(p.content) if p.content else None
	return p


@frappe.whitelist(methods=["POST"])
def plan_now(group):
	_guard(manager=True)
	return group_logic.plan_now(group)


# --------------------------------------------------------------------------- library

@frappe.whitelist()
def library(content_type=None, source=None, group=None, status="Active", start=0):
	_guard()
	filters = {}
	if content_type:
		filters["content_type"] = content_type
	if status:
		filters["status"] = status
	if source == "Uploaded":
		filters["auto_source"] = ["is", "not set"]
	elif source:
		filters["auto_source"] = source
	if group:
		allowed = frappe.get_all("Group Content Group", filters={"whatsapp_group": group}, pluck="parent")
		unrestricted = frappe.db.sql_list("""select name from `tabGroup Content` gc where not exists
			(select 1 from `tabGroup Content Group` g where g.parent = gc.name)""")
		filters["name"] = ["in", list(set(allowed) | set(unrestricted)) or ["-"]]
	rows = frappe.get_all("Group Content", filters=filters, order_by="creation desc", start=int(start), page_length=48,
						  fields=["name", "title", "content_type", "file", "link", "caption", "auto_source", "source_credit",
								  "status", "times_used", "last_used_on"])
	names = [r.name for r in rows] or ["-"]
	links = {}
	for g in frappe.get_all("Group Content Group", filters={"parent": ["in", names]}, fields=["parent", "whatsapp_group"]):
		links.setdefault(g.parent, []).append(g.whatsapp_group)
	planned = dict(frappe.db.sql("""select content, min(post_date) from `tabGroup Post`
		where status in ('Proposed', 'Approved') and content in %(n)s group by content""", {"n": names}))
	for r in rows:
		r["groups"] = links.get(r.name, [])
		r["planned_for"] = str(planned[r.name]) if r.name in planned else None
	return rows


@frappe.whitelist(methods=["POST"])
def add_content(title, content_type, file=None, link=None, caption=None, group=None):
	_guard()
	doc = frappe.get_doc({
		"doctype": "Group Content", "title": title, "content_type": content_type, "file": file or None,
		"link": link or None, "caption": caption, "status": "Active",
		"groups": [{"whatsapp_group": group}] if group else [],
	})
	doc.insert()
	return doc.name


@frappe.whitelist(methods=["POST"])
def generate(group, content_type):
	_guard(manager=True)
	from techniti_connect.content import autofill

	doc = autofill.create_one(frappe.get_doc("WhatsApp Group", group), content_type)
	if not doc:
		frappe.throw(_("Could not create a {0}. For videos and reels add the Pexels or YouTube key in WhatsApp Setting.").format(
			content_type.lower()))
	return doc.name


@frappe.whitelist(methods=["POST"])
def set_content_status(name, status):
	_guard()
	if status not in ("Active", "Retired"):
		frappe.throw(_("Invalid status"))
	frappe.get_doc("Group Content", name).db_set("status", status)
	return status


# --------------------------------------------------------------------------- groups and share checks

@frappe.whitelist()
def groups():
	_guard()
	out = []
	for g in frappe.get_all("WhatsApp Group", fields=["name", "enabled", "purpose", "post_weekday", "post_time",
							"admin_name", "admin_phone", "approver_name", "approver_phone", "auto_content", "content_theme",
							"posting_method", "group_chat_id", "group_chat_name"],
							order_by="name asc"):
		doc = frappe.get_cached_doc("WhatsApp Group", g.name)
		g["slots"] = [{"type": s.content_type, "qty": s.qty} for s in doc.slots]
		g["post_time"] = str(g.post_time or "")[:5]
		g["next_date"] = str(group_logic.next_post_date(doc)) if g.post_weekday else None
		g["unused"] = {s.content_type: _unused_count(doc, s.content_type) for s in doc.slots}
		g["admin_phone"] = _mask(g.admin_phone)
		g["approver_phone"] = _mask(g.approver_phone)
		out.append(g)
	rules = frappe.get_all("Share Check Rule", fields=["name", "enabled", "source_name", "whatsapp_group", "forward_time",
							"escalate_time", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
	for r in rules:
		r["days"] = [d.title()[:3] for d in share_check.DAY_FIELDS if r.get(d)]
		r["forward_time"] = str(r.forward_time or "")[:5]
		r["escalate_time"] = str(r.escalate_time or "")[:5]
		r["checks"] = frappe.get_all("Share Check", filters={"rule": r.name}, order_by="source_date desc", limit=12,
									 fields=["name", "source_date", "share_date", "status", "received_on", "sent_to_admin_on",
											 "shared_on", "shared_on_time"])
		month = frappe.get_all("Share Check", filters={"rule": r.name, "source_date": [">=", add_days(nowdate(), -30)],
								 "share_date": ["<", nowdate()]}, fields=["shared_on_time"])
		r["month_total"] = len(month)
		r["month_on_time"] = sum(1 for m in month if m.shared_on_time)
	return {"groups": out, "rules": rules}


def _unused_count(group, ctype):
	count, taken = 0, []
	while count < 10:
		c = group_logic.pick_content(group, ctype, exclude=taken)
		if not c:
			break
		taken.append(c.name)
		count += 1
	return count


def _mask(phone):
	key = phone_key(phone)
	return f"…{key[-4:]}" if key else None


@frappe.whitelist(methods=["POST"])
def set_auto(group, enabled, theme=None):
	_guard(manager=True)
	doc = frappe.get_doc("WhatsApp Group", group)
	doc.auto_content = 1 if frappe.utils.cint(enabled) else 0
	if theme:
		doc.content_theme = theme
	doc.flags.ignore_mandatory = True
	doc.save()
	return doc.auto_content


@frappe.whitelist(methods=["POST"])
def send_now(post_name):
	"""Send an approved post now instead of waiting for the group's post time."""
	_guard(manager=True)
	post = frappe.get_doc("Group Post", post_name)
	if post.status != "Approved":
		frappe.throw(_("Only approved posts can be sent now"))
	group = frappe.get_doc("WhatsApp Group", post.whatsapp_group)
	if group.posting_method == "Post Directly":
		frappe.enqueue("techniti_connect.groups.post_direct", queue="long", timeout=900, post_names=[post.name],
					   job_id=f"tc-direct-now-{frappe.local.site}-{post.name}", deduplicate=True)
		return {"method": "direct", "target": group.group_chat_name or group.group_chat_id}
	group_logic.send_to_admin(post.name)
	return {"method": "admin", "target": group.admin_name}


@frappe.whitelist(methods=["POST"])
def set_posting(group, method, chat_id=None, chat_name=None):
	_guard(manager=True)
	if method not in ("Forward via Admin", "Post Directly"):
		frappe.throw(_("Unknown posting method"))
	doc = frappe.get_doc("WhatsApp Group", group)
	doc.posting_method = method
	if chat_id is not None:
		doc.group_chat_id = chat_id or None
		doc.group_chat_name = chat_name or None
	doc.flags.ignore_mandatory = True
	doc.save()
	return {"posting_method": doc.posting_method, "group_chat_id": doc.group_chat_id, "group_chat_name": doc.group_chat_name}


# --------------------------------------------------------------------------- group posting number

@frappe.whitelist()
def poster():
	"""Posting number status. While linking, includes the QR code to scan (as an SVG data URL)."""
	_guard(manager=True)
	s = frappe.get_cached_doc("Group Posting Setting")
	out = {"status": s.status or "Not linked", "number": s.linked_number, "name": s.linked_name,
		   "last_checked": s.last_checked, "last_error": s.last_error,
		   "group_count": len(json.loads(s.groups_json or "[]"))}
	state = linked.linking_state()
	if state and state.get("state") in ("starting", "qr", "paired", "syncing", "failed"):
		out["linking"] = state["state"]
		out["error"] = state.get("error")
		out["parts"] = state.get("parts")
		if state.get("qr"):
			import segno

			out["qr"] = segno.make(state["qr"], error="l").svg_data_uri(scale=5, border=2)
	return out


@frappe.whitelist(methods=["POST"])
def poster_link():
	_guard(manager=True)
	linked._set_linking("starting")
	frappe.enqueue("techniti_connect.whatsapp.linked.link_job", queue="long", timeout=900,
				   job_id=f"tc-linked-link-{frappe.local.site}", deduplicate=True)
	return poster()


@frappe.whitelist(methods=["POST"])
def poster_refresh():
	_guard(manager=True)
	frappe.enqueue("techniti_connect.whatsapp.linked.check_job", queue="long", timeout=300,
				   job_id=f"tc-linked-check-{frappe.local.site}", deduplicate=True)
	return {"queued": True}


@frappe.whitelist(methods=["POST"])
def poster_unlink():
	_guard(manager=True)
	frappe.enqueue("techniti_connect.whatsapp.linked.unlink_job", queue="long", timeout=300,
				   job_id=f"tc-linked-unlink-{frappe.local.site}", deduplicate=True)
	return {"queued": True}


@frappe.whitelist()
def poster_groups():
	_guard(manager=True)
	return json.loads(frappe.db.get_single_value("Group Posting Setting", "groups_json") or "[]")


@frappe.whitelist(methods=["POST"])
def mark_shared(check):
	_guard()
	share_check.shared(check)
	return frappe.db.get_value("Share Check", check, "status")


# --------------------------------------------------------------------------- inbox

def _recent_inbound(limit):
	rows = frappe.db.sql(
		"""select m.phone, m.text, m.message_type, m.party_label, m.contact_name, m.sent_or_received_at as at
		from `tabWhatsApp Message` m
		where m.direction = 'In' order by m.sent_or_received_at desc limit %(l)s""", {"l": limit}, as_dict=True)
	for r in rows:
		r["name"] = r.party_label or r.contact_name or f"+{r.phone}"
	return rows


def _unanswered_phones():
	"""Numbers whose latest message in the last 7 days came from them."""
	return frappe.db.sql_list(
		"""select m.phone from `tabWhatsApp Message` m
		join (select phone, max(creation) as c from `tabWhatsApp Message` where creation > %(since)s group by phone) last
		  on last.phone = m.phone and last.c = m.creation
		where m.direction = 'In'""", {"since": add_days(now_datetime(), -7)})


@frappe.whitelist()
def conversations(search=None, only_unanswered=0):
	_guard()
	cond, vals = "", {}
	if search:
		cond = "and (m.phone like %(s)s or m.party_label like %(s)s or m.contact_name like %(s)s)"
		vals["s"] = f"%{search.strip()}%"
	rows = frappe.db.sql(
		f"""select m.phone, m.direction, m.text, m.message_type, m.template_name, m.party_doctype, m.party_name,
			m.party_label, m.contact_name, m.link_note, coalesce(m.sent_or_received_at, m.creation) as at
		from `tabWhatsApp Message` m
		join (select phone, max(creation) as c from `tabWhatsApp Message` where ifnull(phone, '') != '' group by phone) last
		  on last.phone = m.phone and last.c = m.creation
		where 1=1 {cond}
		order by m.creation desc limit 100""", vals, as_dict=True)
	unanswered = set(_unanswered_phones())
	since = add_to_date(now_datetime(), hours=-24)
	last_in = dict(frappe.db.sql("""select phone, max(sent_or_received_at) from `tabWhatsApp Message`
		where direction='In' group by phone"""))
	out = []
	for r in rows:
		r["name"] = r.party_label or r.contact_name or f"+{r.phone}"
		r["unanswered"] = r.phone in unanswered
		r["window_open"] = bool(last_in.get(r.phone) and get_datetime(last_in[r.phone]) > since)
		if frappe.utils.cint(only_unanswered) and not r["unanswered"]:
			continue
		out.append(r)
	return out


@frappe.whitelist()
def thread(phone):
	_guard()
	number = normalize_phone(phone)
	key = phone_key(number)
	msgs = frappe.db.sql(
		"""select name, direction, status, message_type, text, template_name, media_url, error, button_id,
			coalesce(sent_or_received_at, creation) as at
		from `tabWhatsApp Message` where phone like %(k)s
		order by coalesce(sent_or_received_at, creation) desc limit 80""", {"k": f"%{key}"}, as_dict=True)
	msgs.reverse()
	head = frappe.db.get_value("WhatsApp Message", {"phone": ["like", f"%{key}"], "party_name": ["is", "set"]},
							   ["party_doctype", "party_name", "party_label"], as_dict=True) or {}
	last_in = next((m.at for m in reversed(msgs) if m.direction == "In"), None)
	window_open = bool(last_in and get_datetime(last_in) > add_to_date(now_datetime(), hours=-24))
	return {
		"phone": number,
		"messages": msgs,
		"party": head,
		"facts": _facts(head),
		"window_open": window_open,
		"window_closes": add_to_date(last_in, hours=24) if window_open else None,
	}


def _facts(head):
	"""A few safe facts about the linked donor (never ID numbers or addresses)."""
	if not head or head.get("party_doctype") != "Donor" or not frappe.has_permission("Donor", "read", doc=head.get("party_name")):
		return []
	meta = frappe.get_meta("Donor")
	wanted = [("status", "Status"), ("donor_category", "Category"), ("donor_status", "Recency")]
	fields = [f for f, _label in wanted if meta.has_field(f)]
	vals = frappe.db.get_value("Donor", head["party_name"], fields, as_dict=True) if fields else {}
	facts = [{"k": label, "v": vals.get(f)} for f, label in wanted if vals and vals.get(f)]
	if frappe.db.exists("DocType", "Donation") and frappe.get_meta("Donation").has_field("donor"):
		row = frappe.db.sql("select count(*), sum(amount), max(donation_date) from `tabDonation` where donor=%s",
							head["party_name"])
		if row and row[0][0]:
			facts.append({"k": "Donations", "v": f"{row[0][0]} · ₹{frappe.utils.fmt_money(row[0][1] or 0, precision=0)}"})
			facts.append({"k": "Last donation", "v": frappe.utils.formatdate(row[0][2])})
	return facts


@frappe.whitelist(methods=["POST"])
def send(phone, text):
	_guard()
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Type a message first."))
	if not outbox.is_window_open(phone):
		frappe.throw(_("More than 24 hours since their last message. Only an approved template can be sent now."))
	msg = outbox.send(phone, "text", text=text[:4000], hold_if_closed=False)
	return {"status": msg.status, "error": msg.error}


def _initials(name):
	parts = [p for p in (name or "").split() if p]
	return ("".join(p[0] for p in parts[:2]) or "?").upper()
