<template>
	<main class="main">
		<header class="page-head">
			<div class="titles">
				<h1>Groups &amp; Share Checks</h1>
				<span class="muted">Who approves, who forwards, when it goes out, and where the content comes from.</span>
			</div>
			<a v-if="isManager" class="btn" href="/app/whatsapp-group/new">New group</a>
		</header>

		<section v-if="isManager" class="card card-pad poster" aria-label="Group posting number">
			<div class="row" style="align-items: flex-start">
				<div style="display: flex; flex-direction: column; gap: 2px; min-width: 0" class="grow">
					<h2>Group posting number</h2>
					<span class="small muted">A separate WhatsApp number that posts approved content straight into groups. Donor messages never use it.</span>
				</div>
				<span class="chip" :class="posterChip.color">{{ posterChip.label }}</span>
			</div>
			<p v-if="!poster" class="small muted">Checking…</p>
			<template v-else>
				<p v-if="poster.error" class="small" style="color: var(--red)">{{ poster.error }}</p>
				<div v-if="poster.linking === 'qr' && poster.qr" class="qr-wrap">
					<img :src="poster.qr" alt="QR code to link the group posting number" width="230" height="230">
					<ol class="small">
						<li>On the phone with the posting number, open WhatsApp.</li>
						<li>Settings → Linked devices → Link a device.</li>
						<li>Scan this code. It refreshes by itself; you have 3 minutes.</li>
					</ol>
				</div>
				<div v-else-if="poster.linking === 'starting'" class="row"><div class="spinner"></div><span class="small muted">Getting a QR code from WhatsApp…</span></div>
				<template v-else-if="poster.status === 'Linked'">
					<div class="row">
						<span class="grow"><b>{{ poster.name || "Linked" }}</b> <span class="muted">{{ poster.number }}</span></span>
						<button class="btn sm" :disabled="posterBusy" @click="posterRefresh">Refresh groups</button>
						<button class="btn sm" :disabled="posterBusy" @click="posterUnlink">Unlink</button>
					</div>
					<span class="xs muted">In {{ poster.group_count }} group{{ poster.group_count === 1 ? "" : "s" }}<template v-if="poster.last_checked"> · last connected {{ stamp(poster.last_checked) }}</template></span>
					<span v-if="poster.last_error" class="xs" style="color: var(--amber)">Last problem: {{ poster.last_error }}</span>
				</template>
				<div v-else class="row">
					<button class="btn primary" :disabled="posterBusy" @click="posterLink">Link number</button>
					<span class="xs muted">Shows a QR code to scan from the posting phone, like WhatsApp Web.</span>
				</div>
			</template>
		</section>

		<div v-if="loading" class="row"><div class="spinner"></div><span class="muted">Loading…</span></div>
		<div v-else class="grid grid-3">
			<article v-for="g in data.groups" :key="g.name" class="card card-pad group">
				<div class="row" style="align-items: flex-start; flex-wrap: nowrap">
					<div style="display: flex; flex-direction: column; gap: 2px; min-width: 0" class="grow">
						<h2>{{ g.name }}</h2>
						<span class="small muted">{{ g.purpose }}</span>
					</div>
					<span class="chip" :class="g.enabled ? 'green' : 'amber'">{{ g.enabled ? "Active" : "Off" }}</span>
				</div>
				<dl class="facts">
					<dt>Posts</dt><dd>{{ g.post_weekday ? `${g.post_weekday}s, ${g.post_time}` : "—" }}</dd>
					<dt>Next</dt><dd>{{ g.next_date ? fmtDate(g.next_date) : "—" }}</dd>
					<dt>Each week</dt><dd>{{ g.slots.length ? g.slots.map((s) => `${s.qty} ${s.type.toLowerCase()}`).join(" · ") : "Share check only" }}</dd>
					<dt>Unused</dt><dd>{{ g.slots.length ? g.slots.map((s) => `${g.unused[s.type] || 0} ${s.type.toLowerCase()}`).join(" · ") : "—" }}</dd>
					<dt>Approver</dt><dd>{{ g.approver_name || "—" }} <span class="muted">{{ g.approver_phone || "" }}</span></dd>
					<dt>{{ g.posting_method === "Post Directly" ? "Backup" : "Forwards it" }}</dt><dd>{{ g.admin_name || "—" }} <span class="muted">{{ g.admin_phone || "" }}</span></dd>
				</dl>
				<div v-if="g.slots.length" class="auto" style="flex-direction: column; align-items: stretch; gap: 6px">
					<label class="small" style="font-weight: 600; display: flex; flex-direction: column; gap: 4px">How it reaches the group
						<select :value="g.posting_method || 'Forward via Admin'" :disabled="!isManager" class="theme" @change="setMethod(g, $event.target.value)">
							<option value="Forward via Admin">Admin forwards it</option>
							<option value="Post Directly">Post directly (posting number)</option>
						</select>
					</label>
					<template v-if="g.posting_method === 'Post Directly'">
						<span v-if="g.group_chat_id" class="xs muted">Posts into: <b style="color: var(--ink)">{{ g.group_chat_name || g.group_chat_id }}</b></span>
						<span v-else class="xs" style="color: var(--amber)">Choose the WhatsApp group</span>
						<select v-if="isManager && chats.length" class="theme" :value="g.group_chat_id || ''" @change="setChat(g, $event.target.value)" aria-label="WhatsApp group">
							<option value="" disabled>Choose a group…</option>
							<option v-for="c in chats" :key="c.id" :value="c.id">{{ c.name }}</option>
						</select>
						<span v-else-if="isManager && poster?.status === 'Linked'" class="xs muted">{{ chatsLoading ? "Loading groups…" : "The posting number is in no groups yet. Add it to the group, then Refresh groups" }}</span>
						<span v-else-if="isManager" class="xs muted">Link the posting number above to choose a group</span>
					</template>
				</div>
				<div v-if="g.slots.length" class="auto">
					<span style="display: flex; flex-direction: column; flex-grow: 1">
						<span class="small" style="font-weight: 600">Create content automatically</span>
						<select v-if="g.auto_content && isManager" v-model="g.content_theme" @change="setAuto(g, 1)" class="theme" aria-label="Theme">
							<option>Faith (Mixed)</option><option>Students</option><option>General Motivation</option>
						</select>
						<span v-else class="xs muted">{{ g.auto_content ? `Theme: ${g.content_theme}` : "Off: uses content you add" }}</span>
					</span>
					<button class="switch" role="switch" :aria-checked="!!g.auto_content" :aria-label="`Create content automatically for ${g.name}`"
						:class="{ on: g.auto_content }" :disabled="!isManager" @click="setAuto(g, g.auto_content ? 0 : 1)"><span></span></button>
				</div>
				<div class="row" style="margin-top: auto">
					<button v-if="g.slots.length && isManager" class="btn primary grow" :disabled="busy === g.name" @click="plan(g)">
						{{ busy === g.name ? "Planning…" : "Plan next post" }}</button>
					<a class="btn" :href="`/app/whatsapp-group/${encodeURIComponent(g.name)}`">Settings</a>
				</div>
			</article>
		</div>

		<section v-for="r in data.rules || []" :key="r.name" class="card" style="overflow: hidden">
			<div class="section-head">
				<h2>Share check · {{ r.source_name || r.name }}</h2>
				<span class="small muted">Message on {{ r.days.join(" / ") || "—" }} → shared next day in {{ r.whatsapp_group }} · to admin {{ r.forward_time }} · escalate {{ r.escalate_time }}</span>
				<span class="grow"></span>
				<span class="chip" :class="r.enabled ? 'green' : 'amber'">{{ r.enabled ? "On" : "Off" }}</span>
				<span v-if="r.month_total" class="chip grey">On time this month: {{ r.month_on_time }} of {{ r.month_total }}</span>
				<a class="btn sm" :href="`/app/share-check-rule/${encodeURIComponent(r.name)}`">Settings</a>
			</div>
			<div v-if="!r.checks.length" class="empty" style="margin: 16px; border-style: dashed">No message days yet.</div>
			<div v-else style="overflow-x: auto">
				<table>
					<thead><tr><th scope="col">Message day</th><th scope="col">Received</th><th scope="col">Sent to admin</th>
						<th scope="col">Shared</th><th scope="col">Status</th><th scope="col"><span class="sr">Action</span></th></tr></thead>
					<tbody>
						<tr v-for="c in r.checks" :key="c.name">
							<td style="font-weight: 600">{{ fmtDate(c.source_date) }}</td>
							<td>{{ c.received_on ? stamp(c.received_on) : "—" }}</td>
							<td>{{ c.sent_to_admin_on ? stamp(c.sent_to_admin_on) : "—" }}</td>
							<td>{{ c.shared_on ? stamp(c.shared_on) : "—" }}</td>
							<td><span class="chip" :class="checkColor(c)">{{ checkLabel(c) }}</span></td>
							<td style="text-align: right">
								<button v-if="['Received', 'Sent to Admin'].includes(c.status)" class="btn sm" @click="markShared(c)">Mark shared</button>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { call, fmtDate, fmtTime, refreshCounts, store, toast } from "../api.js";
import { useRouter } from "vue-router";

const router = useRouter();
const isManager = computed(() => store.boot?.is_manager);
const data = ref({ groups: [], rules: [] });
const loading = ref(true);
const busy = ref("");

async function load() {
	try {
		data.value = await call("groups");
	} catch (e) {
		toast(e.message, "err");
	}
	loading.value = false;
}
async function setAuto(g, on) {
	try {
		g.auto_content = await call("set_auto", { group: g.name, enabled: on, theme: g.content_theme }, { post: true });
		toast(on ? "Automatic content on" : "Automatic content off");
	} catch (e) {
		toast(e.message, "err");
	}
}
async function plan(g) {
	busy.value = g.name;
	try {
		const posts = await call("plan_now", { group: g.name }, { post: true });
		if (posts && posts.length) {
			toast(`${posts.length} post(s) proposed`);
			refreshCounts();
			router.push("/approvals");
		} else {
			toast("Already planned for the next date, or its time has passed.");
		}
	} catch (e) {
		toast(e.message, "err");
	}
	busy.value = "";
}
async function markShared(c) {
	try {
		c.status = await call("mark_shared", { check: c.name }, { post: true });
		c.shared_on = new Date().toISOString();
		toast("Marked shared");
	} catch (e) {
		toast(e.message, "err");
	}
}
// --- group posting number
const poster = ref(null);
const posterBusy = ref(false);
const chats = ref([]);
const chatsLoading = ref(false);
let posterTimer = null;
const posterChip = computed(() => {
	const p = poster.value;
	if (!p) return { label: "…", color: "grey" };
	if (p.linking === "qr") return { label: "Waiting for scan", color: "amber" };
	if (p.linking === "starting") return { label: "Starting", color: "amber" };
	return p.status === "Linked" ? { label: "Linked", color: "green" } : { label: "Not linked", color: "grey" };
});
async function loadPoster(poll = 0) {
	clearTimeout(posterTimer);
	const wasLinking = ["starting", "qr"].includes(poster.value?.linking);
	try {
		poster.value = await call("poster");
	} catch (e) {
		poster.value = { status: "Not linked", error: e.message };
	}
	const p = poster.value;
	if (p.status === "Linked" && (!chats.value.length || wasLinking)) loadChats();
	if (["starting", "qr"].includes(p.linking)) posterTimer = setTimeout(() => loadPoster(), 3000);
	else if (poll > 0) posterTimer = setTimeout(() => loadPoster(poll - 1), 4000);
}
async function loadChats() {
	chatsLoading.value = true;
	try {
		chats.value = await call("poster_groups");
	} catch (e) {
		toast(e.message, "err");
	}
	chatsLoading.value = false;
}
async function posterLink() {
	posterBusy.value = true;
	try {
		poster.value = await call("poster_link", {}, { post: true });
	} catch (e) {
		toast(e.message, "err");
	}
	posterBusy.value = false;
	loadPoster();
}
async function posterRefresh() {
	posterBusy.value = true;
	try {
		await call("poster_refresh", {}, { post: true });
		toast("Checking the posting number…");
		chats.value = [];
		setTimeout(() => loadPoster(4), 4000);
	} catch (e) {
		toast(e.message, "err");
	}
	posterBusy.value = false;
}
async function posterUnlink() {
	if (!confirm("Unlink the posting number? Groups set to post directly will go to their admin until you link it again.")) return;
	posterBusy.value = true;
	try {
		await call("poster_unlink", {}, { post: true });
		chats.value = [];
		toast("Unlinking…");
		setTimeout(() => loadPoster(4), 3000);
	} catch (e) {
		toast(e.message, "err");
	}
	posterBusy.value = false;
}
async function setMethod(g, method) {
	try {
		Object.assign(g, await call("set_posting", { group: g.name, method }, { post: true }));
		toast(method === "Post Directly" ? "Will post directly" : "Admin will forward");
	} catch (e) {
		toast(e.message, "err");
	}
}
async function setChat(g, id) {
	const chat = chats.value.find((c) => c.id === id);
	try {
		Object.assign(g, await call("set_posting", { group: g.name, method: g.posting_method, chat_id: id, chat_name: chat?.name }, { post: true }));
		toast(`Posts into ${chat?.name || id}`);
	} catch (e) {
		toast(e.message, "err");
	}
}
onBeforeUnmount(() => clearTimeout(posterTimer));

const stamp = (d) => `${fmtDate(d, { weekday: "short" })} ${fmtTime(d)}`;
const checkLabel = (c) => (c.status === "Shared" ? (c.shared_on_time ? "Shared on time" : "Shared late") : c.status);
const checkColor = (c) =>
	({ Shared: c.shared_on_time ? "green" : "amber", Missed: "red", "Waiting for Message": "amber" })[c.status] || "grey";
onMounted(() => {
	load();
	if (isManager.value) loadPoster();
});
</script>

<style scoped>
.group { display: flex; flex-direction: column; gap: 12px; }
.poster { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.qr-wrap { display: flex; flex-wrap: wrap; gap: 20px; align-items: center; }
.qr-wrap img { border: 1px solid var(--line); border-radius: 10px; background: #fff; padding: 8px; }
.qr-wrap ol { margin: 0; padding-left: 18px; display: flex; flex-direction: column; gap: 6px; }
.facts { margin: 0; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 6px 12px; font-size: 13px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; font-weight: 600; }
.auto { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; background: var(--panel); }
.theme { min-height: 30px; padding: 2px 6px; margin-top: 4px; font-size: 12px; }
.switch { width: 44px; height: 26px; border-radius: 999px; border: 0; cursor: pointer; position: relative; padding: 0; background: #c9c9c4; flex: 0 0 auto; }
.switch span { position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 999px; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, .25); transition: left .15s; }
.switch.on { background: var(--green); }
.switch.on span { left: 21px; }
.switch:disabled { cursor: not-allowed; opacity: .7; }
table { width: 100%; border-collapse: collapse; }
th { font-size: 12px; font-weight: 600; color: var(--muted); text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); white-space: nowrap; }
td { font-size: 14px; padding: 10px 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
.sr { position: absolute; left: -9999px; }
</style>
