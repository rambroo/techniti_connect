"""Keep each auto-content group stocked: make quote cards, fetch Pexels clips and YouTube links.

Everything created here is still only a *proposal*: it goes through the normal approval
(Approve / Swap / Skip) before anything reaches a group.
"""

import hashlib
import html
import random

import frappe
from frappe.utils.file_manager import save_file

from techniti_connect.content import cards, sources
from techniti_connect.content.lines import SEARCH_TERMS, THEMES, YOUTUBE_QUERIES

# rotation per content type: tried in sequence, skipping sources without an API key
ROTATION = {
	"Video": ["pexels_landscape", "youtube_video"],
	"Reel": ["pexels_portrait", "youtube_short"],
}


def ensure_stock(group, needed):
	"""needed: {content_type: count}. Creates items until the group has that many unused ones."""
	from techniti_connect.groups import pick_content

	created = []
	for ctype, qty in needed.items():
		have, taken = 0, []
		while have < qty:
			c = pick_content(group, ctype, exclude=taken)
			if not c:
				break
			taken.append(c.name)
			have += 1
		for _i in range(qty - have):
			doc = create_one(group, ctype)
			if not doc:
				break
			created.append(doc.name)
	return created


def create_one(group, ctype):
	theme = group.get("content_theme") or "Faith (Mixed)"
	try:
		if ctype == "Photo":
			return _make_card(group, theme)
		order = ROTATION.get(ctype, [])
		start = frappe.db.count("Group Content", {"content_type": ctype, "auto_source": ["is", "set"]}) % max(len(order), 1)
		for src in order[start:] + order[:start]:
			doc = _from_source(group, theme, ctype, src)
			if doc:
				return doc
	except Exception:
		frappe.log_error(title=f"Auto content failed: {group.name} {ctype}", message=frappe.get_traceback())
	return None


# --------------------------------------------------------------------------- lines

def _line_id(text):
	return "line-" + hashlib.sha1(text.encode()).hexdigest()[:16]


def next_line(theme):
	"""A line never used before (on a card or as a caption). Falls back to the least recent if all used."""
	used = set(frappe.get_all("Group Content", filters={"line_id": ["is", "set"]}, pluck="line_id"))
	pool = THEMES.get(theme) or THEMES["Faith (Mixed)"]
	fresh = [ln for ln in pool if _line_id(ln[0]) not in used]
	return random.choice(fresh or pool)


def _caption(text, source):
	return f"{text}\n— {source}" if source else text


# --------------------------------------------------------------------------- makers

def _make_card(group, theme):
	text, source = next_line(theme)
	bg = sources.pexels_photo_bytes(random.choice(SEARCH_TERMS.get(theme) or ["sunrise"]))
	jpeg = cards.render(text, source, theme=theme, background_bytes=bg)
	line_id = _line_id(text)
	fname = f"card-{line_id[5:]}.jpg"
	f = save_file(fname, jpeg, "WhatsApp Group", group.name, is_private=0)
	return _insert(group, "Photo", title=f"Card: {text[:60]}", file=f.file_url, caption=_caption(text, source),
				   auto_source="Quote Card", line_id=line_id, external_id=None,
				   source_credit="Generated card" + (" (background: Pexels)" if bg else ""))


def _from_source(group, theme, ctype, src):
	terms = SEARCH_TERMS.get(theme) or ["sunrise"]
	text, source = next_line(theme)
	if src in ("pexels_landscape", "pexels_portrait"):
		clip = sources.pexels_video(random.choice(terms), orientation="landscape" if src == "pexels_landscape" else "portrait",
									max_seconds=90 if ctype == "Video" else 60)
		if not clip:
			return None
		f = save_file(f"{clip['external_id']}.mp4", clip["content"], "WhatsApp Group", group.name, is_private=0)
		return _insert(group, ctype, title=f"{ctype}: {text[:50]}", file=f.file_url, caption=_caption(text, source),
					   auto_source="Pexels", line_id=_line_id(text), external_id=clip["external_id"],
					   source_credit=f"Video by {clip.get('credit') or 'Pexels'} on Pexels", link=clip.get("page_url"),
					   keep_link_out_of_caption=True)
	if src in ("youtube_video", "youtube_short"):
		queries = YOUTUBE_QUERIES.get(theme) or ["motivation"]
		yt = sources.youtube_link(random.choice(queries), shorts=src == "youtube_short")
		if not yt:
			return None
		return _insert(group, ctype, title=f"{ctype}: {html.unescape(yt.get('title') or text)[:60]}", link=yt["link"],
					   caption=_caption(text, source), auto_source="YouTube", line_id=_line_id(text),
					   external_id=yt["external_id"], source_credit=f"YouTube: {html.unescape(yt.get('credit') or '')}")
	return None


def _insert(group, ctype, title, caption, auto_source, line_id, external_id, source_credit, file=None, link=None,
			keep_link_out_of_caption=False):
	doc = frappe.get_doc({
		"doctype": "Group Content",
		"title": title,
		"content_type": ctype,
		"status": "Active",
		"file": file,
		"link": None if keep_link_out_of_caption else link,
		"caption": caption,
		"groups": [{"whatsapp_group": group.name}],
		"auto_source": auto_source,
		"line_id": line_id,
		"external_id": external_id,
		"source_credit": source_credit,
	})
	doc.insert(ignore_permissions=True)
	if file:
		attach_to_content(doc)
	return doc


def attach_to_content(doc):
	"""Generated files are saved against the WhatsApp Group first; attach them to the library item, so
	deleting a group never deletes images and clips the library still uses."""
	frappe.db.set_value("File", {"file_url": doc.file, "attached_to_doctype": "WhatsApp Group"},
						{"attached_to_doctype": "Group Content", "attached_to_name": doc.name, "attached_to_field": "file"})
