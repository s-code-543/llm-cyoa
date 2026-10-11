import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base:
    process.env.NODE_ENV === "production" ? "/static/frontend/" : "/frontend/",
  server: {
    port: 5173,
    strictPort: true,
    hmr: { clientPort: 8001, path: "hmr" },
  },
  build: { manifest: true, rollupOptions: { input: "src/main.tsx" } },
});
