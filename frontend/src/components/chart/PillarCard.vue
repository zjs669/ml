<script setup lang="ts">
import { computed } from 'vue'

import type { PillarFact } from '@/api/types'

const props = defineProps<{
  label: string
  pillar: PillarFact
  dayMaster?: string
}>()

const isDayMaster = computed(() => props.pillar.ten_god === '日主')

const elementClass = computed(() => {
  const map: Record<string, string> = {
    木: 'el-wood',
    火: 'el-fire',
    土: 'el-earth',
    金: 'el-metal',
    水: 'el-water',
  }
  return map[props.pillar.stem_element] ?? ''
})
</script>

<template>
  <div class="pillar-card" :class="elementClass">
    <div class="pillar-head">
      <span class="pillar-label">{{ label }}</span>
      <el-tag v-if="pillar.uncertain" size="small" type="warning" effect="plain">时辰不详</el-tag>
      <el-tag v-else-if="isDayMaster" size="small" effect="plain">日主</el-tag>
    </div>

    <div class="pillar-chars">
      <div class="char stem">
        <span class="char-text">{{ pillar.stem }}</span>
        <span class="char-meta">{{ pillar.stem_polarity }}{{ pillar.stem_element }}</span>
      </div>
      <div class="char branch">
        <span class="char-text">{{ pillar.branch }}</span>
        <span class="char-meta">{{ pillar.branch_element }}</span>
      </div>
    </div>

    <div class="pillar-body">
      <div class="row">
        <span class="key">十神</span>
        <span class="value">{{ pillar.ten_god }}</span>
      </div>
      <div class="row hidden">
        <span class="key">藏干</span>
        <span class="value">
          <span v-for="item in pillar.hidden_stems" :key="item.stem" class="hidden-item">
            {{ item.stem }}<sub>{{ item.level }}·{{ item.ten_god }}</sub>
          </span>
          <span v-if="!pillar.hidden_stems.length">—</span>
        </span>
      </div>
      <div class="row">
        <span class="key">纳音</span>
        <span class="value">{{ pillar.nayin || '—' }}</span>
      </div>
      <div class="row">
        <span class="key">空亡</span>
        <span class="value">{{ (pillar.xun_kong ?? []).join('、') || '—' }}</span>
      </div>
      <div class="row">
        <span class="key">地势</span>
        <span class="value">{{ pillar.dishi || '—' }}</span>
      </div>
      <div class="row">
        <span class="key">自坐</span>
        <span class="value">{{ pillar.zizuo || '—' }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pillar-card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.pillar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.pillar-label {
  font-size: 13px;
  color: var(--xs-text-muted);
  letter-spacing: 2px;
}

.pillar-chars {
  display: flex;
  gap: 12px;
}

.char {
  flex: 1;
  border-radius: 10px;
  background: var(--xs-surface-muted);
  padding: 10px 8px;
  text-align: center;
}

.char-text {
  display: block;
  font-size: 34px;
  line-height: 1.1;
  font-weight: 600;
  font-family: 'Songti SC', 'STSong', serif;
}

.char-meta {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.pillar-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12.5px;
}

.row {
  display: flex;
  gap: 8px;
}

.key {
  color: var(--xs-text-muted);
  flex: 0 0 36px;
}

.value {
  flex: 1;
  word-break: break-all;
}

.hidden-item {
  margin-right: 8px;
}

.hidden-item sub {
  font-size: 11px;
  color: var(--xs-text-muted);
  margin-left: 2px;
}

.el-wood .char.stem {
  color: #2f7d4f;
}
.el-wood .char.branch {
  color: #3f9b63;
}
.el-fire .char.stem {
  color: #b8433c;
}
.el-fire .char.branch {
  color: #d0625a;
}
.el-earth .char.stem {
  color: #9a6a24;
}
.el-earth .char.branch {
  color: #b58339;
}
.el-metal .char.stem {
  color: #4c5a75;
}
.el-metal .char.branch {
  color: #66748f;
}
.el-water .char.stem {
  color: #2b5f7d;
}
.el-water .char.branch {
  color: #3d7a99;
}
</style>
