import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The production build goes straight into the Python package, so arena_web.py serves it without Node
const outDir = fileURLToPath(new URL("../src/laya_agent/viewer/app_dist", import.meta.url));
// Dev server proxies the API to a running arena_web.py (default port 8771, override with LAYA_API)
const api = process.env.LAYA_API ?? "http://127.0.0.1:8771";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir,
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": api },
  },
});
