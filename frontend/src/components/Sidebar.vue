<template>
	<nav class="side" aria-label="Main">
		<div class="brand">
			<div class="logo">
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-5.1A8 8 0 1 1 21 12z" /></svg>
			</div>
			<div class="brand-text">
				<span class="name">Techniti Connect</span>
				<span class="xs muted">We Can We Will Foundation</span>
			</div>
		</div>
		<div class="links">
			<router-link to="/" class="link" exact-active-class="on">
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" /></svg>Home
			</router-link>
			<router-link to="/approvals" class="link" active-class="on">
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6L9 17l-5-5" /></svg>Approvals
				<span v-if="counts.approvals" class="badge">{{ counts.approvals }}</span>
			</router-link>
			<router-link to="/inbox" class="link" active-class="on">
				<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-5.1A8 8 0 1 1 21 12z" /></svg>Inbox
				<span v-if="counts.unanswered" class="badge">{{ counts.unanswered }}</span>
			</router-link>
			<router-link to="/library" class="link" active-class="on">
				<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>Library
			</router-link>
			<router-link to="/groups" class="link" active-class="on">
				<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0" /><circle cx="17" cy="9" r="2.5" /><path d="M15.5 14.5A5 5 0 0 1 21 20" /></svg>Groups &amp; Share Checks
			</router-link>
		</div>
		<div class="grow spacer"></div>
		<a class="link" href="/app/whatsapp-setting">
			<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></svg>Settings
		</a>
		<a class="link" href="/app">
			<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>Back to desk
		</a>
		<div v-if="user" class="me">
			<div class="avatar">{{ user.initials }}</div>
			<div class="small" style="display: flex; flex-direction: column">
				<span style="font-weight: 600">{{ user.full_name }}</span>
				<span class="xs muted">{{ store.boot.is_manager ? "WhatsApp Manager" : "WhatsApp Agent" }}</span>
			</div>
		</div>
	</nav>
</template>

<script setup>
import { computed } from "vue";
import { store } from "../api.js";

const counts = computed(() => store.boot?.counts || {});
const user = computed(() => store.boot?.user);
</script>

<style scoped>
.side { flex: 0 0 248px; background: var(--panel); border-right: 1px solid var(--line); padding: 16px 12px; display: flex; flex-direction: column; gap: 4px; min-height: 100vh; position: sticky; top: 0; height: 100vh; overflow-y: auto; }
.brand { display: flex; align-items: center; gap: 10px; padding: 6px 10px 18px; }
.logo { width: 30px; height: 30px; border-radius: 8px; background: var(--green); display: flex; align-items: center; justify-content: center; flex: 0 0 auto; }
.brand-text { display: flex; flex-direction: column; }
.name { font-weight: 700; font-size: 15px; }
.links { display: flex; flex-direction: column; gap: 4px; }
.link { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; color: #3d3d3d; text-decoration: none; font-size: 14px; min-height: 38px; }
.link svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; flex: 0 0 auto; }
.link:hover { background: var(--hover); color: var(--ink); }
.link.on { background: #fff; color: var(--ink); font-weight: 600; box-shadow: 0 1px 2px rgba(0, 0, 0, .08); }
.badge { margin-left: auto; font-size: 12px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: var(--green-soft); color: var(--green-dark); }
.me { display: flex; align-items: center; gap: 10px; padding: 10px; border-top: 1px solid var(--line); margin-top: 8px; }
.avatar { width: 28px; height: 28px; border-radius: 999px; background: #d9e7dd; color: var(--green-dark); font-weight: 700; font-size: 12px; display: flex; align-items: center; justify-content: center; }
@media (max-width: 760px) {
	.side { position: static; height: auto; min-height: 0; flex: 0 0 auto; flex-direction: row; align-items: center; overflow-x: auto; padding: 8px; border-right: 0; border-bottom: 1px solid var(--line); }
	.brand { padding: 0 6px 0 2px; }
	.brand-text, .me, .spacer { display: none; }
	.links { flex-direction: row; }
	.link { white-space: nowrap; }
}
</style>
