app_name = "techniti_connect"
app_title = "Techniti Connect"
app_publisher = "Rohan Rambhiya"
app_description = "WhatsApp, bots and donor messaging for TechNiti (WCWW)"
app_email = "rohanrambhiya59@gmail.com"
app_license = "mit"
required_apps = ["frappe"]

add_to_apps_screen = [
	{
		"name": "techniti_connect",
		"logo": "/assets/techniti_connect/images/logo.svg",
		"title": "Techniti Connect",
		"route": "/app/techniti-connect",
	}
]

# Installation
# ------------
before_install = "techniti_connect.install.before_install"
after_install = "techniti_connect.install.after_install"
after_migrate = "techniti_connect.install.after_migrate"

# Document Events
# ---------------
# WhatsApp Notification rules can target any DocType
doc_events = {
	"*": {
		"on_submit": "techniti_connect.whatsapp.engine.handle_whatsapp_notification_submit",
		"after_save": "techniti_connect.whatsapp.engine.handle_whatsapp_notification_save",
		"on_cancel": "techniti_connect.whatsapp.engine.handle_whatsapp_notification_cancel",
		"after_insert": "techniti_connect.whatsapp.engine.handle_whatsapp_notification_creation",
		"on_update": "techniti_connect.whatsapp.engine.handle_whatsapp_notification_update",
	}
}

# Called by techniti.attach_pdf once a receipt/ticket PDF URL is saved
after_pdf_attach = ["techniti_connect.whatsapp.engine.on_pdf_ready"]

# Scheduled Tasks
# ---------------
scheduler_events = {
	"all": [
		"techniti_connect.techniti_connect.doctype.whatsapp_queue.whatsapp_queue.process_whatsapp_queue",
	],
	"cron": {
		"*/10 * * * *": [
			"techniti_connect.groups.dispatch_due",
			"techniti_connect.groups.remind_unposted",
			"techniti_connect.share_check.tick",
		],
		"0 7 * * *": ["techniti_connect.groups.plan_upcoming"],
		"0 11 * * *": ["techniti_connect.whatsapp.engine.send_scheduled_whatsapp_reminders_enhanced"],
	},
	"hourly": ["techniti_connect.whatsapp.engine.process_scheduled_whatsapp_time_reminders"],
	"daily": [
		"techniti_connect.groups.close_stale",
		"techniti_connect.whatsapp.outbox.expire_held",
	],
}
