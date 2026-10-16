/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the UI proxies API calls to the local FastAPI service.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": "http://127.0.0.1:8000",
      "/healthz": "http://127.0.0.1:8000",
      "/readyz": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
