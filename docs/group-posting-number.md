# Group posting number (WAHA)

WhatsApp's official API (Sparklebot) cannot post into groups created in the WhatsApp app. To post
approved content straight into a group, Techniti Connect can use a **separate** WhatsApp number linked
to a self-hosted [WAHA](https://waha.devlike.pro) server, the same way WhatsApp Web links a phone.

- Use a spare number (a prepaid SIM in a spare phone), never the foundation's official number or a
  personal number. Linked-device tools are not approved by Meta, so a number used this way can be
  banned. At a few posts a week into groups the number belongs to, the risk is low, and if it ever
  happens only this spare number is affected: posts fall back to the group admin automatically.
- Add the number to each group, as an admin where only admins can post. Open WhatsApp on that phone
  now and then: WhatsApp unlinks devices after about 14 days without the phone.
- Donor messages, receipts and reminders always stay on the official number.

## 1. Server

Any small always-on Linux server with Docker and 2 GB RAM (a ₹400–700/month VPS is enough). Point a
domain such as `waha.wecanwewillfdn.org` at it, then create `docker-compose.yml`:

```yaml
services:
  waha:
    image: devlikeapro/waha:latest
    restart: always
    environment:
      WAHA_API_KEY: "<long random string>"
      WHATSAPP_RESTART_ALL_SESSIONS: "True"
      WAHA_DASHBOARD_ENABLED: "False"
      WHATSAPP_SWAGGER_ENABLED: "False"
    volumes:
      - ./sessions:/app/.sessions
  caddy:
    image: caddy:2
    restart: always
    ports: ["80:80", "443:443"]
    command: caddy reverse-proxy --from waha.wecanwewillfdn.org --to waha:3000
    volumes:
      - caddy_data:/data
volumes:
  caddy_data: {}
```

Run `docker compose up -d`. Caddy gets the HTTPS certificate itself. Generate the API key with
`openssl rand -hex 32` and keep it out of chats and email.

## 2. Techniti

1. **Group Posting Setting** (its own page, separate from WhatsApp Setting): WAHA Server URL `https://waha.wecanwewillfdn.org`,
   WAHA Session `default`, WAHA API Key (the same string). Save.
2. **/connect → Groups → Group posting number → Connect number**. A QR code appears.
3. On the spare phone: WhatsApp → Settings → Linked devices → Link a device, and scan it. The card
   turns *Connected*.
4. On each group's card choose **Post directly (posting number)**, then pick the WhatsApp group.

## What happens at post time

Approved posts go straight into the group, a few seconds apart, and are marked **Posted**. If the
number is disconnected, the server is unreachable or WhatsApp refuses a post, that post goes to the
group admin to forward (as before) and the approver gets a WhatsApp message saying why.
