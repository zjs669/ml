<script setup lang="ts">
import { computed, type Component } from 'vue'

import BaziBoard from './BaziBoard.vue'
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

const BOARDS: Record<string, Component> = {
  bazi: BaziBoard,
  ziwei: ZiweiBoard,
  liuyao: LiuyaoBoard,
  qimen: QimenBoard,
}

const board = computed<Component | null>(() => BOARDS[props.result.domain] ?? null)
</script>

<template>
  <component :is="board" v-if="board" :result="result" :show-relations="showRelations" />
  <div v-else class="board-missing">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      :title="`「${result.domain}」的盘面组件尚未接入`"
      description="计算已完成，但本版本还没有对应的可视化组件，可先参考下方计算提示。"
    />
    <ul v-if="result.warnings.length" class="missing-warnings">
      <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
    </ul>
  </div>
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
