<template>
	<main class="main">
		<header class="page-head">
			<div class="titles">
				<h1>Groups &amp; Share Checks</h1>
				<span class="muted">Who approves, who forwards, when it goes out, and where the content comes from.</span>
			</div>
			<a v-if="isManager" class="btn" href="/app/whatsapp-group/new">New group</a>
		</header>

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
					<dt>Forwards it</dt><dd>{{ g.admin_name || "—" }} <span class="muted">{{ g.admin_phone || "" }}</span></dd>
				</dl>
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
import { computed, onMounted, ref } from "vue";
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
const stamp = (d) => `${fmtDate(d, { weekday: "short" })} ${fmtTime(d)}`;
const checkLabel = (c) => (c.status === "Shared" ? (c.shared_on_time ? "Shared on time" : "Shared late") : c.status);
const checkColor = (c) =>
	({ Shared: c.shared_on_time ? "green" : "amber", Missed: "red", "Waiting for Message": "amber" })[c.status] || "grey";
onMounted(load);
</script>

<style scoped>
.group { display: flex; flex-direction: column; gap: 12px; }
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
