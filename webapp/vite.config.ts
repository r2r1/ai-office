import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

// Сборка в static/webapp → FastAPI отдаёт это на /webapp (старый / не трогаем).
// base /webapp/ — чтобы пути к assets резолвились при отдаче из FastAPI.
// dev-сервер проксирует /api, /events, /auth на FastAPI (8000), чтобы cookie+SSE работали.
export default defineConfig({
  plugins: [react()],
  base: "/webapp/",
  build: {
    outDir: "../static/webapp",
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8000",
      "/events": { target: "http://localhost:8000", changeOrigin: true },
      "/auth": "http://localhost:8000",
      "/site": "http://localhost:8000",
    },
  },
})
