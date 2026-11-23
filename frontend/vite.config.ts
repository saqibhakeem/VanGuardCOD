import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = env.VITE_BACKEND_URL || "http://127.0.0.1:8100";

  const proxyHeaders = {
    "ngrok-skip-browser-warning": "true",
  };

  return {
    base: mode === "production" ? "/console/" : "/",
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": { target: backend, changeOrigin: true, headers: proxyHeaders },
        "/ws": { target: backend, ws: true, changeOrigin: true, headers: proxyHeaders },
        "/softphone": { target: backend, changeOrigin: true, headers: proxyHeaders },
        "/health": { target: backend, changeOrigin: true, headers: proxyHeaders },
        "/docs": { target: backend, changeOrigin: true, headers: proxyHeaders },
        "/openapi.json": { target: backend, changeOrigin: true, headers: proxyHeaders },
      },
    },
  };
});
