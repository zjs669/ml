<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult, QimenFacts, QimenPalace } from '@/api/types'

/**
 * 奇门盘面：3×3 洛书九宫（南上北下），每宫显示神/星/门/干。
 * 中五宫无门无神，天禽随天芮寄坤二，因此在坤二宫的星位旁并列显示天禽。
 * 只呈现局数与盘面事实，不取用神、不判旺衰、不择日。
 */
const props = defineProps<{
  result: ChartResult
}>()

const facts = computed(() => props.result.chart_facts as unknown as QimenFacts)

/** 洛书九宫排盘方位（上为南、下为北），空位由中五宫以外的八宫填满 */
const GRID: number[][] = [
  [4, 9, 2],
  [3, 5, 7],
  [8, 1, 6],
]

const byNumber = computed<Record<number, QimenPalace>>(() =>
  Object.fromEntries(facts.value.palaces.map((item) => [item.number, item])),
)

const conv = computed(() => props.result.convention as unknown as Record<string, unknown>)

const timeInfo = computed(() => {
  const value = facts.value
  return [
    { label: '起局', text: `${value.cast_at}（${value.timezone}）` },
    { label: '节气', text: `${value.term.name}（${value.term.local}）` },
    {
      label: '四柱',
      text: (['year', 'month', 'day', 'hour'] as const)
        .map((key) => value.pillars[key].text)
        .join(' '),
    },
    { label: '符头', text: `${value.fu_tou.pillar}（${value.fu_tou.date}）定${value.fu_tou.yuan}` },
    { label: '旬首', text: `${value.xun_kong.xun_head}遁${value.xun_kong.instrument}` },
    { label: '旬空', text: value.xun_kong.branches.join('、') },
    { label: '马星', text: `${value.ma_star.branch}（${value.ma_star.palace_name}）` },
  ]
})

const summary = computed(() => {
  const value = facts.value
  return [
    { label: '局数', text: `${value.dun.text}（${value.dun.yuan}）` },
    {
      label: '值符',
      text: `${value.zhifu.star} 本位${value.zhifu.palace_name} → 落${value.zhifu.landing_name}`,
    },
    {
      label: '值使',
      text: `${value.zhishi.door} 旬内第 ${value.zhishi.steps} 步 → 落${value.zhishi.palace_name}`,
    },
    { label: '时干落宫', text: `${value.hour_stem_palace.stem} → ${value.hour_stem_palace.palace_name}` },
  ]
})

function tags(palace: QimenPalace): string[] {
  const marks: string[] = []
  if (palace.is_zhifu) marks.push('值符宫')
  if (palace.is_zhishi) marks.push('值使宫')
  if (facts.value.ma_star.palace === palace.number) marks.push('马星')
  return marks
}
</script>

<template>
  <div class="qimen-board">
    <div class="head">
      <div class="title">
        <span class="ju">{{ facts.dun.text }}</span>
        <span class="sub">{{ facts.dun.yuan }} · 符头 {{ facts.fu_tou.pillar }}</span>
      </div>
      <div class="tags">
        <el-tag size="small" effect="plain">{{ facts.dun.type }}</el-tag>
        <el-tag size="small" type="warning" effect="plain">{{ facts.dun.yuan }}</el-tag>
        <el-tag v-if="facts.fuyin.star" size="small" type="danger" effect="plain">星伏吟</el-tag>
        <el-tag v-if="facts.fuyin.door" size="small" type="danger" effect="plain">门伏吟</el-tag>
      </div>
    </div>

    <div class="timebar">
      <span v-for="item in timeInfo" :key="item.label" class="time-item">
        <span class="k">{{ item.label }}</span>
        <span class="v">{{ item.text }}</span>
      </span>
    </div>

    <div class="grid">
      <div
        v-for="cell in GRID.flat()"
        :key="cell"
        class="cell"
        :class="{
          center: byNumber[cell]?.is_center,
          zhifu: byNumber[cell]?.is_zhifu,
          zhishi: byNumber[cell]?.is_zhishi,
        }"
      >
        <div class="cell-head">
          <span class="palace-name">{{ byNumber[cell]?.name }}</span>
          <span class="palace-dir">{{ byNumber[cell]?.direction }}</span>
        </div>

        <template v-if="byNumber[cell]?.is_center">
          <div class="center-note">中五宫无门无神<br />天禽寄坤二宫</div>
          <div class="stems">
            <span class="earth">{{ byNumber[cell]?.earth_stem }}</span>
          </div>
        </template>

        <template v-else>
          <div class="deity">{{ byNumber[cell]?.deity }}</div>
          <div class="star-row">
            <span class="star">{{ byNumber[cell]?.star }}</span>
            <span v-if="byNumber[cell]?.extra_star" class="extra">
              {{ byNumber[cell]?.extra_star }}
            </span>
          </div>
          <div class="door">{{ byNumber[cell]?.door }}</div>
          <div class="stems">
            <span class="earth">{{ byNumber[cell]?.earth_stem }}</span>
            <span class="arrow">/</span>
            <span class="sky">{{ byNumber[cell]?.sky_stem }}</span>
            <span v-if="byNumber[cell]?.extra_sky_stem" class="sky">·{{ byNumber[cell]?.extra_sky_stem }}</span>
          </div>
        </template>

        <div v-if="tags(byNumber[cell]!).length" class="cell-tags">
          <el-tag v-for="mark in tags(byNumber[cell]!)" :key="mark" size="small" effect="dark">
            {{ mark }}
          </el-tag>
        </div>
      </div>
    </div>

    <div class="summary">
      <div v-for="item in summary" :key="item.label" class="summary-item">
        <span class="k">{{ item.label }}</span>
        <span class="v">{{ item.text }}</span>
      </div>
    </div>

    <div class="marvels">
      <span class="k">三奇</span>
      <span v-for="item in facts.three_marvels" :key="item.stem" class="marvel">
        {{ item.stem }}在{{ item.palace_name }}
      </span>
    </div>

    <div v-if="result.warnings.length" class="warnings">
      <div class="warnings-title">计算提示</div>
      <ul>
        <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
      </ul>
    </div>

    <div class="footnote">
      <div class="conv-tags">
        <span class="conv-tag">流派：{{ conv.school }}</span>
        <span class="conv-tag">定元：拆补法</span>
        <span class="conv-tag">中宫：寄坤二</span>
        <span class="conv-tag">
          换日：{{ conv.day_boundary === 'zi_hour_policy_b' ? '00:00' : '23:00' }}
        </span>
      </div>
      <div class="versions">
        算法版本 <code>{{ result.algorithm_version }}</code>
        <template v-if="result.source_refs.length">
          · 依据
          <code v-for="ref in result.source_refs" :key="ref.id">{{ ref.id }}</code>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.qimen-board {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}

.title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.ju {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 1px;
}

.sub {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.timebar {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  padding: 10px 14px;
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  background: var(--xs-surface-muted);
  font-size: 12px;
}

.time-item .k {
  color: var(--xs-text-muted);
  margin-right: 6px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 132px;
  padding: 9px 11px;
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  background: #fff;
  font-size: 12px;
}

.cell.zhifu {
  border-color: #d48806;
  box-shadow: inset 0 0 0 1px #f3d19e;
}

.cell.zhishi {
  background: #fffdf5;
}

.cell.center {
  background: var(--xs-surface-muted);
}

.cell-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  color: var(--xs-text-muted);
  font-size: 11px;
}

.palace-name {
  font-weight: 600;
  color: var(--xs-text);
}

.deity {
  font-size: 12px;
  color: #7a5af8;
}

.star-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.star {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.extra {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.door {
  font-size: 13px;
  color: #1677ff;
}

.stems {
  margin-top: auto;
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: var(--xs-text);
}

.arrow {
  margin: 0 3px;
  color: #c0c0c0;
}

.sky {
  color: #d4380d;
}

.center-note {
  font-size: 11px;
  line-height: 1.7;
  color: var(--xs-text-muted);
}

.cell-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.summary-item .k,
.marvels .k {
  color: var(--xs-text-muted);
  margin-right: 8px;
}

.marvels {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.marvel + .marvel {
  margin-left: 12px;
}

.warnings {
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.warnings-title {
  font-weight: 600;
  color: var(--xs-text);
  margin-bottom: 4px;
}

.warnings ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.85;
}

.footnote {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.conv-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.versions code {
  margin: 0 2px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--xs-surface-muted);
  font-size: 11px;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }

  .cell {
    min-height: 118px;
    padding: 7px 8px;
    font-size: 11px;
  }

  .star {
    font-size: 13px;
  }
}
</style>
