import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `vite build` makes the standalone app served by maps4drone-web; `--mode webodm` makes the
// WebODM plugin's UI, served by WebODM under /plugins/maps4drone/ (see .env.webodm).
export default defineConfig(({ mode }) => {
  const webodm = mode === "webodm";
  return {
    plugins: [react()],
    base: webodm ? "/plugins/maps4drone/" : "/",
    build: webodm
      ? { outDir: "dist-webodm", emptyOutDir: true }
      : { outDir: "../src/maps4drone/web/static", emptyOutDir: true },
    server: {
      proxy: { "/api": process.env.MAPS4DRONE_API ?? "http://127.0.0.1:8000" },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
    },
  };
});
