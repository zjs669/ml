<script setup lang="ts">
import { computed } from 'vue'

import type { ChartFacts } from '@/api/types'

const props = defineProps<{
  counts: ChartFacts['five_elements_count']
}>()

const ELEMENTS = ['木', '火', '土', '金', '水'] as const

const rows = computed(() =>
  ELEMENTS.map((element) => ({
    element,
    raw: props.counts?.raw?.[element] ?? 0,
    weighted: props.counts?.weighted?.[element] ?? 0,
  })),
)

const maxWeighted = computed(() => Math.max(...rows.value.map((row) => row.weighted), 1))

const missing = computed(() => props.counts?.missing ?? [])
</script>

<template>
  <div class="element-block">
    <div class="block-head">
      <span class="title">五行分布</span>
      <el-tag size="small" effect="plain">口径 {{ counts?.weight_rule || 'weight-v1' }}</el-tag>
    </div>

    <div class="bars">
      <div v-for="row in rows" :key="row.element" class="bar-row">
        <span class="el-name">{{ row.element }}</span>
        <div class="track">
          <div
            class="fill"
            :class="`fill-${row.element}`"
            :style="{ width: `${Math.max((row.weighted / maxWeighted) * 100, 2)}%` }"
          />
        </div>
        <span class="numbers">{{ row.raw }} / {{ row.weighted }}</span>
      </div>
    </div>

    <div class="legend">
      原值 / 加权（天干 1.0、地支本气 1.0、中气 0.5、余气 0.3）
    </div>
    <div v-if="missing.length" class="missing">
      原值缺失：{{ missing.join('、') }}——缺口只陈述事实，不表示好坏。
    </div>
  </div>
</template>

<style scoped>
.element-block {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
}

.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.title {
  font-weight: 600;
}

.bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.el-name {
  flex: 0 0 20px;
  color: var(--xs-text-muted);
}

.track {
  flex: 1;
  height: 10px;
  border-radius: 999px;
  background: var(--xs-surface-muted);
  overflow: hidden;
}

.fill {
  height: 100%;
  border-radius: 999px;
  background: var(--xs-accent);
  transition: width 0.3s ease;
}

.fill-木 {
  background: #4c9a6d;
}
.fill-火 {
  background: #c8574e;
}
.fill-土 {
  background: #b0842f;
}
.fill-金 {
  background: #6b7b99;
}
.fill-水 {
  background: #3f7f9d;
}

.numbers {
  flex: 0 0 84px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--xs-text-muted);
}

.legend,
.missing {
  margin-top: 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.6;
}

.missing {
  color: #a45f22;
}
</style>
