from frappe.tests.utils import FrappeTestCase

from techniti_connect.techniti_connect.doctype.group_content.group_content import hamming, normalize_link
from techniti_connect.whatsapp.inbound import parse
from techniti_connect.whatsapp.phone import normalize_phone, phone_key, split_phones


class TestPhone(FrappeTestCase):
	def test_ten_digit_starting_with_91_gets_country_code(self):
		# the old handler sent this to "9123456789" (wrong number)
		self.assertEqual(normalize_phone("9123456789", "91"), "919123456789")

	def test_formats(self):
		cases = {
			"7045216675": "917045216675",
			"+91 70452 16675": "917045216675",
			"917045216675": "917045216675",
			"07045216675": "917045216675",
			"0091-7045216675": "917045216675",
			"+44 20 7946 0958": "442079460958",
			"12345": None,
			"": None,
		}
		for raw, expected in cases.items():
			self.assertEqual(normalize_phone(raw, "91"), expected, raw)

	def test_phone_key_and_split(self):
		self.assertEqual(phone_key("+91 70452-16675"), "7045216675")
		self.assertEqual(split_phones("7045216675, +91 98200 00000\n123"), {"7045216675", "9820000000"})


class TestLinks(FrappeTestCase):
	def test_instagram_variants_match(self):
		a = normalize_link("https://www.instagram.com/reel/ABC123/?igsh=xyz")
		b = normalize_link("instagram.com/wecanwewill/reel/ABC123")
		self.assertEqual(a, b)
		self.assertEqual(a, "instagram.com/reel/ABC123")

	def test_youtube_variants_match(self):
		self.assertEqual(normalize_link("https://youtu.be/xyz"), normalize_link("https://www.youtube.com/watch?v=xyz&t=3"))
		self.assertEqual(normalize_link("https://youtube.com/shorts/xyz"), "youtube.com/watch/xyz")

	def test_hamming(self):
		self.assertEqual(hamming("ff", "fe"), 1)
		self.assertEqual(hamming(None, "fe"), 64)


class TestInboundParse(FrappeTestCase):
	def test_meta_button_reply_and_status(self):
		payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {
			"contacts": [{"wa_id": "917045216675", "profile": {"name": "Rohan"}}],
			"messages": [{"from": "917045216675", "id": "wamid.A", "timestamp": "1760000000", "type": "interactive",
						  "interactive": {"type": "button_reply", "button_reply": {"id": "gp:approve:GP-2026-00001", "title": "Approve"}}}],
			"statuses": [{"id": "wamid.B", "status": "read"}],
		}}]}]}
		messages, statuses = parse(payload)
		self.assertEqual(messages[0]["button_id"], "gp:approve:GP-2026-00001")
		self.assertEqual(messages[0]["contact_name"], "Rohan")
		self.assertEqual(statuses[0], {"wamid": "wamid.B", "status": "read", "error": None})

	def test_wrapper_format(self):
		payload = {"event": {"type": "whatsapp.message.received"}, "data": {
			"resource": {"type": "message", "attributes": {"message_id": "wamid.C", "from": "917045216675",
																"timestamp": "1760000000", "type": "text", "text": "Hi"}},
			"relationships": {"contact": {"wa_id": "917045216675", "name": "Rohan"}}}}
		messages, _ = parse(payload)
		self.assertEqual(messages[0]["text"], "Hi")
		self.assertEqual(messages[0]["phone"], "917045216675")
