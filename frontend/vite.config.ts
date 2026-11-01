import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const proxy = {
  '/api': 'http://127.0.0.1:8000',
  '/media': 'http://127.0.0.1:8000',
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 5173, host: true, proxy },
  // `npm run demo` serves the optimised production build — use it for presentations.
  preview: { port: 5173, host: true, proxy },
})
