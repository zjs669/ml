<script setup lang="ts">
/**
 * 页面外壳：统一页头与内容间距。
 *
 * 原先有两种写法 —— 旧页面用 `.intro h2/.intro p`，新页面用 `.page-head h2/.page-head p`，
 * CSS 规则几乎相同却在 17 个文件里各写一遍。改一次字号要改 17 处，还容易漏。
 *
 * 现在：页头只写一次，各页面传 `title` / `desc` 即可。
 *
 * 只有一个默认插槽：具名插槽在 SSR 渲染冒烟里会走 `renderSlot`，
 * 而 vite-node 下 vue 有双实例问题，没有实际使用者的插槽不值得留。
 */
defineProps<{
  title: string
  /** 一句话说明 */
  desc?: string
}>()
</script>

<template>
  <div class="page-shell">
    <header class="page-head">
      <h2>{{ title }}</h2>
      <p v-if="desc">{{ desc }}</p>
    </header>

    <slot />
  </div>
</template>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head h2 {
  margin: 0 0 6px;
  font-size: 20px;
  letter-spacing: 0.5px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
  max-width: 780px;
}
</style>
