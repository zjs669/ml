<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult, LiuyaoFacts, LiuyaoHexagram, LiuyaoLine } from '@/api/types'

/**
 * 六爻盘面：本卦六爻纵排（六神/六亲/纳甲/爻象/世应/动变）+ 变卦 + 互卦 + 时令。
 * 只呈现盘面事实与结构标记，不做用神、旺衰与应期。
 */
const props = defineProps<{
  result: ChartResult
}>()

const facts = computed(() => props.result.chart_facts as unknown as LiuyaoFacts)

/** 自上而下展示：上爻在最上，初爻在最下，与纸面抄录习惯一致。 */
const rows = computed<LiuyaoLine[]>(() => [...facts.value.original.lines].reverse())
const changedRows = computed<Record<number, LiuyaoLine>>(() => {
  const changed = facts.value.changed
  if (!changed) return {}
  return Object.fromEntries(changed.lines.map((line) => [line.position, line]))
})

const conv = computed(() => props.result.convention as unknown as Record<string, unknown>)

const titles = computed(() => {
  const original = facts.value.original
  return {
    name: original.name,
    sub: `${original.upper}上${original.lower}下 · ${original.palace}宫（${original.palace_element}）· ${original.phase}`,
  }
})

const timeInfo = computed(() => {
  const value = facts.value
  return [
    { label: '起卦', text: `${value.cast_at}（${value.hour_branch}时）` },
    { label: '农历', text: value.lunar_date.text },
    { label: '日辰', text: value.day_pillar.text },
    { label: '月建', text: `${value.month_build.text}（${value.month_build.jie}后）` },
    { label: '旬空', text: value.xun_kong.join('、') || '—' },
    { label: '六神起例', text: `${value.day_pillar.stem}日 ${value.liu_shen_order[0]}起初爻` },
  ]
})

function isYang(line: LiuyaoLine): boolean {
  return line.polarity === '阳'
}

function lineMark(line: LiuyaoLine): string {
  if (!line.moving) return ''
  return line.value === 9 ? '○' : '×'
}

function changedOf(line: LiuyaoLine): LiuyaoLine | undefined {
  return line.moving ? changedRows.value[line.position] : undefined
}

function hexText(hexagram: LiuyaoHexagram | null): string {
  if (!hexagram) return ''
  return `${hexagram.name}（${hexagram.palace}宫·${hexagram.phase}，世${hexagram.shi}应${hexagram.ying}）`
}
</script>

<template>
  <div class="liuyao-board">
    <div class="head">
      <div class="gua">
        <span class="gua-name">{{ titles.name }}</span>
        <span class="gua-sub">{{ titles.sub }}</span>
      </div>
      <div class="tags">
        <el-tag size="small" effect="plain">{{ facts.method_label }}</el-tag>
        <el-tag v-if="facts.moving_lines.length" size="small" type="warning" effect="plain">
          {{ facts.moving_lines.length }} 爻动
        </el-tag>
        <el-tag v-else size="small" effect="plain">静卦</el-tag>
        <el-tag size="small" effect="plain">{{ facts.timezone }}</el-tag>
      </div>
    </div>

    <div class="timebar">
      <span v-for="item in timeInfo" :key="item.label" class="time-item">
        <span class="k">{{ item.label }}</span>
        <span class="v">{{ item.text }}</span>
      </span>
    </div>

    <div class="board">
      <div class="board-head">
        <span class="col-shen">六神</span>
        <span class="col-rel">六亲</span>
        <span class="col-najia">纳甲</span>
        <span class="col-line">爻象</span>
        <span class="col-sy">世应</span>
        <span class="col-changed">变爻</span>
      </div>

      <div v-for="line in rows" :key="line.position" class="board-row" :class="{ moving: line.moving }">
        <span class="col-shen">{{ line.liu_shen }}</span>
        <span class="col-rel">{{ line.six_relation }}</span>
        <span class="col-najia">
          {{ line.najia }}
          <span class="element">{{ line.element }}</span>
        </span>
        <span class="col-line">
          <span class="yao" :class="isYang(line) ? 'yang' : 'yin'">
            <i></i><i v-if="!isYang(line)"></i>
          </span>
          <span v-if="lineMark(line)" class="mark">{{ lineMark(line) }}</span>
          <span class="pos">{{ line.position }}</span>
        </span>
        <span class="col-sy">
          <el-tag v-if="line.shi" size="small" type="danger" effect="plain">世</el-tag>
          <el-tag v-else-if="line.ying" size="small" type="success" effect="plain">应</el-tag>
        </span>
        <span class="col-changed">
          <template v-if="changedOf(line)">
            {{ changedOf(line)!.najia }}
            <span class="element">{{ changedOf(line)!.six_relation }}</span>
          </template>
          <span v-else class="empty">—</span>
        </span>
      </div>
    </div>

    <div class="summary">
      <div class="summary-item">
        <span class="k">本卦</span>
        <span class="v">{{ hexText(facts.original) }}</span>
      </div>
      <div v-if="facts.changed" class="summary-item">
        <span class="k">变卦</span>
        <span class="v">{{ hexText(facts.changed) }}</span>
      </div>
      <div class="summary-item">
        <span class="k">互卦</span>
        <span class="v">{{ facts.mutual.name }}（{{ facts.mutual.palace }}宫）</span>
      </div>
    </div>

    <div v-if="facts.question" class="question">
      <span class="k">占问</span>
      <span class="v">{{ facts.question }}</span>
    </div>
    <div v-else class="question muted">
      <span class="k">占问</span>
      <span class="v">未记录（本盘只保存起卦方式与时刻）</span>
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
        <span class="conv-tag">换日：{{ conv.day_boundary === 'zi_hour_policy_b' ? '00:00' : '23:00' }}</span>
        <span class="conv-tag">月建基准：节气</span>
        <span class="conv-tag">六亲参照：本卦卦宫</span>
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
.liuyao-board {
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

.gua {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.gua-name {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 1px;
}

.gua-sub {
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

.board {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.board-head,
.board-row {
  display: grid;
  grid-template-columns: 56px 64px 96px 118px 48px minmax(110px, 1fr);
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 13px;
}

.board-head {
  background: var(--xs-surface-muted);
  font-size: 12px;
  color: var(--xs-text-muted);
}

.board-row + .board-row {
  border-top: 1px dashed var(--xs-border);
}

.board-row.moving {
  background: #fff9f0;
}

.col-najia,
.col-changed {
  font-variant-numeric: tabular-nums;
}

.element {
  margin-left: 4px;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.col-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.yao {
  display: inline-flex;
  gap: 4px;
  width: 52px;
}

.yao i {
  display: block;
  height: 8px;
  border-radius: 2px;
  background: #3b3b3b;
  flex: 1;
}

.yao.yin i {
  flex: 1;
}

.yao.yin {
  justify-content: space-between;
}

.yao.yin i:first-child,
.yao.yin i:last-child {
  flex: 0 0 22px;
}

.mark {
  color: #d48806;
  font-weight: 600;
}

.pos {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.empty {
  color: #c0c0c0;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 22px;
  font-size: 13px;
}

.summary-item .k,
.question .k {
  color: var(--xs-text-muted);
  margin-right: 6px;
}

.question {
  font-size: 13px;
  line-height: 1.8;
}

.question.muted .v {
  color: var(--xs-text-muted);
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
  .board-head {
    display: none;
  }

  .board-row {
    grid-template-columns: 44px 52px 1fr;
    grid-template-areas:
      'shen rel najia'
      'line sy changed';
    row-gap: 6px;
  }

  .col-shen {
    grid-area: shen;
  }

  .col-rel {
    grid-area: rel;
  }

  .col-najia {
    grid-area: najia;
  }

  .col-line {
    grid-area: line;
  }

  .col-sy {
    grid-area: sy;
  }

  .col-changed {
    grid-area: changed;
  }
}
</style>
