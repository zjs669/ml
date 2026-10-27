<script setup lang="ts">
import { computed, defineAsyncComponent, type Component } from 'vue'

import GenericBoard from './GenericBoard.vue'
import type { ChartResult } from '@/api/types'

/**
 * 盘面分发器：按 `result.domain` 选择对应的盘面组件。
 * 各术数的 `ChartResult` 外壳一致，差异只在 `chart_facts` 的形状，
 * 因此这里只做分发，不复制任何排盘逻辑。
 *
 * 为什么用 `defineAsyncComponent` 而不是静态 import：
 * 九个专属盘面合计约 3800 行（ZiweiBoard 994、BaziBoard 661、QimenBoard 419…），
 * 静态引入会让「打开首页」也下载全部域的渲染逻辑。用户一次只看一个域的盘，
 * 按域异步加载后首屏只下载 GenericBoard（兜底用，224 行）。
 *
 * `GenericBoard` 保持静态引入：它是兜底组件，任何域都可能用到，
 * 再包一层异步只会给兜底路径增加一次网络往返。
 */
const props = defineProps<{
  result: ChartResult
  /** 关系列表是否展开（分享预览可关掉以减小体积） */
  showRelations?: boolean
}>()

/** 已有专属可视化的域。新增域先落到 GenericBoard，专属组件就绪后再登记到这里。 */
const BOARDS: Record<string, Component> = {
  bazi: defineAsyncComponent(() => import('./BaziBoard.vue')),
  ziwei: defineAsyncComponent(() => import('./ZiweiBoard.vue')),
  liuyao: defineAsyncComponent(() => import('./LiuyaoBoard.vue')),
  qimen: defineAsyncComponent(() => import('./QimenBoard.vue')),
  almanac: defineAsyncComponent(() => import('./AlmanacBoard.vue')),
  tarot: defineAsyncComponent(() => import('./TarotBoard.vue')),
  daliuren: defineAsyncComponent(() => import('./DaliurenBoard.vue')),
  astrology: defineAsyncComponent(() => import('./AstrologyBoard.vue')),
  meihua: defineAsyncComponent(() => import('./MeihuaBoard.vue')),
}

const board = computed<Component>(() => BOARDS[props.result.domain] ?? GenericBoard)
</script>

<template>
  <component :is="board" :result="result" :show-relations="showRelations" />
</template>
