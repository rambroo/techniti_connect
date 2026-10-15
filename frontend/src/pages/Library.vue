<template>
	<main class="main">
		<header class="page-head">
			<div class="titles">
				<h1>Library</h1>
				<span class="muted">Everything that can be posted. Automatic items appear here before you approve them.</span>
			</div>
			<button class="btn" @click="openAdd">Add content</button>
			<button v-if="isManager" class="btn primary" @click="gen.open = true">Generate now</button>
		</header>

		<div class="row">
			<div class="row" role="tablist" aria-label="Type">
				<button v-for="t in ['', 'Photo', 'Video', 'Reel']" :key="t" class="pill" :class="{ on: f.type === t }" role="tab"
					:aria-selected="f.type === t" @click="f.type = t; load()">{{ t || "All" }}</button>
			</div>
			<span class="grow"></span>
			<label class="field" style="flex-direction: row; align-items: center; gap: 8px">Source
				<select v-model="f.source" @change="load()" style="width: auto">
					<option value="">All sources</option><option value="Quote Card">Quote cards</option>
					<option value="Pexels">Pexels</option><option value="YouTube">YouTube</option><option value="Uploaded">Uploaded</option>
				</select>
			</label>
			<label class="field" style="flex-direction: row; align-items: center; gap: 8px">Group
				<select v-model="f.group" @change="load()" style="width: auto">
					<option value="">All groups</option>
					<option v-for="g in groupNames" :key="g" :value="g">{{ g }}</option>
				</select>
			</label>
			<label class="field" style="flex-direction: row; align-items: center; gap: 8px">Status
				<select v-model="f.status" @change="load()" style="width: auto">
					<option value="Active">Active</option><option value="Retired">Retired</option><option value="">All</option>
				</select>
			</label>
		</div>

		<div v-if="loading" class="row"><div class="spinner"></div><span class="muted">Loading…</span></div>
		<div v-else-if="!items.length" class="empty">
			<p>No content yet. Add some, or turn on automatic content for a group.</p>
		</div>
		<div v-else class="grid grid-4">
			<article v-for="it in items" :key="it.name" class="card tile">
				<MediaPreview :content="it" :dim="it.status === 'Retired'" />
				<div class="body">
					<span class="title">{{ it.title }}</span>
					<div class="row" style="gap: 6px">
						<span v-if="it.planned_for" class="chip amber">Planned {{ fmtDate(it.planned_for) }}</span>
						<span v-else-if="it.status === 'Retired'" class="chip grey">Retired</span>
						<span v-else-if="it.times_used" class="chip grey">Posted {{ it.times_used }}×</span>
						<span v-else class="chip green">Ready</span>
					</div>
					<span class="xs muted">{{ it.groups.length ? it.groups.join(", ") : "Any group" }}</span>
					<div class="row" style="margin-top: auto">
						<button v-if="it.status === 'Active'" class="btn sm" @click="setStatus(it, 'Retired')">Retire</button>
						<button v-else class="btn sm" @click="setStatus(it, 'Active')">Restore</button>
						<a class="btn sm" :href="`/app/group-content/${it.name}`">Open</a>
					</div>
				</div>
			</article>
		</div>
		<div v-if="items.length >= 48 && !loading" class="row" style="justify-content: center">
			<button class="btn" @click="more">Load more</button>
		</div>

		<div v-if="add.open" class="modal-back" @click.self="add.open = false">
			<form class="modal" @submit.prevent="saveAdd">
				<h2>Add content</h2>
				<div class="row" role="tablist">
					<button type="button" v-for="t in ['Photo', 'Video', 'Reel']" :key="t" class="pill" :class="{ on: add.type === t }"
						@click="add.type = t">{{ t }}</button>
				</div>
				<label class="field">Title<input type="text" v-model="add.title" required></label>
				<label class="field" v-if="add.type !== 'Reel'">{{ add.type === "Photo" ? "Photo (JPG/PNG, up to 5 MB)" : "Video (MP4, up to 16 MB)" }}
					<input type="file" :accept="add.type === 'Photo' ? 'image/jpeg,image/png,image/webp' : 'video/mp4'" @change="add.file = $event.target.files[0]">
				</label>
				<label class="field">{{ add.type === "Photo" ? "or a link" : "Link (Instagram reel / YouTube)" }}
					<input type="url" v-model="add.link" placeholder="https://…">
				</label>
				<label class="field">Caption<textarea rows="3" v-model="add.caption"></textarea></label>
				<label class="field">Only for group
					<select v-model="add.group"><option value="">Any group</option><option v-for="g in groupNames" :key="g">{{ g }}</option></select>
				</label>
				<div class="row" style="justify-content: flex-end">
					<button type="button" class="btn" @click="add.open = false">Cancel</button>
					<button class="btn primary" :disabled="add.saving">{{ add.saving ? "Saving…" : "Add" }}</button>
				</div>
			</form>
		</div>

		<div v-if="gen.open" class="modal-back" @click.self="gen.open = false">
			<form class="modal" @submit.prevent="runGenerate">
				<h2>Generate content</h2>
				<p class="small muted">Makes one new item now using the group's theme: a quote card for photos, a Pexels clip or YouTube link for videos and reels.</p>
				<label class="field">Group
					<select v-model="gen.group" required><option v-for="g in groupNames" :key="g">{{ g }}</option></select>
				</label>
				<div class="row" role="tablist">
					<button type="button" v-for="t in ['Photo', 'Video', 'Reel']" :key="t" class="pill" :class="{ on: gen.type === t }"
						@click="gen.type = t">{{ t }}</button>
				</div>
				<div class="row" style="justify-content: flex-end">
					<button type="button" class="btn" @click="gen.open = false">Cancel</button>
					<button class="btn primary" :disabled="gen.running">{{ gen.running ? "Working…" : "Generate" }}</button>
				</div>
			</form>
		</div>
	</main>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import MediaPreview from "../components/MediaPreview.vue";
import { call, fmtDate, store, toast, upload } from "../api.js";

const isManager = computed(() => store.boot?.is_manager);
const f = reactive({ type: "", source: "", group: "", status: "Active" });
const items = ref([]);
const loading = ref(true);
const groupNames = ref([]);
const add = reactive({ open: false, type: "Photo", title: "", file: null, link: "", caption: "", group: "", saving: false });
const gen = reactive({ open: false, group: "", type: "Photo", running: false });

async function load(append = false) {
	if (!append) loading.value = true;
	try {
		const rows = await call("library", {
			content_type: f.type, source: f.source, group: f.group, status: f.status, start: append ? items.value.length : 0,
		});
		items.value = append ? items.value.concat(rows) : rows;
	} catch (e) {
		toast(e.message, "err");
	}
	loading.value = false;
}
const more = () => load(true);

async function setStatus(it, status) {
	try {
		it.status = await call("set_content_status", { name: it.name, status }, { post: true });
		toast(status === "Retired" ? "Retired: it won't be proposed again" : "Restored");
	} catch (e) {
		toast(e.message, "err");
	}
}
function openAdd() {
	Object.assign(add, { open: true, type: "Photo", title: "", file: null, link: "", caption: "", group: f.group, saving: false });
}
async function saveAdd() {
	add.saving = true;
	try {
		const file = add.file && add.type !== "Reel" ? await upload(add.file) : null;
		if (!file && !add.link) throw new Error("Choose a file or paste a link.");
		await call("add_content", {
			title: add.title, content_type: add.type, file, link: add.link, caption: add.caption, group: add.group,
		}, { post: true });
		add.open = false;
		toast("Added to the library");
		load();
	} catch (e) {
		toast(e.message, "err");
	}
	add.saving = false;
}
async function runGenerate() {
	gen.running = true;
	try {
		await call("generate", { group: gen.group, content_type: gen.type }, { post: true });
		gen.open = false;
		toast("Created");
		load();
	} catch (e) {
		toast(e.message, "err");
	}
	gen.running = false;
}
onMounted(async () => {
	load();
	try {
		const g = await call("groups");
		groupNames.value = g.groups.map((x) => x.name);
		gen.group = groupNames.value[0] || "";
	} catch (e) {
		/* groups are optional for filtering */
	}
});
</script>

<style scoped>
.tile { overflow: hidden; display: flex; flex-direction: column; }
.body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 6px; flex-grow: 1; }
.title { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
