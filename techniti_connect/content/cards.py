"""Render quote cards (1080x1080 JPEG) for automatic photo content."""

import io
import os
import random

import frappe

SIZE = 1080
MARGIN = 110
BRAND = "We Can We Will Foundation"

PALETTES = {
	"Faith (Mixed)": [((23, 37, 84), (88, 28, 135)), ((12, 74, 110), (21, 128, 61)), ((120, 53, 15), (190, 18, 60)),
					  ((15, 23, 42), (30, 64, 175)), ((88, 28, 135), (190, 24, 93)), ((6, 78, 59), (2, 132, 199))],
	"Students": [((30, 64, 175), (14, 165, 233)), ((21, 128, 61), (101, 163, 13)), ((194, 65, 12), (234, 179, 8)),
				 ((79, 70, 229), (147, 51, 234))],
	"General Motivation": [((190, 18, 60), (234, 88, 12)), ((13, 148, 136), (37, 99, 235))],
}


def _font(name, size):
	from PIL import ImageFont

	path = frappe.get_app_path("techniti_connect", "public", "fonts", name)
	try:
		return ImageFont.truetype(path, size)
	except OSError:
		return ImageFont.load_default()


def _gradient(top, bottom):
	from PIL import Image

	img = Image.new("RGB", (SIZE, SIZE), top)
	px = img.load()
	for y in range(SIZE):
		t = y / (SIZE - 1)
		row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
		for x in range(SIZE):
			px[x, y] = row
	return img


def _photo_background(image_bytes):
	from PIL import Image, ImageEnhance, ImageFilter

	img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
	w, h = img.size
	side = min(w, h)
	img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2)).resize((SIZE, SIZE))
	img = img.filter(ImageFilter.GaussianBlur(2))
	return ImageEnhance.Brightness(img).enhance(0.42)


def _wrap(draw, text, font, width):
	words, lines, line = text.split(), [], ""
	for word in words:
		trial = f"{line} {word}".strip()
		if draw.textlength(trial, font=font) <= width:
			line = trial
		else:
			if line:
				lines.append(line)
			line = word
	if line:
		lines.append(line)
	return lines


def render(text, source="", theme="Faith (Mixed)", background_bytes=None, seed=None):
	"""Return JPEG bytes."""
	from PIL import ImageDraw

	rnd = random.Random(seed or text)
	if background_bytes:
		try:
			img = _photo_background(background_bytes)
		except Exception:
			img = _gradient(*rnd.choice(PALETTES.get(theme) or PALETTES["Faith (Mixed)"]))
	else:
		img = _gradient(*rnd.choice(PALETTES.get(theme) or PALETTES["Faith (Mixed)"]))
	draw = ImageDraw.Draw(img)
	width = SIZE - 2 * MARGIN

	# largest font size that fits in ~60% of the height
	for size in range(88, 34, -4):
		font = _font("Poppins-SemiBold.ttf", size)
		lines = _wrap(draw, text, font, width)
		line_h = int(size * 1.32)
		if len(lines) * line_h <= SIZE * 0.6:
			break
	block_h = len(lines) * line_h
	y = (SIZE - block_h) // 2 - (40 if source else 0)

	quote_font = _font("Poppins-SemiBold.ttf", 150)
	draw.text((MARGIN - 10, y - 150), "“", font=quote_font, fill=(255, 255, 255, 120))
	for line in lines:
		w = draw.textlength(line, font=font)
		draw.text(((SIZE - w) / 2, y), line, font=font, fill=(255, 255, 255))
		y += line_h

	if source:
		src_font = _font("Poppins-Italic.ttf", 40)
		label = f"— {source}"
		w = draw.textlength(label, font=src_font)
		draw.text(((SIZE - w) / 2, y + 30), label, font=src_font, fill=(235, 235, 235))

	brand_font = _font("Poppins-Regular.ttf", 30)
	w = draw.textlength(BRAND, font=brand_font)
	draw.line([(SIZE / 2 - 60, SIZE - 120), (SIZE / 2 + 60, SIZE - 120)], fill=(255, 255, 255), width=2)
	draw.text(((SIZE - w) / 2, SIZE - 95), BRAND, font=brand_font, fill=(255, 255, 255))

	out = io.BytesIO()
	img.save(out, format="JPEG", quality=88, optimize=True)
	return out.getvalue()


def font_files_present():
	return all(os.path.exists(frappe.get_app_path("techniti_connect", "public", "fonts", f))
			   for f in ("Poppins-SemiBold.ttf", "Poppins-Regular.ttf", "Poppins-Italic.ttf"))
