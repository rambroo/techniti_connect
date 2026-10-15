<template>
	<main class="main">
		<header class="page-head">
			<div class="titles">
				<h1>Approvals</h1>
				<span class="muted">Nothing reaches a group until it is approved here or on WhatsApp.</span>
			</div>
			<div class="row" role="tablist" aria-label="Show">
				<button v-for="t in tabs" :key="t.value" class="pill" :class="{ on: tab === t.value }" role="tab"
					:aria-selected="tab === t.value" @click="setTab(t.value)">{{ t.label }}</button>
			</div>
		</header>

		<div v-if="loading" class="row"><div class="spinner"></div><span class="muted">Loading…</span></div>
		<div v-else-if="!batches.length" class="empty">
			<p v-if="tab === 'Proposed'">Nothing waiting. New posts are proposed automatically at 07:00, or use "Plan next post" on a group.</p>
			<p v-else>No posts here.</p>
			<router-link to="/groups" class="btn" style="margin-top: 12px">Go to groups</router-link>
		</div>

		<section v-for="b in batches" :key="b.group + b.date" class="card" style="overflow: hidden">
			<div class="section-head">
				<h2>{{ b.group }}</h2>
				<span class="chip amber">Posts {{ fmtDate(b.date) }}, {{ b.time }}</span>
				<span class="small muted">Approver: {{ b.approver || "—" }} · forwarded by {{ b.admin || "—" }}</span>
				<span class="grow"></span>
				<button v-if="tab === 'Proposed' && b.posts.some((p) => p.content && p.status === 'Proposed')" class="btn primary"
					:disabled="busy" @click="approveAll(b)">Approve all</button>
			</div>
			<div class="grid grid-3" style="padding: 18px">
				<article v-for="p in b.posts" :key="p.name" class="card post">
					<MediaPreview :content="p.content_doc" :dim="p.status === 'Skipped'">
						<span class="chip status" :class="statusColor(p.status)">{{ p.status }}</span>
					</MediaPreview>
					<div class="body">
						<span style="font-weight: 600">{{ p.content_doc?.title || `${p.content_type}: nothing picked yet` }}</span>
						<p v-if="p.error && !p.content" class="small" style="color: var(--amber)">{{ p.error }}</p>
						<label class="field" v-if="p.content">Caption sent with the post
							<textarea rows="3" v-model="p.caption" :readonly="!editable(p)" @change="saveCaption(p)"></textarea>
						</label>
						<span class="xs muted" v-if="p.content_doc?.source_credit">{{ p.content_doc.source_credit }}</span>
						<span class="xs muted" v-if="p.approved_by && p.status !== 'Proposed'">{{ p.status }} by {{ p.approved_by }}</span>
						<div class="row actions" v-if="editable(p)">
							<button class="btn primary" style="flex: 1 1 0" :disabled="busy || !p.content" @click="act(p, 'approve')">Approve</button>
							<button class="btn" :disabled="busy" @click="act(p, 'swap')">Swap</button>
							<button class="btn" :disabled="busy" @click="act(p, 'skip')">Skip</button>
						</div>
						<div class="row actions" v-else-if="p.status === 'Sent to Admin'">
							<button class="btn" :disabled="busy" @click="act(p, 'posted')">Mark posted</button>
						</div>
					</div>
				</article>
			</div>
		</section>
	</main>
</template>

<script setup>
import { onMounted, ref } from "vue";
import MediaPreview from "../components/MediaPreview.vue";
import { call, fmtDate, refreshCounts, toast } from "../api.js";

const tabs = [
	{ value: "Proposed", label: "Waiting" },
	{ value: "Approved", label: "Approved" },
	{ value: "Done", label: "Sent & posted" },
];
const tab = ref("Proposed");
const batches = ref([]);
const loading = ref(true);
const busy = ref(false);

async function load() {
	loading.value = true;
	try {
		batches.value = await call("approvals", { status: tab.value });
	} catch (e) {
		toast(e.message, "err");
	}
	loading.value = false;
}
function setTab(v) {
	tab.value = v;
	load();
}
const editable = (p) => ["Proposed", "Approved", "Skipped"].includes(p.status);
const statusColor = (s) =>
	({ Proposed: "amber", Approved: "green", Posted: "green", "Sent to Admin": "grey", Skipped: "grey", Missed: "red", Failed: "red" })[s] || "grey";

async function act(p, action) {
	busy.value = true;
	try {
		const fresh = await call("decide", { post_name: p.name, action }, { post: true });
		Object.assign(p, fresh);
		toast({ approve: "Approved", skip: "Skipped", swap: "Swapped for a new pick", posted: "Marked posted" }[action]);
		refreshCounts();
	} catch (e) {
		toast(e.message, "err");
	}
	busy.value = false;
}
async function approveAll(b) {
	busy.value = true;
	try {
		const done = await call("approve_all", { group: b.group, post_date: b.date }, { post: true });
		toast(`${done.length} approved`);
		await load();
		refreshCounts();
	} catch (e) {
		toast(e.message, "err");
	}
	busy.value = false;
}
async function saveCaption(p) {
	try {
		await call("set_caption", { post_name: p.name, caption: p.caption }, { post: true });
		toast("Caption saved");
	} catch (e) {
		toast(e.message, "err");
	}
}
onMounted(load);
</script>

<style scoped>
.post { overflow: hidden; display: flex; flex-direction: column; }
.status { position: absolute; top: 10px; right: 10px; }
.body { padding: 14px; display: flex; flex-direction: column; gap: 10px; flex-grow: 1; }
.actions { margin-top: auto; flex-wrap: nowrap; }
</style>
