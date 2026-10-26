<script setup lang="ts">
import { computed } from 'vue'

import type { AlmanacFacts, ChartResult } from '@/api/types'

/**
 * 黄历盘面：日级条目按「日期 → 宜忌 → 神煞 → 方位 → 九星 → 时辰」分段。
 *
 * 设计取舍：
 * - 宜忌原样列出、不排序不筛选 —— 一旦排序就等于替用户判断重要性；
 * - 吉神/凶煞只报名，不加解释；
 * - 十二时辰用表格，因为它是这一页唯一需要横向对比的部分；
 * - 星宿歌诀不展示：它含大量灾祸措辞，与本项目红线冲突。
 */
const props = defineProps<{ result: ChartResult }>()

const facts = computed(() => props.result.chart_facts as unknown as AlmanacFacts)

const POSITION_LABELS: Record<string, string> = {
  xi: '喜神',
  yang_gui: '阳贵',
  yin_gui: '阴贵',
  fu: '福神',
  cai: '财神',
  tai_sui: '太岁',
}

const positions = computed(() =>
  Object.entries(facts.value.positions ?? {}).map(([key, value]) => ({
    key,
    label: POSITION_LABELS[key] ?? key,
    ...value,
  })),
)

const personal = computed(() => facts.value.personal ?? null)
</script>

<template>
  <div class="almanac-board">
    <div class="head">
      <div class="day">
        <span class="solar">{{ facts.date.solar }}</span>
        <span class="weekday">周{{ facts.date.weekday_name }}</span>
      </div>
      <div class="lunar">
        {{ facts.lunar_date.text }}
        <span class="zodiac">{{ facts.lunar_date.year_zodiac }}年</span>
      </div>
      <div class="tags">
        <el-tag size="small" effect="plain">{{ facts.day_pillar.ganzhi }}日</el-tag>
        <el-tag size="small" effect="plain">{{ facts.day_pillar.na_yin }}</el-tag>
        <el-tag size="small" type="warning" effect="plain">值星 {{ facts.day_pillar.zhi_xing }}</el-tag>
        <el-tag size="small" effect="plain">天神 {{ facts.day_pillar.tian_shen_luck }}</el-tag>
      </div>
    </div>

    <div class="yi-ji">
      <div class="col yi">
        <h4>宜</h4>
        <div class="chips">
          <span v-for="item in facts.yi" :key="item" class="chip">{{ item }}</span>
          <span v-if="!facts.yi.length" class="empty">无</span>
        </div>
      </div>
      <div class="col ji">
        <h4>忌</h4>
        <div class="chips">
          <span v-for="item in facts.ji" :key="item" class="chip ji-chip">{{ item }}</span>
          <span v-if="!facts.ji.length" class="empty">无</span>
        </div>
      </div>
    </div>

    <div class="grid">
      <section>
        <h4>吉神</h4>
        <div class="chips">
          <span v-for="item in facts.ji_shen" :key="item" class="chip">{{ item }}</span>
          <span v-if="!facts.ji_shen.length" class="empty">无</span>
        </div>
      </section>
      <section>
        <h4>凶煞</h4>
        <div class="chips">
          <span v-for="item in facts.xiong_sha" :key="item" class="chip xiong">{{ item }}</span>
          <span v-if="!facts.xiong_sha.length" class="empty">无</span>
        </div>
      </section>
      <section>
        <h4>冲煞</h4>
        <p class="line">冲 {{ facts.chong.desc }}（{{ facts.chong.sheng_xiao }}）</p>
        <p class="line">煞{{ facts.sha_direction }}</p>
      </section>
      <section>
        <h4>星宿</h4>
        <p class="line">
          {{ facts.xiu.name }}宿（{{ facts.xiu.luck }}）· {{ facts.xiu.zheng }} · {{ facts.xiu.animal }}
        </p>
      </section>
      <section>
        <h4>九星</h4>
        <p class="line">
          {{ facts.nine_star.number }}{{ facts.nine_star.color }}（{{ facts.nine_star.element }}）·
          {{ facts.nine_star.position_desc }}
        </p>
        <p class="line muted">
          玄空 {{ facts.nine_star.xuan_kong.name }} · 奇门 {{ facts.nine_star.qi_men.name }} ·
          太乙 {{ facts.nine_star.tai_yi.name }}
        </p>
      </section>
      <section>
        <h4>方位</h4>
        <p v-for="item in positions" :key="item.key" class="line">
          {{ item.label }}：{{ item.branch }}（{{ item.desc }}）
        </p>
      </section>
    </div>

    <section v-if="personal" class="personal">
      <h4>个性化对照</h4>
      <p class="line">
        {{ personal.birth_date }} · {{ personal.birth_year_ganzhi }}年（{{ personal.birth_zodiac }}）·
        日柱 {{ personal.birth_day_ganzhi }}
      </p>
      <p class="line muted">{{ personal.note }}</p>
    </section>

    <section class="hours">
      <h4>十二时辰</h4>
      <table>
        <thead>
          <tr>
            <th>时辰</th>
            <th>干支</th>
            <th>宜</th>
            <th>忌</th>
            <th>冲</th>
            <th>煞</th>
            <th>天神</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="slot in facts.hour_slots" :key="slot.index">
            <td>{{ slot.index }}</td>
            <td class="gz">{{ slot.ganzhi }}</td>
            <td>{{ slot.yi.join('、') || '—' }}</td>
            <td>{{ slot.ji.join('、') || '—' }}</td>
            <td>{{ slot.chong }}</td>
            <td>{{ slot.sha }}</td>
            <td>{{ slot.tian_shen_luck }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.almanac-board {
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

.day {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.solar {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 26px;
  color: var(--xs-accent);
}

.weekday {
  font-size: 13px;
  color: var(--xs-text-muted);
}

.lunar {
  font-size: 14px;
}

.zodiac {
  margin-left: 6px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-left: auto;
}

.yi-ji {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.col {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--xs-surface);
}

.col h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--xs-accent);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 1px 9px;
  border-radius: 999px;
  background: var(--xs-accent-soft);
  font-size: 12px;
}

.ji-chip {
  background: rgba(180, 90, 70, 0.12);
}

.chip.xiong {
  background: rgba(180, 90, 70, 0.12);
}

.empty {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.grid section {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--xs-surface);
}

.grid h4,
.personal h4,
.hours h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--xs-text-muted);
  font-weight: 600;
}

.line {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.8;
}

.line.muted {
  color: var(--xs-text-muted);
  font-size: 12px;
}

.personal {
  border: 1px dashed var(--xs-border);
  border-radius: 12px;
  padding: 12px 14px;
}

.hours {
  overflow-x: auto;
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
}

@media (max-width: 1100px) {
  .grid,
  .yi-ji {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
