import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // Cloudflare Quick Tunnels generate a temporary *.trycloudflare.com hostname.
  // Permit only that trusted suffix for live demo previews; local development
  // remains unchanged.
  server: {
    allowedHosts: ['.trycloudflare.com'],
  },
})
