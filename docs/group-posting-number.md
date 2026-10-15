# Group posting number

WhatsApp's official API (Sparklebot) cannot post into groups created in the WhatsApp app. To post
approved content straight into a group, Techniti Connect links a **separate** WhatsApp number to the
site as a WhatsApp *linked device*, the same way WhatsApp Web does.

It runs inside the app on Frappe Cloud, with no extra server and nothing running all the time.
A background job starts a short-lived process (`whatsapp/linked_runner.py`, using the
[neonize](https://pypi.org/project/neonize/) library). The process connects, does one task and exits:
- link the number (shows a QR code in /connect)
- post the approved items into the group at post time
- refresh the list of groups
- check that the link is still alive (once a day)

The login is kept in `sites/<site>/private/techniti_connect/posting-number.db`.

- Use a spare number (a prepaid SIM in a spare phone), not the foundation's official number. A personal
  number is fine for a short test only. Linked-device tools are not approved by Meta, so a number used
  this way can be banned. At a few posts a week into groups the number belongs to, the risk is low, and
  if it ever happens only that number is affected: posts fall back to the group admin automatically.
- Add the number to each group, as an admin where only admins can post. Open WhatsApp on that phone
  now and then: WhatsApp unlinks devices after about 14 days without the phone.
- Donor messages, receipts and reminders always stay on the official number.

## Set up

1. **/connect → Groups → Group posting number → Link number**. A QR code appears within a few seconds.
2. On the posting phone: WhatsApp → Settings → Linked devices → Link a device, and scan it within
   3 minutes. The card turns *Linked* and lists the groups the number is in.
3. On a group's card choose **Post directly (posting number)** and pick the WhatsApp group. If the number
   joins a group later, press **Refresh groups**.

The status is also shown on the **Group Posting Setting** page, which is separate from WhatsApp
Setting. There is nothing to type in.

## What happens at post time

Approved posts go straight into the group, about 8 seconds apart, and are marked **Posted**:
- photos as images
- YouTube and other links as text with a preview
- video files as videos (this needs ffmpeg on the server)

If the number is not linked, WhatsApp refuses a post or it fails, that post goes to the group admin to
forward (as before) and the approver gets one WhatsApp message saying why. If WhatsApp unlinks the
number, the approvers of the groups that post directly are told.
