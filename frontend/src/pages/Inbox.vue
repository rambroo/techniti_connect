<template>
	<div class="inbox">
		<section class="list" aria-label="Conversations">
			<h1 style="margin: 0 6px">Inbox</h1>
			<label class="field" style="margin: 0 6px">Search name or number
				<input type="search" v-model="search" @input="debounced" placeholder="e.g. 98200…">
			</label>
			<div class="row" style="margin: 0 6px" role="tablist">
				<button class="pill" :class="{ on: !onlyWaiting }" role="tab" :aria-selected="!onlyWaiting" @click="onlyWaiting = false; loadList()">All</button>
				<button class="pill" :class="{ on: onlyWaiting }" role="tab" :aria-selected="onlyWaiting" @click="onlyWaiting = true; loadList()">Waiting for reply</button>
			</div>
			<div class="convs">
				<p v-if="!convs.length && !loading" class="small muted" style="padding: 12px">No conversations.</p>
				<button v-for="c in convs" :key="c.phone" class="conv" :class="{ on: c.phone === phone }" @click="open(c.phone)">
					<span class="avatar" :class="{ donor: c.party_name }">{{ initials(c.name) }}</span>
					<span style="display: flex; flex-direction: column; min-width: 0; text-align: left">
						<span style="font-weight: 600">{{ c.name }}</span>
						<span class="small muted ell">{{ c.direction === "Out" ? "You: " : "" }}{{ c.text || c.template_name || `[${c.message_type}]` }}</span>
					</span>
					<span style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px">
						<span class="xs muted">{{ ago(c.at) }}</span>
						<span v-if="c.unanswered" class="dot" aria-label="Waiting for reply"></span>
					</span>
				</button>
			</div>
		</section>

		<section class="thread" aria-label="Conversation">
			<div v-if="!phone" class="empty" style="margin: 40px">Choose a conversation.</div>
			<template v-else-if="t">
				<header class="thead">
					<div style="display: flex; flex-direction: column; flex: 1 1 200px">
						<span style="font-size: 16px; font-weight: 700">{{ t.party?.party_label || `+${t.phone}` }}</span>
						<span class="small muted">+{{ t.phone }}{{ t.party?.party_name ? ` · ${t.party.party_doctype} ${t.party.party_name}` : "" }}</span>
					</div>
					<span class="chip" :class="t.window_open ? 'green' : 'amber'">{{ t.window_open ? `Reply window open until ${fmtTime(t.window_closes)}` : "Template only" }}</span>
				</header>
				<div ref="scroller" class="msgs">
					<div v-for="m in t.messages" :key="m.name" class="mrow" :class="m.direction === 'In' ? 'in' : 'out'">
						<div class="bubble">
							<b v-if="m.message_type === 'template'" class="small">{{ m.template_name || "Template" }}</b>
							<span>{{ m.text || (m.media_url ? `[${m.message_type}]` : "") }}</span>
							<span class="xs muted meta">{{ fmtDate(m.at, { day: "numeric", month: "short" }) }} {{ fmtTime(m.at) }}<template v-if="m.direction === 'Out'"> · {{ m.status }}</template></span>
							<span v-if="m.error && m.status === 'Failed'" class="xs" style="color: var(--red)">{{ m.error }}</span>
						</div>
					</div>
				</div>
				<footer class="foot">
					<form v-if="t.window_open" class="row" style="flex-wrap: nowrap; align-items: flex-end" @submit.prevent="sendReply">
						<label class="field grow">Reply<textarea rows="2" v-model="reply" placeholder="Type a reply…" @keydown.ctrl.enter="sendReply"></textarea></label>
						<button class="btn primary" :disabled="sending || !reply.trim()">{{ sending ? "Sending…" : "Send" }}</button>
					</form>
					<p v-else class="small" style="color: var(--amber); padding: 6px 2px">More than 24 hours since their last message. WhatsApp only allows an approved template now.</p>
				</footer>
			</template>
			<div v-else class="row" style="margin: 40px"><div class="spinner"></div></div>
		</section>

		<aside class="side" aria-label="Contact details" v-if="t && phone">
			<span class="xs muted caps">Linked record</span>
			<template v-if="t.party?.party_name">
				<span style="font-size: 16px; font-weight: 700">{{ t.party.party_label }}</span>
				<a class="small" :href="`/app/${slug(t.party.party_doctype)}/${encodeURIComponent(t.party.party_name)}`">Open {{ t.party.party_doctype }} {{ t.party.party_name }}</a>
				<dl class="facts" v-if="t.facts.length">
					<template v-for="f in t.facts" :key="f.k"><dt>{{ f.k }}</dt><dd>{{ f.v }}</dd></template>
				</dl>
			</template>
			<p v-else class="small muted">Not linked to a donor. Add this number to the Donor's contact number and it links automatically.</p>
			<p class="xs muted">Only safe details are shown here: never ID numbers or addresses.</p>
		</aside>
	</div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ago, call, fmtDate, fmtTime, refreshCounts, toast } from "../api.js";

const route = useRoute();
const router = useRouter();
const convs = ref([]);
const loading = ref(true);
const search = ref("");
const onlyWaiting = ref(false);
const phone = ref(route.params.phone || "");
const t = ref(null);
const reply = ref("");
const sending = ref(false);
const scroller = ref(null);
let timer = null;
let poll = null;

async function loadList() {
	try {
		convs.value = await call("conversations", { search: search.value, only_unanswered: onlyWaiting.value ? 1 : 0 });
		if (!phone.value && convs.value.length && window.innerWidth > 760) open(convs.value[0].phone);
	} catch (e) {
		toast(e.message, "err");
	}
	loading.value = false;
}
function debounced() {
	clearTimeout(timer);
	timer = setTimeout(loadList, 300);
}
async function loadThread(scroll = true) {
	if (!phone.value) return;
	try {
		t.value = await call("thread", { phone: phone.value });
		if (scroll) {
			await nextTick();
			if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
		}
	} catch (e) {
		toast(e.message, "err");
	}
}
function open(p) {
	if (p === phone.value && t.value) return;
	phone.value = p;
	t.value = null;
	router.replace(`/inbox/${p}`);
	loadThread();
}
async function sendReply() {
	if (!reply.value.trim()) return;
	sending.value = true;
	try {
		const r = await call("send", { phone: phone.value, text: reply.value }, { post: true });
		if (r.status === "Failed") toast(r.error || "Not sent", "err");
		reply.value = "";
		await loadThread();
		loadList();
		refreshCounts();
	} catch (e) {
		toast(e.message, "err");
	}
	sending.value = false;
}
const initials = (n) => (n || "?").replace("+", "").split(/\s+/).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
const slug = (dt) => (dt || "").toLowerCase().replace(/ /g, "-");

watch(() => route.params.phone, (p) => p && p !== phone.value && open(p));
onMounted(() => {
	loadList();
	if (phone.value) loadThread();
	// new messages arrive through the Sparklebot webhook; refresh every 20 seconds
	poll = setInterval(() => {
		loadList();
		loadThread(false);
	}, 20000);
});
onBeforeUnmount(() => clearInterval(poll));
</script>

<style scoped>
.inbox { flex: 1 1 auto; min-width: 0; display: flex; flex-wrap: wrap; min-height: 100vh; }
.list { flex: 1 1 300px; max-width: 340px; border-right: 1px solid var(--line); padding: 18px 12px; display: flex; flex-direction: column; gap: 12px; }
.convs { display: flex; flex-direction: column; gap: 2px; overflow-y: auto; }
.conv { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 12px; border-radius: 10px; width: 100%; border: 0; background: transparent; cursor: pointer; font-family: inherit; color: var(--ink); font-size: 14px; }
.conv:hover, .conv.on { background: var(--hover); }
.avatar { width: 36px; height: 36px; border-radius: 999px; background: #eef0f2; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.avatar.donor { background: #d9e7dd; color: var(--green-dark); }
.dot { width: 10px; height: 10px; border-radius: 999px; background: var(--green); }
.ell { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.thread { flex: 3 1 420px; min-width: 0; display: flex; flex-direction: column; background: var(--panel); min-height: 100vh; }
.thead { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 14px 20px; background: #fff; border-bottom: 1px solid var(--line); }
.msgs { flex-grow: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; max-height: calc(100vh - 170px); }
.mrow { display: flex; }
.mrow.out { justify-content: flex-end; }
.bubble { max-width: 70%; display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; border-radius: 12px; white-space: pre-line; line-height: 1.45; word-break: break-word; }
.mrow.in .bubble { background: #fff; border: 1px solid var(--line); }
.mrow.out .bubble { background: #dcf3e5; }
.meta { align-self: flex-end; }
.foot { background: #fff; border-top: 1px solid var(--line); padding: 12px 16px; }
.side { flex: 1 1 240px; max-width: 300px; border-left: 1px solid var(--line); padding: 18px; display: flex; flex-direction: column; gap: 10px; }
.caps { text-transform: uppercase; letter-spacing: .06em; }
.facts { margin: 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 12px; font-size: 13px; }
.facts dt { color: var(--muted); }
.facts dd { margin: 0; font-weight: 600; text-align: right; }
@media (max-width: 760px) {
	.list { max-width: none; }
	.thread { min-height: 70vh; }
	.side { max-width: none; border-left: 0; }
}
</style>
