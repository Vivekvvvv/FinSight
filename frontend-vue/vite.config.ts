import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath, URL } from 'node:url';

// FinSight Vue dev server.
// 默认端口 5174, API 默认指向 FastAPI 8000。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    include: [
      'echarts/core',
      'echarts/renderers',
      'echarts/charts',
      'echarts/components',
      'vue-echarts',
    ],
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // echarts 单独包（最大，约 700KB gzip 前）
          'vendor-echarts': ['echarts', 'vue-echarts'],
          // Vue 生态
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
          // axios
          'vendor-http': ['axios'],
        },
      },
    },
    chunkSizeWarningLimit: 800,
  },
  server: {
    port: 5174,
    strictPort: true,
    host: true,
  },
  preview: {
    port: 5174,
  },
});
