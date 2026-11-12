import { networkInterfaces } from 'node:os'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const PORT = 5173

// changeOrigin: Django only accepts its own host names, and a phone reaches this server by the PC's Wi-Fi address.
const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
}

/**
 * This PC's address on the Wi-Fi, so QR codes made while running locally open on a phone
 * instead of pointing at "localhost". LAN_HOST overrides the guess.
 */
function lanOrigin() {
  if (process.env.VERCEL) return '' // a hosted build is opened by its real address
  if (process.env.LAN_HOST) return `http://${process.env.LAN_HOST}:${PORT}`
  const virtual = /vethernet|virtualbox|vmware|wsl|docker|hyper-v|loopback|bluetooth/i
  const found: { name: string; address: string }[] = []
  for (const [name, addrs] of Object.entries(networkInterfaces())) {
    if (virtual.test(name)) continue
    for (const a of addrs ?? []) {
      // 192.168.56.x is VirtualBox's host-only network, which a phone can't reach.
      if (a.family === 'IPv4' && !a.internal && !a.address.startsWith('192.168.56.')) found.push({ name, address: a.address })
    }
  }
  const pick = found.find((f) => /wi-?fi|wlan|wireless/i.test(f.name)) ?? found[0]
  return pick ? `http://${pick.address}:${PORT}` : ''
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  define: { __LAN_ORIGIN__: JSON.stringify(lanOrigin()) },
  server: { port: PORT, host: true, proxy },
  // `npm run demo` serves the optimised production build — use it for presentations.
  preview: { port: PORT, host: true, proxy },
})
