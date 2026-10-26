<script setup lang="ts">
import { computed, type Component } from 'vue'

import AlmanacBoard from './AlmanacBoard.vue'
import BaziBoard from './BaziBoard.vue'
import DaliurenBoard from './DaliurenBoard.vue'
import GenericBoard from './GenericBoard.vue'
import TarotBoard from './TarotBoard.vue'
import ZiweiBoard from './ZiweiBoard.vue'
import LiuyaoBoard from './LiuyaoBoard.vue'
import QimenBoard from './QimenBoard.vue'
import type { ChartResult } from '@/api/types'

/**
 * 盘面分发器：按 `result.domain` 选择对应的盘面组件。
 * 四个术数的 `ChartResult` 外壳一致，差异只在 `chart_facts` 的形状，
 * 因此这里只做分发，不复制任何排盘逻辑。
 *
 * 新增术数时：写一个 Board 组件并登记到 `BOARDS`，各调用页无需改动。
 */
const props = defineProps<{
  result: ChartResult
  /** 关系列表是否展开（分享预览可关掉以减小体积） */
  showRelations?: boolean
}>()

/** 已有专属可视化的域。新增域先落到 GenericBoard，专属组件就绪后再登记到这里。 */
const BOARDS: Record<string, Component> = {
  bazi: BaziBoard,
  ziwei: ZiweiBoard,
  liuyao: LiuyaoBoard,
  qimen: QimenBoard,
  almanac: AlmanacBoard,
  tarot: TarotBoard,
  daliuren: DaliurenBoard,
}

const board = computed<Component>(() => BOARDS[props.result.domain] ?? GenericBoard)
</script>

<template>
  <component :is="board" :result="result" :show-relations="showRelations" />
</template>

<style scoped>
.board-missing {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.missing-warnings {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.8;
}
</style>
