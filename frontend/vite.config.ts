import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const dashboardPort = process.env.DASHBOARD_PORT || '38271'
const backendTarget = process.env.VITE_BACKEND_URL || `http://localhost:${dashboardPort}`
const websocketTarget = backendTarget.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: backendTarget,
        changeOrigin: true
      },
      '/ws': {
        target: websocketTarget,
        ws: true
      }
    }
  }
})
