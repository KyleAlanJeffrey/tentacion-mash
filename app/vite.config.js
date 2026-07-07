import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api and /images proxy to production during local dev, so `npm run dev`
// shows the live timeline; local-generated files in public/ still win as
// a fallback when offline.
export default defineConfig({
  plugins: [react()],
  css: { preprocessorOptions: { scss: { api: "modern-compiler" } } },
  server: {
    proxy: {
      "/api": { target: "https://xxx5050.com", changeOrigin: true },
      "/images": { target: "https://xxx5050.com", changeOrigin: true },
    },
  },
});
