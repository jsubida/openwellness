/// <reference types="vitest/config" />
import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  // Optional dev proxy — uncomment to call the API same-origin through Vite
  // instead of relying on backend CORS (then set VITE_API_BASE_URL=/v1).
  // server: {
  //   proxy: {
  //     '/v1': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  //   },
  // },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
})
