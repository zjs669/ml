<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult, DaliurenFacts } from '@/api/types'

/**
 * 大六壬盘面：天地盘十二宫 + 四课 + 三传。
 *
 * 盘面读法是三层结构，不能只写一层：
 *   地盘某宫 → 天盘某支 → 临某将
 * 因此每个宫位格子里同时显示地盘支、天盘支与天将。
 *
 * 三传未判定时**不留空白**，而是把原因写在原位 —— 空白会让人以为「忘了渲染」。
 */
const props = defineProps<{ result: ChartResult }>()

const facts = computed(() => props.result.chart_facts as unknown as DaliurenFacts)

/** 地盘十二宫按传统方位排：子上、丑寅卯辰巳午未申酉戌亥顺时针 */
const ORDER = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

const plate = computed(() => {
  const byEarth = Object.fromEntries(facts.value.plate.map((row) => [row.earth, row]))
  return ORDER.map((earth) => byEarth[earth]).filter(Boolean)
})

const lessons = computed(() => facts.value.four_lessons)

const chuan = computed(() => facts.value.san_chuan)
const status = computed(() => facts.value.san_chuan_status)

const chuanRows = computed(() => {
  const value = chuan.value
  if (!value) return []
  return [
    { label: '初传', item: value.first },
    { label: '中传', item: value.middle },
    { label: '末传', item: value.last },
  ]
})

const dayNightLabel = computed(() => (facts.value.day_night.value === 'day' ? '昼' : '夜'))
</script>

<template>
  <div class="daliuren-board">
    <div class="head">
      <div class="title">
        <span class="general">
          月将 {{ facts.month_general.branch }}（{{ facts.month_general.name }}）
        </span>
        <span class="sub">{{ facts.datetime.solar }} · {{ facts.datetime.hour_branch }}</span>
      </div>
      <div class="tags">
        <el-tag size="small" effect="plain">
          {{ dayNightLabel }}用{{ facts.shen_sha.gui_ren.used }}
        </el-tag>
        <el-tag size="small" effect="plain">建除 {{ facts.shen_sha.jian_chu }}</el-tag>
        <el-tag size="small" effect="plain">天马 {{ facts.shen_sha.tian_ma }}</el-tag>
        <el-tag v-if="facts.month_general.source === 'manual'" size="small" type="warning" effect="plain">
          手工指定
        </el-tag>
      </div>
    </div>

    <div class="pillars">
      <span v-for="(value, key) in facts.pillars" :key="key" class="pillar">
        <em>{{ { year: '年', month: '月', day: '日', hour: '时' }[key] }}</em>{{ value }}
      </span>
      <span class="pillar muted">日干寄宫 {{ facts.shen_sha.lodge }}</span>
    </div>

    <section class="plate">
      <h4>天地盘</h4>
      <div class="cells">
        <div v-for="row in plate" :key="row.earth" class="cell">
          <div class="earth">{{ row.earth }}</div>
          <div class="sky">{{ row.sky }}</div>
          <div class="general-name">{{ row.general ?? '—' }}</div>
        </div>
      </div>
      <p class="legend">每格自上而下：地盘支 → 天盘支 → 所临天将</p>
    </section>

    <div class="two-col">
      <section>
        <h4>四课</h4>
        <table>
          <thead>
            <tr>
              <th>课</th>
              <th>上神</th>
              <th>下神</th>
              <th>上下五行</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="lesson in lessons" :key="lesson.index">
              <td>{{ ['一', '二', '三', '四'][lesson.index - 1] }}课</td>
              <td class="gz">{{ lesson.upper }}</td>
              <td class="gz">{{ lesson.lower }}</td>
              <td class="muted">{{ lesson.upper_element }} / {{ lesson.lower_element }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section>
        <h4>三传</h4>
        <template v-if="chuan">
          <table>
            <thead>
              <tr>
                <th>传</th>
                <th>支</th>
                <th>天将</th>
                <th>五行</th>
                <th>长生</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in chuanRows" :key="row.label">
                <td>{{ row.label }}</td>
                <td class="gz">{{ row.item.branch }}</td>
                <td>{{ row.item.general ?? '—' }}</td>
                <td class="muted">{{ row.item.element ?? '—' }}</td>
                <td class="muted">{{ row.item.chang_sheng ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p class="legend">取法：{{ chuan.method }}</p>
        </template>
        <div v-else class="unimplemented">
          <el-alert type="warning" :closable="false" show-icon title="三传未判定" />
          <p class="reason">{{ status.reason }}</p>
          <p v-if="status.candidates.length" class="legend">
            候选：{{ status.candidates.map((item) => `${item.index}课 ${item.text}`).join('、') }}
          </p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.daliuren-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--xs-border);
}

.title {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.general {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 22px;
  color: var(--xs-accent);
}

.sub {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-left: auto;
}

.pillars {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 15px;
}

.pillar em {
  font-style: normal;
  font-size: 11px;
  color: var(--xs-text-muted);
  margin-right: 3px;
}

.pillar.muted {
  font-family: inherit;
  font-size: 12px;
  color: var(--xs-text-muted);
}

section h4 {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--xs-text-muted);
  font-weight: 600;
}

.cells {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.cell {
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  background: var(--xs-surface);
  padding: 8px 4px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.earth {
  font-size: 10px;
  color: var(--xs-text-muted);
}

.sky {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 18px;
  color: var(--xs-text);
}

.general-name {
  font-size: 11px;
  color: var(--xs-accent);
}

.legend {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.two-col {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

th,
td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--xs-border);
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--xs-text-muted);
  font-weight: 600;
}

.gz {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 14px;
}

td.muted {
  color: var(--xs-text-muted);
}

.unimplemented .reason {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.8;
  color: var(--xs-text-muted);
}

@media (max-width: 1100px) {
  .cells {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .two-col {
    grid-template-columns: 1fr;
  }
}
</style>
