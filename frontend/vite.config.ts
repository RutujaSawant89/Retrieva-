import { fileURLToPath, URL } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Same-origin API in development so the httpOnly refresh cookie (SameSite=Strict) works.
    proxy: {
      '/api': { target: apiTarget, changeOrigin: false },
      '/health': { target: apiTarget },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (/recharts|d3-/.test(id)) return 'charts'
          if (/react-markdown|remark|micromark|mdast|unified|hast/.test(id)) return 'markdown'
          if (/react-dom|react-router|[\\/]react[\\/]/.test(id)) return 'react'
          return undefined
        },
      },
    },
  },
})
