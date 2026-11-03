// Сборка (Vite) и тесты (Vitest) — D-047, D-052.
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Для `npm run dev`: запросы /api уходят на backend (основной запуск — nginx, D-048).
    proxy: { '/api': { target: 'http://localhost:8000', ws: true } },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.js'],
    setupFiles: ['src/test/setup.js'],
    restoreMocks: true,
  },
})
