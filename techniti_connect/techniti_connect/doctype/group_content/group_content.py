# Copyright (c) 2026, Rohan Rambhiya and contributors
# For license information, please see license.txt

import hashlib
import io
import re
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

MAX_BYTES = {"Photo": 5 * 1024 * 1024, "Video": 16 * 1024 * 1024}
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_EXT = (".mp4", ".3gp")
SIMILAR_BITS = 6  # dHash distance at or below this = same picture (resized / re-saved)


class GroupContent(Document):
	def validate(self):
		if not self.file and not self.link:
			frappe.throw(_("Attach a file or paste a link"))
		if self.content_type == "Reel" and not self.link and not self.file:
			frappe.throw(_("A reel needs a link or a video file"))
		self.normalized_link = normalize_link(self.link) if self.link else None
		if self.file:
			self._check_file()
		else:
			self.file_hash = self.image_hash = None
			self.file_size = 0
		self._check_duplicates()

	def _check_file(self):
		path = self.file.lower().split("?")[0]
		if self.content_type == "Photo" and not path.endswith(IMAGE_EXT):
			frappe.throw(_("Photos must be JPG, PNG or WEBP"))
		if self.content_type in ("Video", "Reel") and not path.endswith(VIDEO_EXT):
			frappe.throw(_("Videos must be MP4 or 3GP"))
		if self.file.startswith("/private/"):
			frappe.throw(_("The file must be public, otherwise WhatsApp cannot download it. Re-upload it with 'Is Private' unticked."))

		content = _file_content(self.file)
		if content is None:
			return
		self.file_size = len(content)
		limit = MAX_BYTES.get("Photo" if self.content_type == "Photo" else "Video")
		if self.file_size > limit:
			frappe.throw(_("File is {0} MB. WhatsApp allows up to {1} MB for this type. Compress it or use a link.").format(
				round(self.file_size / 1048576, 1), limit // 1048576))
		self.file_hash = hashlib.sha256(content).hexdigest()
		self.image_hash = dhash(content) if self.content_type == "Photo" else None

	def _check_duplicates(self):
		others = {"name": ["!=", self.name or ""]}
		if self.file_hash:
			dup = frappe.db.get_value("Group Content", {**others, "file_hash": self.file_hash})
			if dup:
				frappe.throw(_("This exact file is already in the library: {0}").format(dup))
		if self.normalized_link:
			dup = frappe.db.get_value("Group Content", {**others, "normalized_link": self.normalized_link})
			if dup:
				frappe.throw(_("This link is already in the library: {0}").format(dup))
		if self.image_hash:
			for row in frappe.get_all("Group Content", filters={**others, "image_hash": ["is", "set"]},
									  fields=["name", "image_hash"]):
				if hamming(self.image_hash, row.image_hash) <= SIMILAR_BITS:
					frappe.throw(_("This photo looks the same as {0} (resized or re-saved copy)").format(row.name))


def _file_content(file_url):
	name = frappe.db.get_value("File", {"file_url": file_url})
	if not name:
		return None
	try:
		return frappe.get_doc("File", name).get_content()
	except Exception:
		return None


def dhash(content, size=8):
	"""64-bit difference hash: survives resizing and re-compression."""
	try:
		from PIL import Image

		img = Image.open(io.BytesIO(content)).convert("L").resize((size + 1, size))
	except Exception:
		return None
	px = list(img.getdata())
	bits = 0
	for row in range(size):
		for col in range(size):
			left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
			bits = (bits << 1) | (1 if left > right else 0)
	return f"{bits:016x}"


def hamming(a, b):
	try:
		return bin(int(a, 16) ^ int(b, 16)).count("1")
	except (TypeError, ValueError):
		return 64


def normalize_link(link):
	link = (link or "").strip()
	if not link:
		return None
	p = urlparse(link if "://" in link else "https://" + link)
	host = p.netloc.lower().removeprefix("www.").removeprefix("m.")
	path = p.path.rstrip("/")
	m = re.match(r"^/(?:[^/]+/)?(reel|reels|p|tv)/([^/]+)", path)
	if "instagram.com" in host and m:
		return f"instagram.com/reel/{m.group(2)}"
	if host in ("youtu.be",):
		return f"youtube.com/watch/{path.strip('/')}"
	if "youtube.com" in host:
		vid = dict(q.split("=", 1) for q in p.query.split("&") if "=" in q).get("v")
		if vid:
			return f"youtube.com/watch/{vid}"
		if path.startswith("/shorts/"):
			return f"youtube.com/watch/{path.split('/')[2]}"
	return f"{host}{path}"
