import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = env.VITE_BACKEND_URL || "http://127.0.0.1:8100";

  return {
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
  };
});
