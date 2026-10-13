import re

import frappe


def default_country_code():
	try:
		cc = frappe.db.get_single_value("WhatsApp Setting", "default_country_code")
	except Exception:
		cc = None
	return re.sub(r"\D", "", str(cc or "91")) or "91"


def normalize_phone(raw, country_code=None):
	"""Return the number as digits with country code (no "+"), or None if it can't be a WhatsApp number.

	Decides by length, not by prefix: a 10-digit mobile such as 9123456789 starts with
	"91" but still needs the country code added.
	"""
	if not raw:
		return None
	s = str(raw).strip()
	has_plus = s.startswith("+") or s.startswith("00")
	digits = re.sub(r"\D", "", s)
	if s.startswith("00"):
		digits = digits[2:]
	if not digits:
		return None

	cc = re.sub(r"\D", "", str(country_code)) if country_code else default_country_code()

	if has_plus:
		return digits if 8 <= len(digits) <= 15 else None
	if len(digits) == 10:
		return cc + digits
	if len(digits) == 11 and digits.startswith("0"):
		return cc + digits[1:]
	if len(digits) == len(cc) + 10 and digits.startswith(cc):
		return digits
	if 11 <= len(digits) <= 15:
		return digits
	return None


def phone_key(raw):
	"""Last 10 digits — used to match a WhatsApp sender against numbers stored in any format."""
	digits = re.sub(r"\D", "", str(raw or ""))
	return digits[-10:] if len(digits) >= 10 else None


def split_phones(text):
	"""Comma/newline separated numbers → set of phone keys."""
	keys = set()
	for part in re.split(r"[,\n;/]", text or ""):
		key = phone_key(part)
		if key:
			keys.add(key)
	return keys
