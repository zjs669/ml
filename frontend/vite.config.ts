import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        // 开发期把 /api 转发到后端，前端代码里始终用相对路径
        '/api': {
          target,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      // element-plus 单独成块后仍有约 900KB（组件库本身的成本），放宽阈值避免噪声告警
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          // Element Plus 体积大，单独切块，避免首屏 chunk 超过 1MB
          manualChunks: {
            vue: ['vue', 'vue-router', 'pinia'],
            element: ['element-plus'],
          },
        },
      },
    },
  }
})
