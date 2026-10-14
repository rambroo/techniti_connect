"""External sources for automatic content: Pexels (free-licence photos/videos) and YouTube (links)."""

import random

import frappe
import requests

TIMEOUT = 30
MAX_VIDEO_BYTES = 16 * 1024 * 1024  # WhatsApp video limit
PEXELS = "https://api.pexels.com"
YOUTUBE = "https://www.googleapis.com/youtube/v3/search"


def _key(field):
	try:
		return frappe.get_cached_doc("WhatsApp Setting").get_password(field, raise_exception=False)
	except Exception:
		return None


def pexels_key():
	return _key("pexels_api_key")


def youtube_key():
	return _key("youtube_api_key")


def used_external_ids():
	return set(frappe.get_all("Group Content", filters={"external_id": ["is", "set"]}, pluck="external_id"))


# --------------------------------------------------------------------------- Pexels

def pexels_photo_bytes(query):
	"""A background photo for a quote card (repeats are fine: the text on it is always new)."""
	key = pexels_key()
	if not key:
		return None
	try:
		r = requests.get(f"{PEXELS}/v1/search", params={"query": query, "orientation": "square", "per_page": 40,
							"page": random.randint(1, 3)}, headers={"Authorization": key}, timeout=TIMEOUT)
		photos = r.json().get("photos") or []
		if not photos:
			return None
		photo = random.choice(photos)
		img = requests.get(photo["src"].get("large") or photo["src"]["original"], timeout=TIMEOUT)
		return img.content if img.ok else None
	except Exception:
		frappe.log_error(title="Pexels photo failed", message=frappe.get_traceback())
		return None


def pexels_video(query, orientation="landscape", max_seconds=90):
	"""Find an unused clip, download a WhatsApp-sized MP4. Returns dict or None."""
	key = pexels_key()
	if not key:
		return None
	used = used_external_ids()
	try:
		for page in random.sample(range(1, 6), 3):
			r = requests.get(f"{PEXELS}/videos/search", params={"query": query, "orientation": orientation,
								"size": "medium", "per_page": 40, "page": page}, headers={"Authorization": key}, timeout=TIMEOUT)
			videos = [v for v in (r.json().get("videos") or []) if (v.get("duration") or 0) <= max_seconds]
			random.shuffle(videos)
			for v in videos:
				ext_id = f"pexels-video-{v['id']}"
				if ext_id in used:
					continue
				content = _download_smallest_ok(v.get("video_files") or [], orientation)
				if content:
					return {"external_id": ext_id, "content": content, "page_url": v.get("url"),
							"credit": (v.get("user") or {}).get("name"), "duration": v.get("duration")}
	except Exception:
		frappe.log_error(title="Pexels video failed", message=frappe.get_traceback())
	return None


def _download_smallest_ok(files, orientation):
	"""Prefer ~720p MP4; never more than 16 MB."""
	def short_side(f):
		return min(f.get("width") or 9999, f.get("height") or 9999)

	mp4 = [f for f in files if (f.get("file_type") or "").endswith("mp4") and f.get("link")]
	mp4.sort(key=lambda f: abs(short_side(f) - 720))
	for f in mp4[:4]:
		try:
			with requests.get(f["link"], stream=True, timeout=60) as resp:
				if not resp.ok:
					continue
				size = int(resp.headers.get("Content-Length") or 0)
				if size and size > MAX_VIDEO_BYTES:
					continue
				buf = bytearray()
				for chunk in resp.iter_content(1024 * 256):
					buf.extend(chunk)
					if len(buf) > MAX_VIDEO_BYTES:
						buf = None
						break
				if buf:
					return bytes(buf)
		except Exception:
			continue
	return None


# --------------------------------------------------------------------------- YouTube

def youtube_link(query, shorts=False):
	key = youtube_key()
	if not key:
		return None
	used = used_external_ids()
	try:
		r = requests.get(YOUTUBE, params={"part": "snippet", "q": f"{query} #shorts" if shorts else query, "type": "video",
						 "videoDuration": "short", "safeSearch": "strict", "maxResults": 25, "key": key}, timeout=TIMEOUT)
		items = r.json().get("items") or []
		random.shuffle(items)
		for it in items:
			vid = (it.get("id") or {}).get("videoId")
			if not vid or f"youtube-{vid}" in used:
				continue
			url = f"https://www.youtube.com/shorts/{vid}" if shorts else f"https://www.youtube.com/watch?v={vid}"
			snip = it.get("snippet") or {}
			return {"external_id": f"youtube-{vid}", "link": url, "title": snip.get("title"),
					"credit": snip.get("channelTitle")}
	except Exception:
		frappe.log_error(title="YouTube search failed", message=frappe.get_traceback())
	return None
