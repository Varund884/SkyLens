import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // The API runs on :8000 in development; calling /api/... from the browser
    // keeps one origin, so there are no CORS surprises here or in production.
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') } },
  },
})
