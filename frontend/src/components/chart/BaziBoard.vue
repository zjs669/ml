<script setup lang="ts">
import { computed } from 'vue'

import ElementBlock from './ElementBlock.vue'
import PillarCard from './PillarCard.vue'
import RelationList from './RelationList.vue'
import ShenshaGrid from './ShenshaGrid.vue'
import type { ChartResult, Position } from '@/api/types'

/**
 * 四柱盘面：日主头图 + 四柱 + 五行 + 节气 + 大运时间轴 + 流年条。
 * 排盘页、命盘详情页、分享预览页通过 `ChartBoard` 分发到这里，保证三处口径一致。
 *
 * 只呈现引擎算出的事实：大运与流年都是「干支 + 年龄 + 起止」，不做旺衰与吉凶。
 */
const props = defineProps<{
  result: ChartResult
  /** 关系列表是否展开（分享预览可关掉以减小体积） */
  showRelations?: boolean
}>()

const LABELS: Record<Position, string> = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' }

const facts = computed(() => props.result.chart_facts)
const order = computed<Position[]>(() => facts.value.order ?? ['year', 'month', 'day', 'hour'])

const jieqi = computed(() => facts.value.jieqi)
const dayun = computed(() => facts.value.dayun)
const solar = computed(() => facts.value.solar_time_adjust)
const liunian = computed(() => facts.value.liunian)

const ELEMENT_CLASS: Record<string, string> = {
  木: 'el-wood',
  火: 'el-fire',
  土: 'el-earth',
  金: 'el-metal',
  水: 'el-water',
}

const masterClass = computed(() => ELEMENT_CLASS[facts.value.day_master.element] ?? '')

/** 当前公历年：只用于高亮，不参与计算（截图与分享不受影响） */
const thisYear = new Date().getFullYear()

/** 流年窗口里第一柱所属的大运，用于在大运时间轴上高亮 */
const activeDayun = computed(() => liunian.value?.list?.[0]?.dayun_index ?? null)

const liunianLast = computed(() => {
  const rows = liunian.value?.list ?? []
  return rows.length ? rows[rows.length - 1].year : null
})

const RELATION_SYMBOL: Record<string, string> = {
  天干五合: '合', 天干相冲: '冲', 天干相克: '克',
  六合: '合', 三合: '合', 三会: '会', 半会: '半会',
  六冲: '冲', 三刑: '刑', 相刑: '刑', 自刑: '刑',
  相害: '害', 相破: '破',
}

/** 四柱下方的关系摘要：只取前 6 条，完整列表仍在 RelationList */
const relationStrip = computed(() => {
  const rules = facts.value.relations?.rules ?? []
  const format = (scope: string) =>
    rules
      .filter((rule) => rule.scope === scope)
      .slice(0, 6)
      .map((rule) => {
        const symbol = RELATION_SYMBOL[rule.relation] ?? rule.relation
        // 合/克/冲 按「甲克戊」写；半会/三合/三会 是组合名，写成「亥子半会」
        const joined = rule.members.join('')
        if (["半会", "三合", "三会"].includes(rule.relation)) {
          return `${joined}${symbol}`
        }
        return rule.members.length === 2 ? `${rule.members[0]}${symbol}${rule.members[1]}` : `${joined}${symbol}`
      })
  return { stems: format('stem'), branches: format('branch'), total: rules.length }
})

const conventionTags = computed(() => {
  const conv = props.result.convention
  return [
    { label: '年柱边界', text: conv.year_boundary === 'lichun_day' ? '立春当日' : '立春交节' },
    { label: '换日', text: conv.day_boundary === 'zi_hour_policy_b' ? '00:00' : '23:00' },
    {
      label: '时间修正',
      text:
        conv.solar_time === 'true_solar_time'
          ? `真太阳时 ${solar.value?.delta_minutes ?? 0} 分`
          : '不修正',
    },
    { label: '流派', text: conv.school },
    { label: '权重', text: conv.five_element_weight },
  ]
})

const hourConfidence = computed(() => {
  if (facts.value.hour_confidence === 'unknown') return '时辰不详：时柱相关结论仅供参考'
  if (facts.value.hour_confidence === 'low') return '时辰处于边界：已按所选换日口径处理'
  return '时辰确定'
})
</script>

<template>
  <div class="chart-board">
    <div class="board-head">
      <div class="master">
        <span class="master-label">日主</span>
        <span class="master-char" :class="masterClass">{{ facts.day_master.stem }}</span>
        <span class="master-sub">
          {{ facts.day_master.polarity }}{{ facts.day_master.element }} ·
          {{ hourConfidence }}
        </span>
      </div>
      <div class="head-tags">
        <el-tag size="small" effect="plain">{{ facts.timezone }}</el-tag>
        <el-tag size="small" effect="plain">
          {{ jieqi.prev.name }} {{ jieqi.prev.local }}
        </el-tag>
      </div>
    </div>

    <div class="pillars">
      <PillarCard
        v-for="pos in order"
        :key="pos"
        :label="LABELS[pos]"
        :pillar="facts.pillars[pos]"
      />
    </div>

    <div v-if="relationStrip.total" class="relation-strip">
      <span v-if="relationStrip.stems.length" class="group">
        <b>天干</b>{{ relationStrip.stems.join(' · ') }}
      </span>
      <span v-if="relationStrip.branches.length" class="group">
        <b>地支</b>{{ relationStrip.branches.join(' · ') }}
      </span>
      <span class="more">共 {{ relationStrip.total }} 条，详见下方</span>
    </div>

    <ShenshaGrid v-if="facts.shensha" :shensha="facts.shensha" :order="order" />

    <div class="grid">
      <ElementBlock :counts="facts.five_elements_count" />

      <div class="card">
        <div class="card-head">
          <span class="card-title">节气与交节</span>
          <el-tag size="small" effect="plain">{{ jieqi.prev.source }}</el-tag>
        </div>
        <div class="kv">
          <span class="k">上一节</span>
          <span class="v">{{ jieqi.prev.name }} · {{ jieqi.prev.local }}</span>
        </div>
        <div class="kv">
          <span class="k">下一节</span>
          <span class="v">{{ jieqi.next.name }} · {{ jieqi.next.local }}</span>
        </div>
        <div class="kv">
          <span class="k">距上一节</span>
          <span class="v">{{ jieqi.minutes_to_prev }} 分钟</span>
        </div>
        <div class="kv">
          <span class="k">距下一节</span>
          <span class="v">{{ jieqi.minutes_to_next }} 分钟</span>
        </div>
        <div class="hint">交节时刻由天文算法计算，临界 ±2 分钟内的命例会给出额外提示。</div>
      </div>

      <div class="card dayun-card">
        <div class="card-head">
          <span class="card-title">大运</span>
          <el-tag v-if="dayun.computed" size="small" effect="plain">
            {{ dayun.forward ? '顺排' : '逆排' }}
          </el-tag>
        </div>
        <template v-if="dayun.computed">
          <div class="kv">
            <span class="k">起运</span>
            <span class="v">{{ dayun.start_age?.text }}（{{ dayun.start_datetime_estimate }}）</span>
          </div>
          <div class="dayun-track">
            <div
              v-for="item in dayun.list"
              :key="item.index"
              class="dy-card"
              :class="{ active: item.index === activeDayun }"
            >
              <span class="dy-pillar">{{ item.pillar }}</span>
              <span class="dy-age">{{ item.start_age_years }}–{{ item.end_age_years }} 岁</span>
              <span class="dy-year">{{ item.start_year }} 起</span>
            </div>
          </div>
          <div class="hint">{{ dayun.error_bound }}</div>
        </template>
        <div v-else class="dayun-empty">
          <p>{{ dayun.reason || '本次未计算大运' }}</p>
          <p class="hint">在上方把「性别」选为男或女后重新排盘，即可得到大运与气运归属；流年不依赖性别，已照常列出。</p>
        </div>
      </div>
    </div>

    <section v-if="liunian" class="liunian-block">
      <div class="block-head">
        <div class="block-title-row">
          <span class="block-title">流年</span>
          <span class="block-sub">{{ liunian.start_year }}–{{ liunianLast }} · 以立春为界</span>
        </div>
        <span class="block-note">只列干支、十神与所属大运，不作吉凶推断</span>
      </div>
      <div class="ln-strip">
        <div
          v-for="row in liunian.list"
          :key="row.year"
          class="ln-card"
          :class="{ now: row.year === thisYear }"
        >
          <div class="ln-head">
            <span class="ln-year">{{ row.year }}</span>
            <span class="ln-age">{{ row.virtual_age }} 岁</span>
          </div>
          <div class="ln-pillar">{{ row.pillar }}</div>
          <div class="ln-ten">{{ row.ten_god }}</div>
          <div class="ln-foot">
            <span v-if="row.dayun_pillar">大运 {{ row.dayun_pillar }}</span>
            <span v-else class="muted">未起运</span>
          </div>
        </div>
      </div>
    </section>

    <div v-if="solar.applied" class="solar-note">
      已应用真太阳时修正：经度 {{ solar.longitude }}°，修正 {{ solar.delta_minutes }} 分钟（{{ solar.method }}）。
    </div>

    <RelationList
      v-if="showRelations !== false"
      :rules="result.triggered_rules"
      :incomplete="facts.relations?.incomplete"
      :conflicts="facts.relations?.conflicts"
    />

    <div v-if="result.warnings.length" class="warnings">
      <div class="warnings-title">计算提示</div>
      <ul>
        <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
      </ul>
    </div>

    <div class="footnote">
      <div class="conv-tags">
        <span v-for="tag in conventionTags" :key="tag.label" class="conv-tag">
          {{ tag.label }}：{{ tag.text }}
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
.chart-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ---- 日主头图 ---- */
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  padding: 14px 18px;
  background:
    radial-gradient(700px 180px at 0% -40%, #fffdf6 0%, rgba(255, 253, 246, 0) 70%),
    linear-gradient(135deg, #fdfbf6 0%, #f3efe4 100%);
}

.master {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.master-label {
  font-size: 12px;
  letter-spacing: 2px;
  color: var(--xs-text-muted);
}

.master-char {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  color: var(--xs-accent);
}

.master-sub {
  font-size: 12.5px;
  color: var(--xs-text-muted);
}

.head-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* ---- 四柱 ---- */
.pillars {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

/* ---- 关系摘要 ---- */
.relation-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  padding: 9px 14px;
  border: 1px dashed var(--xs-border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.7);
  font-size: 12px;
  color: var(--xs-text);
}

.relation-strip .group b {
  margin-right: 6px;
  color: var(--xs-text-muted);
  font-weight: 600;
}

.relation-strip .more {
  margin-left: auto;
  color: var(--xs-text-muted);
}

/* ---- 三块信息 ---- */
.grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(240px, 1fr) minmax(320px, 1.4fr);
  gap: 12px;
  align-items: start;
}

.card {
  border: 1px solid var(--xs-border);
  border-radius: 14px;
  background: #fff;
  padding: 14px 16px;
  font-size: 13px;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.card-title {
  font-weight: 600;
}

.kv {
  display: flex;
  gap: 8px;
  line-height: 1.9;
}

.kv .k {
  flex: 0 0 64px;
  color: var(--xs-text-muted);
}

.kv .v {
  flex: 1;
}

/* ---- 大运时间轴 ---- */
.dayun-card {
  min-width: 0;
}

.dayun-empty {
  border: 1px dashed var(--xs-border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--xs-text-muted);
}

.dayun-empty p {
  margin: 0;
}

.dayun-empty p + p {
  margin-top: 4px;
  color: #8a5a1c;
}

.dayun-track {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.dy-card {
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  padding: 8px 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  background: var(--xs-surface-muted);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.dy-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--xs-shadow);
}

.dy-card.active {
  border-color: rgba(138, 106, 59, 0.5);
  background: linear-gradient(160deg, #fffdf6 0%, #f7efdd 100%);
  box-shadow: 0 8px 18px rgba(138, 106, 59, 0.16);
}

.dy-pillar {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 18px;
  font-weight: 600;
}

.dy-age {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.dy-year {
  font-size: 10.5px;
  color: #a08a6a;
}

/* ---- 流年 ---- */
.liunian-block {
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: #fff;
  padding: 14px 16px 16px;
}

.block-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.block-title-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.block-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
}

.block-sub {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.block-note {
  font-size: 11.5px;
  color: var(--xs-text-muted);
}

.ln-strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
  gap: 8px;
}

.ln-card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  padding: 9px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: linear-gradient(180deg, #fff 0%, #fcfaf4 100%);
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.ln-card:hover {
  transform: translateY(-2px);
  border-color: rgba(138, 106, 59, 0.4);
  box-shadow: var(--xs-shadow);
}

.ln-card.now {
  border-color: rgba(138, 106, 59, 0.55);
  box-shadow: inset 0 0 0 1px #e8cfa8;
}

.ln-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.ln-pillar {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--xs-text);
}

.ln-ten {
  font-size: 12px;
  color: var(--xs-accent);
}

.ln-foot {
  margin-top: 2px;
  font-size: 10.5px;
  color: var(--xs-text-muted);
}

.hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.muted {
  color: var(--xs-text-muted);
}

.solar-note {
  font-size: 12px;
  color: #2b5f7d;
  background: #eef5f9;
  border-radius: 8px;
  padding: 8px 10px;
}

.warnings {
  border: 1px dashed #d08a3a;
  border-radius: 10px;
  background: #fdf6ec;
  padding: 10px 12px;
  font-size: 12px;
  color: #8a5a1c;
}

.warnings-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.warnings ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}

.footnote {
  border-top: 1px dashed var(--xs-border);
  padding-top: 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conv-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.conv-tag {
  background: var(--xs-surface-muted);
  border-radius: 6px;
  padding: 2px 8px;
}

.versions code {
  background: var(--xs-surface-muted);
  border-radius: 4px;
  padding: 1px 5px;
  margin: 0 2px;
}

.el-wood {
  color: #2f7d4f;
}
.el-fire {
  color: #b8433c;
}
.el-earth {
  color: #9a6a24;
}
.el-metal {
  color: #4c5a75;
}
.el-water {
  color: #2b5f7d;
}

@media (max-width: 1100px) {
  .grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .pillars {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .master-char {
    font-size: 32px;
  }
}
</style>
