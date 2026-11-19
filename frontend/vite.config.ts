/// <reference types="vitest/config" />
// Vite : React, Tailwind CSS et, en développement, un proxy /api -> API FastAPI (port 8000).
// Avec le proxy, le navigateur ne parle qu'à une seule origine (pas de CORS en développement).
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { configDefaults } from "vitest/config";

const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: API_TARGET,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: { host: "127.0.0.1", port: 4173 },
  build: { sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
    // Les parcours E2E (e2e/, Playwright) tournent contre la pile Docker : make e2e.
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
});
