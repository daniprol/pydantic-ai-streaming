import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tsconfigPaths from 'vite-tsconfig-paths'
// import { analyzer } from 'vite-bundle-analyzer'

// 8000 is quite common for backend, avoid the clash
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react(), tailwindcss(), tsconfigPaths({ root: __dirname })],
  build: {
    assetsDir: 'assets',
  },
  server: {
    proxy: {
      '/api': {
        target: API_BASE_URL,
        changeOrigin: true,
      },
    },
  },
}))
