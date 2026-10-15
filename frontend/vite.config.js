import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "../techniti_connect/public/frontend");
const wwwPage = path.resolve(here, "../techniti_connect/www/connect.html");

// After building, the generated index.html becomes the /connect page (rendered by Frappe, which
// fills in {{ csrf_token }}), the same way Frappe CRM serves /crm.
const copyIndexToWww = {
	name: "copy-index-to-www",
	closeBundle() {
		const src = path.join(outDir, "index.html");
		if (fs.existsSync(src)) fs.copyFileSync(src, wwwPage);
	},
};

export default defineConfig({
	base: "/assets/techniti_connect/frontend/",
	plugins: [vue(), copyIndexToWww],
	build: { outDir, emptyOutDir: true, target: "es2019", chunkSizeWarningLimit: 800 },
	server: {
		port: 8081,
		proxy: { "^/(app|api|assets|files|private|login)": "http://127.0.0.1:8015" },
	},
});
