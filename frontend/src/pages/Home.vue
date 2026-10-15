<template>
	<main class="main">
		<header class="page-head">
			<div class="titles">
				<h1>{{ greeting }}, {{ firstName }}</h1>
				<span class="muted">{{ today }} · WhatsApp {{ store.boot.whatsapp_enabled ? "connected" : "switched off in WhatsApp Setting" }}</span>
			</div>
			<router-link v-if="d.counts?.approvals" to="/approvals" class="btn primary">Review {{ d.counts.approvals }} post{{ d.counts.approvals === 1 ? "" : "s" }}</router-link>
		</header>

		<div v-if="loading" class="row"><div class="spinner"></div></div>
		<template v-else>
			<section class="grid grid-4" aria-label="At a glance">
				<router-link to="/approvals" class="card card-pad stat">
					<span class="small muted">Waiting for approval</span><span class="num">{{ d.counts.approvals }}</span>
					<span class="small" :style="{ color: d.counts.approvals ? 'var(--amber)' : 'var(--muted)' }">{{ nextLabel }}</span>
				</router-link>
				<div class="card card-pad stat">
					<span class="small muted">Posts in the next two weeks</span><span class="num">{{ postedOf }}</span>
					<span class="small muted">{{ d.group_count }} active group{{ d.group_count === 1 ? "" : "s" }}</span>
				</div>
				<router-link to="/groups" class="card card-pad stat">
					<span class="small muted">Share checks, last 7 days</span><span class="num">{{ sharedOf }}</span>
					<span class="small muted">shared on time</span>
				</router-link>
				<router-link to="/inbox" class="card card-pad stat">
					<span class="small muted">Waiting for a reply</span><span class="num">{{ d.counts.unanswered }}</span>
					<span class="small muted">conversations</span>
				</router-link>
			</section>

			<div class="row" style="align-items: flex-start; gap: 20px">
				<section class="card card-pad" style="flex: 3 1 480px; min-width: 0">
					<div class="row" style="justify-content: space-between; margin-bottom: 6px"><h2>Upcoming posts</h2><router-link to="/groups" class="small">All groups</router-link></div>
					<p v-if="!d.week.length" class="small muted" style="padding: 10px 0">Nothing planned yet. Posts are proposed a couple of days before each group's post day.</p>
					<div v-for="w in d.week" :key="w.group + w.date" class="line">
						<div style="display: flex; flex-direction: column"><b class="small">{{ fmtDate(w.date) }}</b><span class="xs muted">{{ w.time }}</span></div>
						<div style="display: flex; flex-direction: column; min-width: 0"><span style="font-weight: 600">{{ w.group }}</span><span class="small muted">{{ w.types.join(" · ") }}</span></div>
						<span class="chip" :class="w.summary === 'Posted' ? 'green' : w.summary.includes('approve') ? 'amber' : 'grey'">{{ w.summary }}</span>
					</div>
				</section>
				<section class="card card-pad" style="flex: 2 1 320px; min-width: 0">
					<div class="row" style="justify-content: space-between; margin-bottom: 6px"><h2>Recent messages</h2><router-link to="/inbox" class="small">Open inbox</router-link></div>
					<p v-if="!d.recent.length" class="small muted" style="padding: 10px 0">No messages yet.</p>
					<router-link v-for="m in d.recent" :key="m.phone + m.at" :to="`/inbox/${m.phone}`" class="msg">
						<span class="avatar">{{ initials(m.name) }}</span>
						<span style="display: flex; flex-direction: column; min-width: 0"><span style="font-weight: 600">{{ m.name }}</span><span class="small muted ell">{{ m.text || `[${m.message_type}]` }}</span></span>
						<span class="xs muted">{{ ago(m.at) }}</span>
					</router-link>
				</section>
			</div>
		</template>
	</main>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ago, call, fmtDate, store, toast } from "../api.js";

const d = ref({ counts: {}, week: [], checks: [], recent: [] });
const loading = ref(true);
const hour = new Date().getHours();
const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
const firstName = computed(() => (store.boot?.user?.full_name || "").split(" ")[0]);
const today = new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });
const nextLabel = computed(() => {
	const w = d.value.week.find((x) => x.summary.includes("approve"));
	return w ? `${w.group} · ${fmtDate(w.date)} ${w.time}` : "All caught up";
});
const postedOf = computed(() => {
	const all = d.value.week.length;
	return `${d.value.week.filter((w) => w.summary === "Posted").length} of ${all}`;
});
const sharedOf = computed(() => {
	const done = d.value.checks.filter((c) => c.share_date < new Date().toISOString().slice(0, 10) || c.status === "Shared");
	return `${done.filter((c) => c.shared_on_time).length} of ${done.length}`;
});
const initials = (n) => (n || "?").split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();

onMounted(async () => {
	try {
		d.value = await call("home");
		store.boot.counts = d.value.counts;
	} catch (e) {
		toast(e.message, "err");
	}
	loading.value = false;
});
</script>

<style scoped>
.stat { display: flex; flex-direction: column; gap: 6px; text-decoration: none; color: var(--ink); }
.stat:hover { border-color: #cfcfca; color: var(--ink); }
.num { font-size: 28px; font-weight: 700; }
.line { display: grid; grid-template-columns: 88px minmax(0, 1fr) auto; gap: 14px; align-items: center; padding: 10px 0; border-top: 1px solid var(--line-soft); }
.msg { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 8px 0; border-top: 1px solid var(--line-soft); text-decoration: none; color: var(--ink); }
.avatar { width: 36px; height: 36px; border-radius: 999px; background: #eef0f2; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.ell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
