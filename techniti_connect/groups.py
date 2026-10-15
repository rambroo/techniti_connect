"""Weekly WhatsApp group posts: plan -> approve -> post -> Posted.

WhatsApp's official API cannot post into an existing group. Each group either has the approved post
delivered to its admin's WhatsApp ready to forward, with a "Posted" button to confirm (Forward via Admin),
or posted straight into the group by the separate linked group posting number (Post Directly).
"""

import datetime

import frappe
from frappe import _
from frappe.utils import add_days, formatdate, get_datetime, getdate, now_datetime, nowdate

from techniti_connect.whatsapp import outbox

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
USED_STATUSES = ("Approved", "Sent to Admin", "Posted")
REMIND_AFTER_HOURS = 3


# --------------------------------------------------------------------------- dates

def next_post_date(group, from_date=None):
	start = getdate(from_date or nowdate())
	target = WEEKDAYS.index(group.post_weekday)
	return start + datetime.timedelta(days=(target - start.weekday()) % 7)


def post_datetime(group, post_date):
	return get_datetime(f"{post_date} {group.post_time or '08:00:00'}")


# --------------------------------------------------------------------------- planning

def plan_upcoming():
	"""Daily: create proposals for each group's next post date once it is within plan_days_before."""
	for name in frappe.get_all("WhatsApp Group", filters={"enabled": 1}, pluck="name"):
		try:
			plan_group(frappe.get_doc("WhatsApp Group", name))
		except Exception:
			frappe.log_error(title=f"Group plan failed: {name}", message=frappe.get_traceback())


def plan_group(group, post_date=None, force=False):
	post_date = getdate(post_date) if post_date else next_post_date(group)
	if not force and (post_date - getdate(nowdate())).days > (group.plan_days_before or 0):
		return []
	if post_datetime(group, post_date) <= now_datetime():
		return []
	existing = frappe.get_all("Group Post", filters={"whatsapp_group": group.name, "post_date": post_date},
							 fields=["name", "status", "content"])
	if existing and (not force or any(p.content or p.status not in ("Proposed", "Skipped") for p in existing)):
		return []
	# "Plan next post" redoes a date whose slots all came out empty, now that there may be content
	if existing:
		frappe.db.delete("Group Post", {"name": ["in", [p.name for p in existing]]})

	if group.get("auto_content"):
		from techniti_connect.content import autofill

		needed = {}
		for slot in group.slots:
			needed[slot.content_type] = needed.get(slot.content_type, 0) + (slot.qty or 1)
		autofill.ensure_stock(group, needed)

	created, taken = [], []
	for slot in group.slots:
		for _i in range(slot.qty or 1):
			content = pick_content(group, slot.content_type, exclude=taken)
			post = frappe.get_doc({
				"doctype": "Group Post",
				"whatsapp_group": group.name,
				"post_date": post_date,
				"content_type": slot.content_type,
				"content": content.name if content else None,
				"caption": content.caption if content else None,
				"status": "Proposed",
				"error": None if content else _empty_reason(group, slot.content_type),
			}).insert(ignore_permissions=True)
			if content:
				taken.append(content.name)
			created.append(post)

	frappe.db.commit()
	notify_approver(group, post_date, created)
	return [p.name for p in created]


def _empty_reason(group, content_type):
	if group.get("auto_content") and content_type in ("Video", "Reel"):
		from techniti_connect.content import sources

		if not (sources.pexels_key() or sources.youtube_key()):
			return (f"No {content_type} could be made automatically: add a Pexels or YouTube API key in "
					"WhatsApp Setting, or upload one in Group Content")
	return f"No unused {content_type} left for this group - add more content"


def pick_content(group, content_type, exclude=None):
	"""Least-used Active item of this type allowed in this group and not already used there."""
	exclude = list(exclude or [])
	used = _used_in_group(group)
	allowed = frappe.db.sql(
		"""
		select gc.name, gc.title, gc.caption, gc.file, gc.link, gc.content_type
		from `tabGroup Content` gc
		where gc.status = 'Active' and gc.content_type = %(ctype)s
		  and (not exists (select 1 from `tabGroup Content Group` g where g.parent = gc.name)
		       or exists (select 1 from `tabGroup Content Group` g where g.parent = gc.name and g.whatsapp_group = %(grp)s))
		order by ifnull(gc.times_used, 0) asc, ifnull(gc.last_used_on, '1900-01-01') asc, rand()
		""",
		{"ctype": content_type, "grp": group.name},
		as_dict=True,
	)
	for row in allowed:
		if row.name not in exclude and row.name not in used:
			return row
	return None


def _used_in_group(group):
	filters = {"whatsapp_group": group.name, "status": ["in", USED_STATUSES], "content": ["is", "set"]}
	if group.repeat_after_days:
		filters["post_date"] = [">=", add_days(nowdate(), -group.repeat_after_days)]
	used = set(frappe.get_all("Group Post", filters=filters, pluck="content"))
	# items already proposed for an upcoming date are not offered again for another date
	used.update(frappe.get_all("Group Post", filters={"whatsapp_group": group.name, "status": "Proposed",
							   "content": ["is", "set"], "post_date": [">=", nowdate()]}, pluck="content"))
	return used


# --------------------------------------------------------------------------- approval

def notify_approver(group, post_date, posts):
	if group.approver_user:
		_desk_alert(group.approver_user, _("Approve {0} post(s) for {1} on {2}").format(
			len(posts), group.name, formatdate(post_date)), "Group Post", posts[0].name if posts else None)
	if not group.approver_phone:
		return
	intro = (f"Posts for *{group.name}* on {getdate(post_date).strftime('%A, %d %b')}.\n"
			 f"Approve each one, Swap for another, or Skip.")
	outbox.send(group.approver_phone, "text", text=intro, contact_name=group.approver_name,
				nudge_text=f"{len(posts)} post(s) for {group.name} need your approval", reference=("WhatsApp Group", group.name))
	for i, post in enumerate(posts, 1):
		send_preview(group, post, i, len(posts))


def send_preview(group, post, index=None, total=None):
	content = frappe.get_doc("Group Content", post.content) if post.content else None
	label = f"{index}/{total} " if index else ""
	if not content:
		outbox.send(group.approver_phone, "buttons", contact_name=group.approver_name, reference=("Group Post", post.name),
					text=f"{label}{post.content_type} for {group.name}: {post.error or 'no unused content left'}. "
					"Then Swap to fill this slot, or Skip it.",
					buttons=[[f"gp:swap:{post.name}", "Swap"], [f"gp:skip:{post.name}", "Skip"]])
		return
	_send_content(group.approver_phone, group.approver_name, content, post.caption, ("Group Post", post.name))
	outbox.send(group.approver_phone, "buttons", contact_name=group.approver_name, reference=("Group Post", post.name),
				text=f"{label}{post.content_type} for {group.name}: {content.title}",
				buttons=[[f"gp:approve:{post.name}", "Approve"], [f"gp:swap:{post.name}", "Swap"],
						 [f"gp:skip:{post.name}", "Skip"]])


def _send_content(phone, name, content, caption, reference):
	if content.file:
		media_type = "image" if content.content_type == "Photo" else "video"
		return outbox.send(phone, "media", media_type=media_type, media_url=outbox.public_url(content.file),
						   caption=_with_link(caption, content.link), contact_name=name, reference=reference)
	return outbox.send(phone, "text", text=_with_link(caption, content.link) or content.title,
					   contact_name=name, reference=reference)


def _with_link(caption, link):
	parts = [p for p in ((caption or "").strip(), (link or "").strip()) if p]
	return "\n\n".join(parts) or None


@frappe.whitelist()
def approve(post_name):
	_check_role()
	return _decide(post_name, "Approved", frappe.session.user)


@frappe.whitelist()
def skip(post_name):
	_check_role()
	return _decide(post_name, "Skipped", frappe.session.user)


@frappe.whitelist()
def swap(post_name):
	_check_role()
	return _swap(post_name, frappe.session.user, notify=False)


def _check_role():
	if not frappe.has_permission("Group Post", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _decide(post_name, status, by):
	post = frappe.get_doc("Group Post", post_name)
	if post.status not in ("Proposed", "Approved", "Skipped"):
		return post.status
	if status == "Approved" and not post.content:
		frappe.throw(_("Nothing to approve: no content was picked. Swap or add content first."))
	post.db_set({"status": status, "approved_by": by, "approved_on": now_datetime()})
	if status == "Skipped":
		_retire_if_auto(post.content)
	return status


def _retire_if_auto(content_name):
	"""Automatically created items you swap or skip are not offered again; manual uploads stay."""
	if content_name and frappe.db.get_value("Group Content", content_name, "auto_source"):
		frappe.db.set_value("Group Content", content_name, "status", "Retired")


def _swap(post_name, by, notify=True):
	post = frappe.get_doc("Group Post", post_name)
	if post.status not in ("Proposed", "Approved"):
		return post.status
	group = frappe.get_doc("WhatsApp Group", post.whatsapp_group)
	siblings = frappe.get_all("Group Post", filters={"whatsapp_group": group.name, "post_date": post.post_date,
						  "name": ["!=", post.name]}, pluck="content")
	exclude = [post.content, *siblings]
	new = pick_content(group, post.content_type, exclude=exclude)
	if not new and group.get("auto_content"):
		from techniti_connect.content import autofill

		if autofill.create_one(group, post.content_type):
			new = pick_content(group, post.content_type, exclude=exclude)
	if new:
		_retire_if_auto(post.content)
	if not new:
		if notify and group.approver_phone:
			outbox.send(group.approver_phone, "text", contact_name=group.approver_name, reference=("Group Post", post.name),
						text=f"No other {post.content_type} available for {group.name}. "
						+ (_empty_reason(group, post.content_type) if not post.content else "Approve or Skip the current one."))
		return "No alternative"
	post.db_set({"content": new.name, "content_title": new.title, "caption": new.caption, "status": "Proposed",
				 "error": None, "swap_count": (post.swap_count or 0) + 1, "approved_by": by, "approved_on": now_datetime()})
	if notify and group.approver_phone:
		send_preview(group, frappe.get_doc("Group Post", post.name))
	return "Swapped"


# --------------------------------------------------------------------------- delivery

def dispatch_due():
	"""Every few minutes: post (or send to the admin) approved posts at post time; flag unapproved ones."""
	now = now_datetime()
	rows = frappe.get_all("Group Post", filters={"status": ["in", ["Proposed", "Approved"]], "post_date": ["<=", nowdate()]},
						  fields=["name", "whatsapp_group", "post_date", "status"], order_by="post_date asc, name asc")
	direct = {}
	for row in rows:
		group = frappe.get_cached_doc("WhatsApp Group", row.whatsapp_group)
		if post_datetime(group, row.post_date) > now:
			continue
		try:
			if _off_schedule(group, row.post_date):
				frappe.db.set_value("Group Post", row.name, {"status": "Skipped",
									"error": f"Post day changed to {group.post_weekday}"})
			elif row.status == "Approved" and group.get("posting_method") == "Post Directly":
				direct.setdefault(group.name, []).append(row.name)
			elif row.status == "Approved":
				send_to_admin(row.name)
			else:
				frappe.db.set_value("Group Post", row.name, {"status": "Missed", "error": "Not approved before post time"})
				if group.approver_phone:
					outbox.send(group.approver_phone, "text", contact_name=group.approver_name, reference=("Group Post", row.name),
								text=f"Post {row.name} for {group.name} was not approved in time and was not sent.")
		except Exception:
			frappe.log_error(title=f"Group post dispatch failed: {row.name}", message=frappe.get_traceback())
	frappe.db.commit()
	for group_name, names in direct.items():
		frappe.enqueue("techniti_connect.groups.post_direct", queue="long", timeout=900, post_names=names,
					   job_id=f"tc-direct-{frappe.local.site}-{group_name}", deduplicate=True)


def send_to_admin(post_name):
	post = frappe.get_doc("Group Post", post_name)
	group = frappe.get_doc("WhatsApp Group", post.whatsapp_group)
	content = frappe.get_doc("Group Content", post.content)
	ref = ("Group Post", post.name)
	outbox.send(group.admin_phone, "text", contact_name=group.admin_name, reference=ref,
				nudge_text=f"today's post for {group.name} is ready to forward",
				text=f"Today's {post.content_type.lower()} for *{group.name}*. Please forward the next message into the group.")
	sent = _send_content(group.admin_phone, group.admin_name, content, post.caption, ref)
	outbox.send(group.admin_phone, "buttons", contact_name=group.admin_name, reference=ref,
				text=f"Once you have posted it in {group.name}, confirm here.", buttons=[[f"gp:posted:{post.name}", "Posted"]])
	post.db_set({"status": "Sent to Admin" if sent.status in ("Sent", "Held") else "Failed",
				 "sent_to_admin_on": now_datetime(), "error": sent.error})


def post_direct(post_names):
	"""Background job: post approved posts straight into the group from the linked posting number.
	Anything that cannot be posted goes to the group admin to forward, and the approver is told why."""
	from techniti_connect.whatsapp import linked

	posts = [frappe.get_doc("Group Post", n) for n in post_names]
	posts = [p for p in posts if p.status == "Approved"]
	if not posts:
		return
	group = frappe.get_doc("WhatsApp Group", posts[0].whatsapp_group)
	problems = [None] * len(posts)
	if not group.group_chat_id:
		problems = ["no WhatsApp group is chosen for it"] * len(posts)
	elif not linked.is_linked():
		problems = ["the group posting number is not linked"] * len(posts)
	else:
		try:
			problems = linked.post_many(group.group_chat_id, [_direct_item(p) for p in posts])
		except linked.LinkedError as e:
			problems = [str(e)] * len(posts)
		except Exception as e:
			frappe.log_error(title=f"Direct post failed: {group.name}", message=frappe.get_traceback())
			problems = [f"posting failed ({e.__class__.__name__})"] * len(posts)

	failed = []
	for post, problem in zip(posts, problems):
		if not problem:
			mark_posted(post.name, "Group posting number")
			post.db_set("error", None)
			continue
		failed.append(f"{post.content_type}: {problem}")
		if group.admin_phone:
			send_to_admin(post.name)
		else:
			post.db_set({"status": "Failed", "error": problem[:500]})
	if failed and group.approver_phone:
		outbox.send(group.approver_phone, "text", contact_name=group.approver_name, reference=("WhatsApp Group", group.name),
					text=f"Could not post directly into {group.name}:\n" + "\n".join(failed) + "\n"
					+ (f"Sent to {group.admin_name or 'the admin'} to forward instead. " if group.admin_phone else "")
					+ "Check the posting number in /connect > Groups.")
	frappe.db.commit()


def _direct_item(post):
	content = frappe.get_doc("Group Content", post.content)
	caption = _with_link(post.caption, content.link)
	if content.file:
		path = frappe.get_doc("File", {"file_url": content.file}).get_full_path()
		return {"kind": "image" if content.content_type == "Photo" else "video", "path": path, "caption": caption}
	return {"kind": "text", "text": caption or content.title}


def _off_schedule(group, post_date):
	return bool(group.post_weekday) and getdate(post_date).weekday() != WEEKDAYS.index(group.post_weekday)


def cancel_off_schedule(group):
	"""When a group's post day changes, pending posts planned for the old day are skipped."""
	count = 0
	for row in frappe.get_all("Group Post", filters={"whatsapp_group": group.name, "status": ["in", ["Proposed", "Approved"]],
							  "post_date": [">=", nowdate()]}, fields=["name", "post_date"]):
		if _off_schedule(group, row.post_date):
			frappe.db.set_value("Group Post", row.name, {"status": "Skipped",
								"error": f"Post day changed to {group.post_weekday}"})
			count += 1
	return count


def remind_unposted():
	cutoff = now_datetime() - datetime.timedelta(hours=REMIND_AFTER_HOURS)
	for row in frappe.get_all("Group Post", filters={"status": "Sent to Admin", "reminder_sent": 0,
							  "sent_to_admin_on": ["<", cutoff]}, fields=["name", "whatsapp_group"]):
		group = frappe.get_cached_doc("WhatsApp Group", row.whatsapp_group)
		outbox.send(group.admin_phone, "buttons", contact_name=group.admin_name, reference=("Group Post", row.name),
					text=f"Reminder: today's post for {group.name} is not marked as posted yet.",
					buttons=[[f"gp:posted:{row.name}", "Posted"]])
		frappe.db.set_value("Group Post", row.name, "reminder_sent", 1)


def close_stale():
	"""Daily: posts sent to the admin but never confirmed by the next day become Missed."""
	for name in frappe.get_all("Group Post", filters={"status": "Sent to Admin", "post_date": ["<", add_days(nowdate(), -1)]},
							   pluck="name"):
		frappe.db.set_value("Group Post", name, {"status": "Missed", "error": "Admin did not confirm it was posted"})


def mark_posted(post_name, by):
	post = frappe.get_doc("Group Post", post_name)
	if post.status == "Posted":
		return
	post.db_set({"status": "Posted", "posted_on": now_datetime()})
	if post.content:
		used = frappe.db.get_value("Group Content", post.content, "times_used") or 0
		frappe.db.set_value("Group Content", post.content, {"times_used": used + 1, "last_used_on": nowdate()})


@frappe.whitelist()
def posted(post_name):
	_check_role()
	mark_posted(post_name, frappe.session.user)


@frappe.whitelist()
def plan_now(group_name, post_date=None):
	"""Desk button: create this week's proposals immediately."""
	if not frappe.has_permission("WhatsApp Group", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return plan_group(frappe.get_doc("WhatsApp Group", group_name), post_date=post_date, force=True)


# --------------------------------------------------------------------------- WhatsApp buttons

def handle_button(msg, action, post_name):
	"""Called by inbound routing for ids like gp:approve:GP-2026-00001."""
	if not frappe.db.exists("Group Post", post_name):
		return
	post = frappe.get_doc("Group Post", post_name)
	group = frappe.get_doc("WhatsApp Group", post.whatsapp_group)
	from techniti_connect.whatsapp.phone import phone_key

	sender = phone_key(msg.phone)
	is_approver = sender and sender == phone_key(group.approver_phone)
	is_admin = sender and sender == phone_key(group.admin_phone)
	who = msg.contact_name or msg.phone

	if action in ("approve", "skip", "swap") and is_approver:
		try:
			if action == "swap":
				result = _swap(post_name, who)
				if result != "Swapped":
					_reply(msg, f"{post_name}: {result}")
			else:
				result = _decide(post_name, "Approved" if action == "approve" else "Skipped", who)
				_reply(msg, f"{post_name}: {result}")
		except frappe.ValidationError as e:
			_reply(msg, f"{post_name}: {frappe.utils.strip_html(str(e))}")
	elif action == "posted" and (is_admin or is_approver):
		mark_posted(post_name, who)
		_reply(msg, f"Thanks! Marked as posted in {group.name}.")
	else:
		_reply(msg, "This button is not meant for your number.")


def _reply(msg, text):
	outbox.send(msg.phone, "text", text=text, contact_name=msg.contact_name, hold_if_closed=False)


def _desk_alert(user, subject, doctype=None, docname=None):
	try:
		frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": subject,
						"document_type": doctype, "document_name": docname, "from_user": "Administrator"}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Desk alert failed", message=frappe.get_traceback())
