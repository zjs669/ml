<script setup lang="ts">
import { computed } from 'vue'

import type { Position, ShenshaFacts } from '@/api/types'

/**
 * 神煞网格：按柱分列，只陈列「哪个神煞在哪一柱」。
 * 不排序好坏、不做吉凶评断；扩展口径（勾绞/童子）会有 variant 标记。
 */
const props = defineProps<{
  shensha: ShenshaFacts
  order: Position[]
}>()

const LABELS: Record<Position, string> = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' }

const columns = computed(() =>
  props.order.map((position) => ({
    position,
    label: LABELS[position],
    names: props.shensha.by_pillar?.[position] ?? [],
  })),
)
</script>

<template>
  <div class="shensha-grid">
    <div class="head">
      <span class="title">神煞</span>
      <span class="hint">
        只列落在哪一柱，不作吉凶判断{{ shensha.variant === 'extended' ? '（含扩展口径）' : '' }}
      </span>
    </div>
    <div class="cols">
      <div v-for="col in columns" :key="col.position" class="col">
        <div class="col-label">{{ col.label }}</div>
        <div class="chips">
          <span v-for="name in col.names" :key="name" class="chip">{{ name }}</span>
          <span v-if="!col.names.length" class="empty">—</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.shensha-grid {
  border: 1px solid var(--xs-border);
  border-radius: 14px;
  background: #fff;
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.title {
  font-weight: 600;
  font-size: 14px;
}

.hint {
  font-size: 11.5px;
  color: var(--xs-text-muted);
}

.cols {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.col {
  border-left: 2px solid var(--xs-surface-muted);
  padding-left: 10px;
  min-width: 0;
}

.col-label {
  font-size: 11.5px;
  color: var(--xs-text-muted);
  margin-bottom: 4px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chip {
  font-size: 11.5px;
  line-height: 1.6;
  padding: 0 6px;
  border-radius: 6px;
  background: linear-gradient(135deg, #f8f3e7, #f0e7d4);
  color: #7a5a2c;
  box-shadow: inset 0 0 0 1px rgba(138, 106, 59, 0.12);
}

.empty {
  color: #b7b0a4;
  font-size: 11.5px;
}

@media (max-width: 760px) {
  .cols {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
