import { createRouter, createWebHistory } from "vue-router";

const routes = [
	{ path: "/", name: "home", component: () => import("./pages/Home.vue") },
	{ path: "/approvals", name: "approvals", component: () => import("./pages/Approvals.vue") },
	{ path: "/inbox/:phone?", name: "inbox", component: () => import("./pages/Inbox.vue") },
	{ path: "/library", name: "library", component: () => import("./pages/Library.vue") },
	{ path: "/groups", name: "groups", component: () => import("./pages/Groups.vue") },
	{ path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({ history: createWebHistory("/connect"), routes });
