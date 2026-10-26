<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult } from '@/api/types'

/**
 * 通用盘面：把 `chart_facts` 按结构渲染成「分组 + 键值 + 列表」。
 *
 * 为什么需要它：新增的 10 个域各有专属的盘面形状（黄历是日级条目、塔罗是牌阵、
 * 大六壬是天地盘）。在没有专属可视化组件之前，先把事实如实呈现出来 ——
 * 这比让页面显示「盘面组件尚未接入」有用得多，也不会伪造任何可视化。
 *
 * 专属组件就绪后，在 `ChartBoard` 的 `BOARDS` 里登记即可覆盖本组件。
 */
const props = defineProps<{ result: ChartResult }>()

/** 字段名 → 中文标签。未登记的字段按原名展示（不猜译名）。 */
const LABELS: Record<string, string> = {
  date: '日期',
  datetime: '时刻',
  lunar_date: '农历',
  pillars: '四柱',
  month_general: '月将',
  day_night: '昼夜',
  plate: '天地盘',
  four_lessons: '四课',
  san_chuan: '三传',
  san_chuan_status: '三传状态',
  shen_sha: '神煞',
  layers: '层次',
  primary: '主层',
  mode: '主层类型',
  target: '目标',
  natal: '本命盘',
  transit_transformations: '逐层四化',
  query: '查询',
  answer: '结果',
  palace_transformations: '宫干四化全表',
  spread: '牌阵',
  deck: '牌池',
  draw: '抽牌',
  cards: '牌面',
  casting: '起卦',
  original: '本卦',
  mutual: '互卦',
  changed: '变卦',
  opposite: '错卦',
  reversed: '综卦',
  body_use: '体用',
  yi: '宜',
  ji: '忌',
  ji_shen: '吉神',
  xiong_sha: '凶煞',
  chong: '冲',
  sha_direction: '煞方',
  xiu: '星宿',
  nine_star: '九星',
  positions: '方位',
  hour_slots: '时辰',
  day_pillar: '日柱',
  personal: '个性化对照',
  shichen: '时辰',
  month_palace: '月宫',
  day_palace: '日宫',
  result_palace: '时宫（落点）',
  steps: '递推步骤',
  angles: '角度',
  planets: '行星',
  unavailable: '未实现项',
  houses: '宫位',
  aspects: '相位',
  moment: '时刻',
  place: '地点',
  code: '代码',
  dimensions: '维度',
  bank: '题库',
  keywords: '意象',
  categories: '分类',
  media: '图片',
  analysis_type: '分析类型',
}

const SKIP = new Set(['text', 'question'])

function label(key: string): string {
  return LABELS[key] ?? key
}

function isPlain(value: unknown): boolean {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function asEntries(value: unknown): Array<[string, unknown]> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  return Object.entries(value as Record<string, unknown>).filter(([key]) => !SKIP.has(key))
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

/** 顶层分组：chart_facts 的一级键 */
const groups = computed(() => asEntries(props.result.chart_facts))
</script>

<template>
  <div class="generic-board">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="通用盘面"
      description="该术数尚未提供专属可视化，以下为计算结果的完整事实，未做任何加工。"
    />

    <section v-for="[key, value] in groups" :key="key" class="group">
      <h4>{{ label(key) }}</h4>

      <!-- 键值对象 -->
      <dl v-if="asEntries(value).length && !asList(value).length" class="kv">
        <template v-for="[subKey, subValue] in asEntries(value)" :key="subKey">
          <dt>{{ label(subKey) }}</dt>
          <dd>
            <template v-if="isPlain(subValue)">{{ subValue ?? '—' }}</template>
            <template v-else-if="asList(subValue).length">
              <span v-for="(item, index) in asList(subValue)" :key="index" class="chip">
                {{ isPlain(item) ? item : JSON.stringify(item) }}
              </span>
            </template>
            <template v-else>{{ JSON.stringify(subValue) }}</template>
          </dd>
        </template>
      </dl>

      <!-- 列表 -->
      <ul v-else-if="asList(value).length" class="list">
        <li v-for="(item, index) in asList(value)" :key="index">
          <template v-if="isPlain(item)">{{ item }}</template>
          <template v-else>
            <span v-for="[subKey, subValue] in asEntries(item)" :key="subKey" class="pair">
              <em>{{ label(subKey) }}</em>
              <span>{{ isPlain(subValue) ? subValue ?? '—' : JSON.stringify(subValue) }}</span>
            </span>
          </template>
        </li>
      </ul>

      <!-- 纯量 -->
      <p v-else class="scalar">{{ isPlain(value) ? value ?? '—' : JSON.stringify(value) }}</p>
    </section>
  </div>
</template>

<style scoped>
.generic-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.group {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: var(--xs-surface);
  padding: 14px 18px;
  box-shadow: var(--xs-shadow);
}

.group h4 {
  margin: 0 0 10px;
  font-size: 14px;
  color: var(--xs-accent);
}

.kv {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 13px;
}

.kv dt {
  color: var(--xs-text-muted);
}

.kv dd {
  margin: 0;
  word-break: break-word;
}

.list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
}

.pair {
  display: inline-flex;
  gap: 6px;
  margin-right: 14px;
}

.pair em {
  font-style: normal;
  color: var(--xs-text-muted);
}

.chip {
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--xs-accent-soft);
  font-size: 12px;
}

.scalar {
  margin: 0;
  font-size: 13px;
}
</style>
