// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // En dev : redirige /packs/* vers le backend FastAPI
      // Permet d'éviter les problèmes CORS sans modifier le backend
      "/packs":      "http://localhost:8000",
      "/properties": "http://localhost:8000",
      "/health":     "http://localhost:8000",
    },
  },
});
