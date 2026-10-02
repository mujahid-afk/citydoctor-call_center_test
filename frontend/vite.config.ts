import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only talks to this dev server; /api and /recordings are proxied
// to FastAPI, so no backend URL or credential ever ends up in frontend code.
const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/recordings": { target: backend, changeOrigin: true },
    },
  },
});
