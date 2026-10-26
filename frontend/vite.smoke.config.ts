import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

/**
 * 冒烟专用配置：关掉依赖预打包（optimizeDeps）。
 *
 * 为什么需要单独一份：vite-node 默认复用主配置，会把 vue 预打包到
 * `node_modules/.vite/deps/vue.js`，而 SFC 组件又按源码路径 import vue ——
 * 于是运行时有两份 Vue 实例，`renderSlot` 拿到 null 实例直接抛
 * `Cannot read properties of null (reading 'ce')`。
 * SSR 冒烟不需要预打包，关掉即可保证单实例。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    noDiscovery: true,
    include: [],
  },
  ssr: {
    noExternal: ['element-plus'],
  },
})
