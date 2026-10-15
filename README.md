# Techniti Connect

WhatsApp for TechNiti (We Can We Will Foundation), built on Frappe v15 and the Sparklebot
WhatsApp Cloud API account.

- **Weekly group posts**: a content library, never-repeat picks, approval on WhatsApp
  (Approve / Swap / Skip — tap buttons with an API v2 token, otherwise a short reply code such as A12), and delivery to the group admin with a "Posted" button.
- **Share check**: a message expected on set days (e.g. Hitesh sir, Tue/Thu/Sat) is captured
  when it reaches the foundation's number, sent to the group admin the next morning, and escalated
  if it is missed.
- **Message log**: every incoming and outgoing WhatsApp message, linked to the document it belongs to.
- **Notifications engine** (moved from the techniti app): WhatsApp Notification rules on any
  DocType, the WhatsApp Queue with retries, and date/time reminders.

## The /connect app

`https://<site>/connect` is a separate screen (like Frappe CRM's `/crm`) for people with the
WhatsApp Manager or WhatsApp Agent role:

| Page | What it does |
|---|---|
| Home | Posts waiting for approval, upcoming posts, share checks, recent messages |
| Approvals | Each week's posts with previews: edit the caption, Approve / Swap / Skip, Approve all |
| Inbox | Every WhatsApp conversation, linked to its Donor; reply while the 24-hour window is open |
| Library | All content with filters; add photos, videos or links; generate content now |
| Groups & Share Checks | Schedules, automatic-content switch, plan next post, share-check history |

It is a Vue 3 app in `frontend/`. `bench build` runs `yarn build` (root `package.json`), which writes
the assets to `techniti_connect/public/frontend/` and the page to `techniti_connect/www/connect.html`.
For development: `cd frontend && yarn dev` (proxies to a bench on port 8015).

Donor and Website Donor forms also get a WhatsApp section at the top (conversation, window status,
reply box). Every message is linked automatically to the Donor whose number matches.

## Automatic content

Tick **Create Content Automatically** on a WhatsApp Group and choose a theme (Faith (Mixed),
Students, General Motivation). Before asking for approval each week, the app tops up that group's
library itself:

| Slot | Source |
|---|---|
| Photo | A new quote card (1080×1080) with a line that has never been used before. The background is a colour gradient, or a free Pexels photo when a Pexels key is set |
| Video | A free-licence Pexels clip (landscape, ≤ 16 MB), or a YouTube link, alternating |
| Reel | A free-licence Pexels clip (portrait), or a YouTube Shorts link, alternating |

Nothing is posted without approval. Swap fetches a new item; automatically created items that are
swapped or skipped are retired so they are not offered again. Keys go in **WhatsApp Setting →
Automatic Content Sources** (both free: pexels.com/api and Google Cloud's YouTube Data API v3).

## How posts reach the group

WhatsApp's official API (which Sparklebot uses) cannot post into a group created in the WhatsApp
app. Each WhatsApp Group chooses a **Posting Method**:

- **Forward via Admin**: the approved post is sent to the admin's own WhatsApp, ready to forward.
  Tapping **Posted** records it.
- **Post Directly**: a separate *group posting number*, linked to a self-hosted WAHA server, posts it
  straight into the group and it is marked Posted. If that number is disconnected, the post goes to
  the admin to forward instead. Setup: [docs/group-posting-number.md](docs/group-posting-number.md).

When a group's post day changes, pending posts planned for the old day are skipped.

## Install

```bash
bench get-app <this repo URL>
bench --site <site> install-app techniti_connect
```

If the site already has the WhatsApp DocTypes from the techniti app, installing re-homes them to this
app. Their data stays as it is, the API token is moved to encrypted storage, and an
incoming-webhook secret is generated. Deploy the techniti version without the WhatsApp module at the
same time.

## Set up

1. **WhatsApp Setting**: Enabled, API v1 base `https://sparklebot.in/api/v1`, tenant
   `wecanwewillfdnorg`, API token (Sparklebot > Settings > System > API Management).
2. **Incoming messages**: copy *Webhook URL for Sparklebot* from WhatsApp Setting into Sparklebot >
   Settings > Application > Whatsapp Webhook: tick *Enable WebHooks Re-send*, method **POST**.
3. **Staff alert template** (recommended): create a UTILITY template in Sparklebot with two body
   fields and enter its name in WhatsApp Setting. Example:
   `Hello {{1}}, {{2}}. Please reply OK to see it.`
   Free-form messages only reach someone within 24 hours of their last message. When that window
   is closed, staff get this template, and their reply releases the held messages.
4. **WhatsApp Group**: fill in the admin's and approver's numbers, the weekday and time, and what to
   post each week. Tick Enabled.
5. **Group Content**: upload photos (≤ 5 MB) and videos (≤ 16 MB), or paste reel links. Exact and
   near-duplicate photos are rejected.
6. **Share Check Rule**: the numbers allowed to submit the message, the days, and the target group.
   Tick Enabled.

## Roles

| Role | Can |
|---|---|
| WhatsApp Manager | Everything in this app |
| WhatsApp Agent | Add content, approve and confirm posts, mark shares, read messages |

The webhook endpoint accepts requests only with the secret token. Nothing donor-specific is
sent to group admins or approvers.

## Schedules

| When | What |
|---|---|
| 07:00 daily | Propose next posts for groups whose post day is within *Ask for Approval (days before)* |
| Every 10 min | Send approved posts at post time, remind admins after 3 h, run share checks |
| Daily | Mark unconfirmed posts as Missed, expire messages held for over 3 days |
| Every 4 min | WhatsApp Queue (notification rules) |

## License

MIT
