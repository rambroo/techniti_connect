"""Find the record (Donor first, then Website Donor) that owns a WhatsApp number.

Matching is on the last 10 digits, so "+91-7045216675", "917045216675" and "07045216675" all match.
A number shared by several records (families) is not linked to any single one; the note lists them.
"""

import frappe

from techniti_connect.whatsapp.phone import phone_key

# (doctype, phone fields, label field) in priority order. Doctypes that don't exist on a site are skipped.
SOURCES = [
	("Donor", ["contact_number"], "name1"),
	("Website Donor", ["mobile"], "full_name"),
]
CACHE_SECONDS = 600


def resolve(phone):
	"""Return dict(party_doctype, party_name, party_label, link_note); empty values when nothing matches."""
	key = phone_key(phone)
	empty = {"party_doctype": None, "party_name": None, "party_label": None, "link_note": None}
	if not key:
		return empty
	cache_key = f"tc_party:{key}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached

	result = dict(empty)
	for doctype, fields, label_field in SOURCES:
		matches = find(doctype, fields, label_field, key)
		if len(matches) == 1:
			result.update(party_doctype=doctype, party_name=matches[0].name, party_label=matches[0].label)
			break
		if len(matches) > 1:
			names = ", ".join(f"{m.name} ({m.label})" for m in matches[:5])
			result.update(link_note=f"Number shared by {len(matches)} {doctype} records: {names}")
			break
	frappe.cache().set_value(cache_key, result, expires_in_sec=CACHE_SECONDS)
	return result


def find(doctype, fields, label_field, key):
	if not frappe.db.exists("DocType", doctype):
		return []
	meta = frappe.get_meta(doctype)
	fields = [f for f in fields if meta.has_field(f)]
	if not fields:
		return []
	label = label_field if meta.has_field(label_field) else "name"
	where = " or ".join(
		f"right(regexp_replace(ifnull(`{f}`, ''), '[^0-9]', ''), 10) = %(key)s" for f in fields
	)
	return frappe.db.sql(
		f"select name, `{label}` as label from `tab{doctype}` where {where} order by modified desc limit 6",
		{"key": key},
		as_dict=True,
	)


def phones_of(doctype, name):
	"""All phone keys stored on a record (used to show its conversation)."""
	for dt, fields, _label in SOURCES:
		if dt != doctype:
			continue
		meta = frappe.get_meta(doctype)
		values = frappe.db.get_value(doctype, name, [f for f in fields if meta.has_field(f)], as_dict=True) or {}
		return {k for k in (phone_key(v) for v in values.values()) if k}
	return set()


def clear(phone):
	key = phone_key(phone)
	if key:
		frappe.cache().delete_value(f"tc_party:{key}")


@frappe.whitelist()
def relink_all():
	"""Link every stored WhatsApp message to its donor (run after donors' numbers are fixed)."""
	if not frappe.has_permission("WhatsApp Message", "write"):
		frappe.throw("Not permitted", frappe.PermissionError)
	return link_existing()


def link_existing():
	linked = 0
	for phone in frappe.db.sql_list("select distinct phone from `tabWhatsApp Message` where ifnull(phone, '') != ''"):
		clear(phone)
		res = resolve(phone)
		key = phone_key(phone)
		frappe.db.sql(
			"""update `tabWhatsApp Message` set party_doctype=%(dt)s, party_name=%(dn)s, party_label=%(lb)s, link_note=%(nt)s
			where phone=%(phone)s""",
			{"dt": res["party_doctype"], "dn": res["party_name"], "lb": res["party_label"], "nt": res["link_note"],
			 "phone": phone},
		)
		if res["party_name"] and key:
			linked += 1
	frappe.db.commit()
	return linked
