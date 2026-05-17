import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: ["cody.danblanco.dev"],
    proxy: {
      "/query": "http://api:8000",
      "/repos": "http://api:8000",
      "/ingest": "http://api:8000",
    },
  },
});
