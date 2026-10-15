// Thin wrapper over Frappe's /api/method endpoints.
import { reactive } from "vue";

export const store = reactive({ boot: null, error: null, toast: null });

function errorText(body, fallback) {
	try {
		if (body._server_messages) {
			const msgs = JSON.parse(body._server_messages).map((m) => JSON.parse(m).message);
			return msgs.join("\n").replace(/<[^>]+>/g, "");
		}
	} catch (e) {
		/* fall through */
	}
	if (body.exception) return String(body.exception).split(":").slice(1).join(":").trim() || fallback;
	return fallback;
}

export async function call(method, args = {}, { post = false } = {}) {
	const path = method.includes(".") ? method : `techniti_connect.api.connect.${method}`;
	let url = `/api/method/${path}`;
	const opts = { headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token || "" } };
	if (post) {
		opts.method = "POST";
		opts.headers["Content-Type"] = "application/json";
		opts.body = JSON.stringify(args);
	} else {
		const qs = new URLSearchParams();
		Object.entries(args).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && qs.append(k, v));
		if ([...qs].length) url += `?${qs}`;
	}
	const res = await fetch(url, opts);
	let body = {};
	try {
		body = await res.json();
	} catch (e) {
		/* not JSON */
	}
	if (res.status === 403 && /login|session/i.test(JSON.stringify(body))) {
		window.location.href = "/login?redirect-to=/connect";
	}
	if (!res.ok) throw new Error(errorText(body, `Request failed (${res.status})`));
	return body.message;
}

export async function upload(file) {
	const form = new FormData();
	form.append("file", file, file.name);
	form.append("is_private", "0");
	form.append("folder", "Home");
	const res = await fetch("/api/method/upload_file", {
		method: "POST",
		headers: { "X-Frappe-CSRF-Token": window.csrf_token || "", Accept: "application/json" },
		body: form,
	});
	const body = await res.json().catch(() => ({}));
	if (!res.ok) throw new Error(errorText(body, "Upload failed"));
	return body.message.file_url;
}

export function toast(text, kind = "ok") {
	store.toast = { text, kind };
	clearTimeout(toast._t);
	toast._t = setTimeout(() => (store.toast = null), 3500);
}

export async function refreshCounts() {
	try {
		const b = await call("boot");
		store.boot = b;
	} catch (e) {
		/* keep old counts */
	}
}

export function fmtDate(d, opts = { weekday: "short", day: "numeric", month: "short" }) {
	if (!d) return "";
	const date = new Date(String(d).replace(" ", "T"));
	return isNaN(date) ? d : date.toLocaleDateString("en-IN", opts);
}

export function fmtTime(d) {
	if (!d) return "";
	const date = new Date(String(d).replace(" ", "T"));
	return isNaN(date) ? d : date.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
}

export function ago(d) {
	if (!d) return "";
	const date = new Date(String(d).replace(" ", "T"));
	const mins = Math.round((Date.now() - date.getTime()) / 60000);
	if (mins < 1) return "now";
	if (mins < 60) return `${mins} min`;
	if (mins < 60 * 24) return `${Math.round(mins / 60)} h`;
	return fmtDate(d, { day: "numeric", month: "short" });
}
