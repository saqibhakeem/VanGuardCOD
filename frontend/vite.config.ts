import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const backend = "https://consult-amicably-studied.ngrok-free.dev";

export default defineConfig(({ mode }) => ({
  base: mode === "production" ? "/console/" : "/",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend, ws: true, changeOrigin: true },
      "/softphone": { target: backend, changeOrigin: true },
      "/health": { target: backend, changeOrigin: true },
      "/docs": { target: backend, changeOrigin: true },
      "/openapi.json": { target: backend, changeOrigin: true },
    },
  },
}));
