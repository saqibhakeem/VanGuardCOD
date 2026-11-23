import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const backend = env.VITE_BACKEND_URL || "http://127.0.0.1:8100";

  const createProxyTarget = (isWs = false) => ({
    target: backend,
    changeOrigin: true,
    secure: false,
    ws: isWs,
    configure: (proxy: any) => {
      proxy.on("proxyReq", (proxyReq: any) => {
        proxyReq.setHeader("ngrok-skip-browser-warning", "true");
      });
    },
  });

  return {
    base: mode === "production" ? "/console/" : "/",
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        "/api": createProxyTarget(false),
        "/ws": createProxyTarget(true),
        "/softphone": createProxyTarget(false),
        "/health": createProxyTarget(false),
        "/docs": createProxyTarget(false),
        "/openapi.json": createProxyTarget(false),
      },
    },
  };
});
