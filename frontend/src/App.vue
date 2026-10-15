<template>
	<div v-if="store.error" class="main" style="max-width: 560px; margin: 60px auto">
		<h1>Techniti Connect</h1>
		<p class="muted">{{ store.error }}</p>
		<a class="btn" href="/app">Back to desk</a>
	</div>
	<div v-else class="layout">
		<Sidebar />
		<router-view v-if="store.boot" :key="$route.name" />
		<div v-else class="main" style="align-items: center; justify-content: center"><div class="spinner"></div></div>
	</div>
	<div v-if="store.toast" class="toast" :class="{ err: store.toast.kind === 'err' }" role="status">{{ store.toast.text }}</div>
</template>

<script setup>
import { onMounted } from "vue";
import Sidebar from "./components/Sidebar.vue";
import { call, store } from "./api.js";

onMounted(async () => {
	try {
		store.boot = await call("boot");
	} catch (e) {
		store.error = e.message;
	}
});
</script>
