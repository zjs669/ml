<script setup lang="ts">
import { computed } from 'vue'

import GenericChartPage from './GenericChartPage.vue'
import { DOMAIN_FORMS, type DomainFormConfig } from '@/config/domainForms'

/**
 * 薄壳页的合并版：10 个同构域共用这一个组件。
 *
 * 为什么合并：原先 `AlmanacPage` / `XiaoliurenPage` / `MeihuaPage` … 是 10 个
 * 各 12 行的文件，内容只有「取哪个配置」一行不同。新增一个同构域要新建页面、
 * 加路由、加 import，三处都要动，而差异只有一个字符串。
 *
 * URL 不变：路由仍是 `/almanac`、`/xiaoliuren` …，只是指向同一组件，
 * 因此不存在外链失效，也不需要 redirect。
 *
 * 为什么用 props 而不是 `useRoute()`：`domain` 由路由表的
 * `props: (route) => ({ domain: route.meta.domain })` 直接传进来。
 * 这样组件不依赖路由注入，SSR 渲染冒烟（`scripts/check-routes.mjs`）才能跑，
 * 单测也能直接挂载它而不必造一个 router。
 */
const props = defineProps<{ domain: string }>()

const config = computed<DomainFormConfig>(() => {
  const found = DOMAIN_FORMS[props.domain]
  if (!found) {
    // 路由传了未知域时立刻炸，避免静默渲染空白页
    throw new Error(`config/domainForms.ts 里没有 ${props.domain} 的表单配置`)
  }
  return found
})
</script>

<template>
  <GenericChartPage :config="config" />
</template>
