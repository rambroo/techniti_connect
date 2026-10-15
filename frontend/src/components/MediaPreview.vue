<template>
	<div class="media" :class="{ dim }">
		<img v-if="kind === 'image'" :src="c.file" :alt="c.title || 'Photo'" loading="lazy" />
		<video v-else-if="kind === 'video'" :src="c.file" controls preload="metadata" :aria-label="c.title || 'Video'"></video>
		<a v-else-if="kind === 'youtube'" :href="c.link" target="_blank" rel="noopener" class="yt" :aria-label="`Open ${c.title || 'video'} on YouTube`">
			<img :src="ytThumb" alt="" loading="lazy" />
			<span class="play"><svg width="22" height="22" viewBox="0 0 24 24" fill="#1c1c1c" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg></span>
		</a>
		<a v-else-if="kind === 'link'" :href="c.link" target="_blank" rel="noopener" class="linkcard">
			<span class="xs" style="opacity: .8">{{ host }}</span>
			<span style="font-weight: 600">Open link</span>
		</a>
		<div v-else class="none">
			<span class="small">No content picked</span>
		</div>
		<span v-if="c" class="chip dark tag">{{ c.content_type }} · {{ c.auto_source || "Uploaded" }}</span>
		<slot />
	</div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({ content: { type: Object, default: null }, dim: Boolean });
const c = computed(() => props.content);

const ytId = computed(() => {
	const link = c.value?.link || "";
	const m = link.match(/(?:youtu\.be\/|v=|shorts\/)([\w-]{6,})/);
	return m ? m[1] : null;
});
const ytThumb = computed(() => (ytId.value ? `https://i.ytimg.com/vi/${ytId.value}/hqdefault.jpg` : ""));
const host = computed(() => {
	try {
		return new URL(c.value?.link).hostname.replace(/^www\./, "");
	} catch (e) {
		return "";
	}
});
const kind = computed(() => {
	if (!c.value) return "none";
	if (c.value.file) return c.value.content_type === "Photo" ? "image" : "video";
	if (ytId.value) return "youtube";
	if (c.value.link) return "link";
	return "none";
});
</script>

<style scoped>
.media { position: relative; aspect-ratio: 1 / 1; background: #1f2a26; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.media.dim { opacity: .45; }
.media img, .media video { width: 100%; height: 100%; object-fit: cover; display: block; background: #111; }
.yt { position: relative; width: 100%; height: 100%; display: block; }
.play { position: absolute; inset: 0; margin: auto; width: 56px; height: 56px; border-radius: 999px; background: rgba(255, 255, 255, .92); display: flex; align-items: center; justify-content: center; }
.linkcard { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; color: #fff; text-decoration: none; background: linear-gradient(160deg, #2a2a2a, #6b2d5c); }
.none { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; color: #6b7280; background: repeating-linear-gradient(45deg, #f4f4f2, #f4f4f2 10px, #ecece9 10px, #ecece9 20px); }
.tag { position: absolute; top: 10px; left: 10px; }
</style>
