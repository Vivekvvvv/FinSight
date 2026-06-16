import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath, URL } from 'node:url';

// FinSight Vue dev server.
// 默认端口 5174, API 默认指向 FastAPI 8000。
export default defineConfig({
  plugins: [
    vue(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'logo.svg', 'icons/*.png'],
      manifest: {
        name: 'FinSight AI 智能金融研究终端',
        short_name: 'FinSight',
        description: '智能金融研究终端 - A股数据可视化与AI研究助手',
        theme_color: '#0066cc',
        background_color: '#0d0d0d',
        display: 'standalone',
        orientation: 'any',
        start_url: '/',
        scope: '/',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // 离线缓存策略
        globPatterns: ['**/*.{js,css,html,ico,svg}'],
        runtimeCaching: [
          {
            // API请求：network first，超时3s降级缓存
            urlPattern: /^http:\/\/127\.0\.0\.1:8000\/api\//,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              networkTimeoutSeconds: 3,
              expiration: { maxAgeSeconds: 300 },
            },
          },
          {
            // 静态资源：cache first
            urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp|woff2?)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'assets-cache',
              expiration: { maxEntries: 60, maxAgeSeconds: 86400 * 7 },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
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
          'vendor-echarts': ['echarts', 'vue-echarts'],
          'vendor-vue': ['vue', 'vue-router', 'pinia'],
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
