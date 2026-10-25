<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ChartResult, ZiweiFacts, ZiweiPalace } from '@/api/types'

/**
 * 紫微盘面：4×4 十二宫格 + 中宫信息 + 四化标记 + 大限区间。
 *
 * 只呈现引擎算出的事实（宫位、星曜、四化、大限），不做任何吉凶评断，
 * 也不做借对宫、三方四正一类需要额外流派的推导。
 */
const props = defineProps<{
  result: ChartResult
  /** 关系标记是否展开（分享预览可关掉以减小体积） */
  showRelations?: boolean
}>()

/** 十二宫在地支上的固定位置：巳午未申 / 辰…酉 / 卯…戌 / 寅丑子亥。 */
const LAYOUT: Record<string, { row: number; col: number }> = {
  巳: { row: 1, col: 1 },
  午: { row: 1, col: 2 },
  未: { row: 1, col: 3 },
  申: { row: 1, col: 4 },
  辰: { row: 2, col: 1 },
  酉: { row: 2, col: 4 },
  卯: { row: 3, col: 1 },
  戌: { row: 3, col: 4 },
  寅: { row: 4, col: 1 },
  丑: { row: 4, col: 2 },
  子: { row: 4, col: 3 },
  亥: { row: 4, col: 4 },
}

const facts = computed(() => props.result.chart_facts as unknown as ZiweiFacts)
const palaces = computed<ZiweiPalace[]>(() => facts.value.palaces ?? [])
const sihua = computed(() => facts.value.si_hua ?? {})

/** 三方四正：默认关闭，打开后给命/财/官/迁四宫描边（只定位，不判吉凶） */
const showSanfang = ref(false)
const sanfangSet = computed(() => {
  const life = (facts.value.palaces ?? []).find((palace) => palace.name === '命宫')
  return new Set(life?.sanfang ?? [])
})

/** 年龄序列太长，卡片里只显示前 4 个 */
function shortAges(ages?: number[]): string {
  if (!ages?.length) return '—'
  const head = ages.slice(0, 4).join('/')
  return ages.length > 4 ? `${head}…` : head
}

const liunianTable = computed(() => facts.value.liunian_table ?? [])
const flying = computed(() => facts.value.flying)

/** 宫干四化按宫分组：每宫最多 4 条，用于「禄→财帛」这种落宫标注 */
const flyingByPalace = computed<Record<string, string[]>>(() => {
  const grouped: Record<string, string[]> = {}
  for (const row of facts.value.palace_transformations ?? []) {
    // 卡片里只放「化 + 落宫」，星名放 title，避免一行挤到看不清
    const label = `${row.type}→${row.to_palace}`
    grouped[row.from_palace] = [...(grouped[row.from_palace] ?? []), label]
  }
  return grouped
})

function flyingOf(palace: ZiweiPalace): string[] {
  return flyingByPalace.value[palace.name] ?? []
}

/* ---- 四化与飞星面板 ---- */
type SihuaLayer = 'birth' | 'palace' | 'dayun' | 'liunian' | 'flying'

const LAYERS: { key: SihuaLayer; label: string }[] = [
  { key: 'birth', label: '生年四化' },
  { key: 'palace', label: '宫干四化' },
  { key: 'dayun', label: '大限四化' },
  { key: 'liunian', label: '流年四化' },
  { key: 'flying', label: '飞星串联' },
]

const activeLayer = ref<SihuaLayer>('birth')

interface SihuaRow {
  source: string
  type: string
  star: string
  palace: string
}

function layerRowsOf(key: SihuaLayer): SihuaRow[] {
  const value = facts.value
  if (key === 'flying') {
    return []
  }
  if (key === 'birth') {
    return (value.transformations ?? []).map((item) => ({
      source: `${value.year_ganzhi}年干`,
      type: item.type,
      star: item.star,
      palace: item.palace,
    }))
  }
  if (key === 'palace') {
    return (value.palace_transformations ?? []).map((row) => ({
      source: `${row.from_palace}·${row.stem}干`,
      type: row.type,
      star: row.star,
      palace: row.to_palace,
    }))
  }
  const block = key === 'dayun' ? value.dayun_transformation : value.liunian_transformation
  if (!block) return []
  const prefix = key === 'dayun' ? `${block.age} 岁·${block.palace}` : `${block.ganzhi}年·${block.palace}`
  return block.items.map((item) => ({
    source: `${prefix}·${block.stem}干`,
    type: item.type,
    star: item.star,
    palace: item.palace,
  }))
}

const layerRows = computed(() => layerRowsOf(activeLayer.value))

function layerCount(key: SihuaLayer): number {
  if (key === 'flying') return flying.value?.chains.length ?? 0
  return layerRowsOf(key).length
}

/** 大限/流年只描述「用哪个宫干推了哪四个四化」，没给入参时该字段不存在。 */
const periodRows = computed(() => {
  const value = facts.value
  const rows: { label: string; text: string }[] = []
  if (value.dayun_transformation) {
    const block = value.dayun_transformation
    rows.push({
      label: '大限四化',
      text: `${block.age ?? ''} 岁·${block.palace}（${block.stem}干）：` +
        block.items.map((item) => `${item.star}化${item.type}入${item.palace}`).join('、'),
    })
  }
  if (value.liunian_transformation) {
    const block = value.liunian_transformation
    rows.push({
      label: '流年四化',
      text: `${block.ganzhi ?? ''}年·流年命宫${block.palace}（${block.stem}干）：` +
        block.items.map((item) => `${item.star}化${item.type}入${item.palace}`).join('、'),
    })
  }
  return rows
})

const huaText = computed(() =>
  Object.entries(sihua.value)
    .map(([type, star]) => `${star}化${type}`)
    .join('、'),
)

function areaStyle(branch: string): Record<string, string> {
  const cell = LAYOUT[branch] ?? { row: 1, col: 1 }
  return { gridRow: String(cell.row), gridColumn: String(cell.col) }
}

/** 宫内星曜的四化类型（可能是辅星，如文曲化忌），按星名建索引。 */
function huaOf(palace: ZiweiPalace, star: string): string[] {
  return (palace.transformations ?? []).filter((item) => item.star === star).map((item) => item.type)
}

const conventionTags = computed(() => {
  const conv = props.result.convention as unknown as Record<string, unknown>
  return [
    { label: '历法基准', text: conv.calendar_basis === 'lunar' ? '农历' : String(conv.calendar_basis ?? '') },
    { label: '年界', text: conv.year_boundary === 'lunar_new_year' ? '农历正月初一' : String(conv.year_boundary ?? '') },
    { label: '闰月', text: conv.leap_month === 'as_current_month' ? '按本月计' : String(conv.leap_month ?? '') },
    { label: '子时', text: conv.zi_hour === 'same_day' ? '当日之子时' : String(conv.zi_hour ?? '') },
    { label: '流派', text: String(conv.school ?? '') },
  ].filter((tag) => tag.text)
})
</script>

<template>
  <div class="ziwei-board">
    <div class="chart-wrap">
      <div class="chart">
        <div
          v-for="palace in palaces"
          :key="palace.name"
          class="palace"
          :class="{
            'is-life': palace.order === 0,
            'is-body': palace.is_body,
            'is-sanfang': showSanfang && sanfangSet.has(palace.name),
          }"
          :style="areaStyle(palace.branch)"
        >
          <div class="palace-head">
            <span class="palace-name">{{ palace.name }}</span>
            <span class="palace-stem">{{ palace.heavenly_stem }}{{ palace.branch }}</span>
          </div>

          <div class="star-list">
            <span v-for="star in palace.main_stars" :key="star" class="star main">
              {{ star }}
              <em
                v-for="kind in huaOf(palace, star)"
                :key="kind"
                class="hua"
                :class="`hua-${kind}`"
              >{{ kind }}</em>
            </span>
            <span v-if="!palace.main_stars.length" class="star empty">无主星</span>
          </div>

          <div v-if="palace.aux_stars.length" class="star-list aux">
            <span v-for="star in palace.aux_stars" :key="star" class="star aux-star">
              {{ star }}
              <em
                v-for="kind in huaOf(palace, star)"
                :key="kind"
                class="hua"
                :class="`hua-${kind}`"
              >{{ kind }}</em>
            </span>
          </div>

          <div v-if="palace.minor_stars?.length" class="star-list minor">
            <span v-for="star in palace.minor_stars ?? []" :key="star" class="star minor-star">{{ star }}</span>
          </div>

          <div v-if="palace.life_cycle || palace.bo_shi || palace.jiang_qian || palace.sui_qian" class="shen-sha">
            <span v-if="palace.life_cycle">{{ palace.life_cycle }}</span>
            <span v-if="palace.bo_shi" class="bo-shi">{{ palace.bo_shi }}</span>
            <span v-if="palace.jiang_qian" class="jiang">{{ palace.jiang_qian }}</span>
            <span v-if="palace.sui_qian" class="sui">{{ palace.sui_qian }}</span>
            <span v-for="kind in palace.self_hua ?? []" :key="kind" class="self-hua" :class="`sh-${kind}`">
              {{ kind }}↺
            </span>
          </div>

          <div class="ages">
            <span>小限 {{ shortAges(palace.xiaoxian_ages) }}</span>
            <span>流年 {{ shortAges(palace.liunian_ages) }}</span>
          </div>

          <div v-if="flyingOf(palace).length" class="flying">
            <span
              v-for="label in flyingOf(palace)"
              :key="label"
              class="flying-tag"
              :title="`${palace.heavenly_stem}干四化：${label}`"
            >{{ label }}</span>
          </div>

          <div class="palace-foot">
            <span class="dayun">{{ palace.dayun.start_age }}–{{ palace.dayun.end_age }} 岁</span>
            <span v-if="palace.is_body" class="body-tag">身宫</span>
          </div>
        </div>

        <div class="center">
          <div class="center-title">
            <span class="lunar">{{ facts.lunar_date.text }}</span>
            <span class="solar">{{ facts.solar_date }}</span>
          </div>

          <div class="bureau">{{ facts.five_element_bureau.name }}</div>

          <div class="kv">
            <span class="k">年干支</span>
            <span class="v">{{ facts.year_ganzhi }}（{{ facts.year_zodiac }}）</span>
          </div>
          <div class="kv">
            <span class="k">命宫</span>
            <span class="v">
              {{ facts.life_palace.text }}
              <span class="muted">纳音 {{ facts.five_element_bureau.life_palace_nayin }}</span>
            </span>
          </div>
          <div class="kv">
            <span class="k">身宫</span>
            <span class="v">{{ facts.body_palace.palace }}（{{ facts.body_palace.branch }}宫）</span>
          </div>
          <div class="kv">
            <span class="k">紫微</span>
            <span class="v">落{{ facts.ziwei_star.palace }}（{{ facts.ziwei_star.branch }}宫）</span>
          </div>
          <div class="kv">
            <span class="k">时支</span>
            <span class="v">
              {{ facts.hour_branch }}时
              <span v-if="!facts.hour_known" class="muted">（时辰未知，按午时占位）</span>
            </span>
          </div>
          <div class="kv">
            <span class="k">大限</span>
            <span class="v">{{ facts.dayun_forward ? '顺行' : '逆行' }}</span>
          </div>
          <div v-if="huaText" class="kv">
            <span class="k">生年四化</span>
            <span class="v">{{ huaText }}</span>
          </div>
          <div v-for="row in periodRows" :key="row.label" class="kv period">
            <span class="k">{{ row.label }}</span>
            <span class="v">{{ row.text }}</span>
          </div>
        </div>
      </div>
    </div>

    <section class="sihua-panel">
      <div class="panel-head">
        <span class="panel-title">四化与飞星</span>
        <span class="panel-hint">五层并列：生年 / 宫干 / 大限 / 流年 / 飞星；只看“什么星化什么、落在哪宫”，不作吉凶</span>
        <button class="toggle" type="button" :class="{ on: showSanfang }" @click="showSanfang = !showSanfang">
          三方四正{{ showSanfang ? '开' : '关' }}
        </button>
      </div>

      <div class="layer-tabs">
        <button
          v-for="layer in LAYERS"
          :key="layer.key"
          class="layer-tab"
          :class="{ active: activeLayer === layer.key }"
          type="button"
          @click="activeLayer = layer.key"
        >
          {{ layer.label }}
          <em>{{ layerCount(layer.key) }}</em>
        </button>
      </div>

      <div v-if="activeLayer === 'flying'" class="flying-list">
        <template v-if="flying?.chains.length">
          <div v-for="(chain, index) in flying.chains" :key="index" class="chain">
            <span class="chain-start">{{ chain.start_palace }}·{{ chain.start_stem }}干</span>
            <template v-for="(hop, hopIndex) in chain.hops" :key="hopIndex">
              <span class="arrow">→</span>
              <span class="hop" :class="`t-${hop.type}`">
                {{ hop.palace }} {{ hop.star }}化{{ hop.type }} 入 {{ hop.to_palace }}
              </span>
            </template>
            <span v-if="chain.cycle" class="cycle">（回到起点，链路结束）</span>
          </div>
          <p v-if="flying.truncated" class="empty">链路较多，已截断；可减少起点或降低深度。</p>
        </template>
        <p v-else class="empty">本盘暂无可用链路。</p>
      </div>

      <div v-else-if="layerRows.length" class="sihua-table">
        <div class="sh-row sh-head">
          <span>来源</span><span>化</span><span>星</span><span>落宫</span>
        </div>
        <div v-for="(row, index) in layerRows" :key="`${row.source}-${index}`" class="sh-row">
          <span class="src">{{ row.source }}</span>
          <span class="type" :class="`t-${row.type}`">{{ row.type }}</span>
          <span class="star">{{ row.star }}</span>
          <span class="to">{{ row.palace }}</span>
        </div>
      </div>
      <p v-else class="empty">
        该层还没有数据：大限四化需要在排盘页填「虚岁」，流年四化需要填「农历年」。
      </p>
    </section>

    <section v-if="liunianTable.length" class="period-table">
      <div class="panel-head">
        <span class="panel-title">流年表</span>
        <span class="panel-hint">从入参年份起 10 年；虚岁按公历年差 +1，未起运时同样列出</span>
      </div>
      <div class="pt-scroll">
        <div class="pt-row pt-head">
          <span>年份</span><span>虚岁</span><span>干支</span><span>流年命宫</span>
        </div>
        <div v-for="row in liunianTable" :key="row.year" class="pt-row">
          <span>{{ row.year }}</span><span>{{ row.virtual_age }}</span>
          <span class="pillar">{{ row.pillar }}</span><span class="palace-name">{{ row.palace }}</span>
        </div>
      </div>
    </section>

    <div v-if="props.showRelations !== false && result.triggered_rules.length" class="markers">
      <div class="markers-title">结构标记</div>
      <ul>
        <li v-for="rule in result.triggered_rules" :key="rule.rule_id">
          <strong>{{ rule.label }}</strong>：{{ rule.note }}
        </li>
      </ul>
    </div>

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
.ziwei-board {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.chart-wrap {
  overflow-x: auto;
}

.chart {
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  grid-template-rows: repeat(4, minmax(132px, auto));
  gap: 6px;
  min-width: 640px;
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: var(--xs-surface-muted);
  padding: 6px;
}

.palace {
  border: 1px solid var(--xs-border);
  border-radius: 8px;
  background: #fff;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.palace.is-life {
  border-color: #8a5a1c;
  box-shadow: inset 0 0 0 1px #e8cfa8;
}

.palace.is-body {
  background: #fdfaf3;
}

.palace-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
}

.palace-name {
  font-weight: 600;
}

.palace-stem {
  font-family: 'Songti SC', 'STSong', serif;
  color: var(--xs-text-muted);
}

.star-list {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
}

.star {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 14px;
  line-height: 1.5;
}

.star.main {
  color: #1f2d3d;
  font-weight: 600;
}

.star.aux-star {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.star.minor-star {
  font-size: 11px;
  color: #9a938a;
}

.star-list.minor {
  gap: 1px 6px;
}

.shen-sha {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  font-size: 10.5px;
  color: #a08a6a;
}

.bo-shi {
  color: #8b93a8;
}

.jiang {
  color: #7a6a8a;
}

.sui {
  color: #6b7a6b;
}

.self-hua {
  font-weight: 600;
}

.sh-禄 {
  color: #3a9d5d;
}
.sh-权 {
  color: #2b6cb0;
}
.sh-科 {
  color: #7c5cbf;
}
.sh-忌 {
  color: #c0392b;
}

.ages {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 8px;
  font-size: 10px;
  color: #9b917f;
}

.palace.is-sanfang {
  border-color: rgba(43, 108, 176, 0.55);
  box-shadow: inset 0 0 0 2px rgba(43, 108, 176, 0.16);
}

.flying {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 4px;
  margin-top: 2px;
}

.flying-tag {
  font-size: 10px;
  line-height: 1.4;
  padding: 0 3px;
  border-radius: 3px;
  background: #f4f1ea;
  color: #7a6a52;
}

.star.empty {
  font-size: 12px;
  color: #a0a0a0;
  font-weight: 400;
}

.hua {
  font-style: normal;
  font-size: 10px;
  margin-left: 1px;
  padding: 0 2px;
  border-radius: 3px;
  color: #fff;
}

.hua-禄 {
  background: #3a9d5d;
}

.hua-权 {
  background: #2b6cb0;
}

.hua-科 {
  background: #7c5cbf;
}

.hua-忌 {
  background: #c0392b;
}

.palace-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.body-tag {
  border: 1px solid #d08a3a;
  border-radius: 4px;
  padding: 0 4px;
  color: #8a5a1c;
  background: #fdf6ec;
}

.center {
  grid-area: 2 / 2 / 4 / 4;
  border: 1px solid var(--xs-border);
  border-radius: 8px;
  background: #fff;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.center-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 2px;
}

.center-title .lunar {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 15px;
  font-weight: 600;
}

.center-title .solar {
  color: var(--xs-text-muted);
}

.bureau {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 22px;
  font-weight: 700;
  color: #8a5a1c;
  letter-spacing: 2px;
  margin: 2px 0 4px;
}

.kv {
  display: flex;
  gap: 8px;
  line-height: 1.8;
}

.kv .k {
  flex: 0 0 58px;
  color: var(--xs-text-muted);
}

.kv .v {
  flex: 1;
}

.kv.period .v {
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--xs-text-muted);
}

.muted {
  color: var(--xs-text-muted);
}

.markers,
.warnings {
  border: 1px dashed var(--xs-border);
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--xs-text-muted);
}

/* ---- 四化与飞星 ---- */
.sihua-panel {
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.panel-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 1px;
}

.panel-hint {
  font-size: 11.5px;
  color: var(--xs-text-muted);
}

.toggle {
  margin-left: auto;
  border: 1px solid var(--xs-border);
  background: #fff;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 11.5px;
  color: var(--xs-text-muted);
  cursor: pointer;
}

.toggle.on {
  border-color: rgba(43, 108, 176, 0.5);
  color: #2b6cb0;
  background: rgba(43, 108, 176, 0.08);
}

.layer-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.layer-tab {
  border: 1px solid var(--xs-border);
  background: #fff;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  color: var(--xs-text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.layer-tab:hover {
  color: var(--xs-text);
  box-shadow: var(--xs-shadow);
}

.layer-tab em {
  font-style: normal;
  font-size: 10.5px;
  background: var(--xs-surface-muted);
  border-radius: 999px;
  padding: 0 6px;
}

.layer-tab.active {
  background: linear-gradient(135deg, #8a6a3b, #b08a52);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 6px 14px rgba(138, 106, 59, 0.25);
}

.layer-tab.active em {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
}

.sihua-table {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  overflow-y: auto;
  max-height: 286px;
}

.sh-row {
  display: grid;
  grid-template-columns: minmax(120px, 1.6fr) 40px minmax(56px, 1fr) minmax(72px, 1fr);
  gap: 8px;
  padding: 7px 12px;
  font-size: 12.5px;
  border-top: 1px solid var(--xs-border);
}

.sh-row:first-child {
  border-top: none;
}

.sh-head {
  background: var(--xs-surface-muted);
  font-size: 11.5px;
  color: var(--xs-text-muted);
  position: sticky;
  top: 0;
  z-index: 1;
}

.sh-row .src {
  color: var(--xs-text-muted);
}

.sh-row .star {
  font-family: 'Songti SC', 'STSong', serif;
}

.sh-row .to {
  color: var(--xs-accent);
}

.sh-row .type {
  font-weight: 600;
}

.t-禄 {
  color: #3a9d5d;
}
.t-权 {
  color: #2b6cb0;
}
.t-科 {
  color: #7c5cbf;
}
.t-忌 {
  color: #c0392b;
}

.empty {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  color: var(--xs-text-muted);
}

/* ---- 飞星串联 ---- */
.flying-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 12px;
}

.chain {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--xs-border);
}

.chain:last-child {
  border-bottom: none;
}

.chain-start {
  font-weight: 600;
  color: var(--xs-accent);
}

.arrow {
  color: #c0b6a4;
}

.hop {
  color: var(--xs-text);
}

.cycle {
  font-size: 11px;
  color: #c0392b;
}

/* ---- 流年表 ---- */
.period-table {
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pt-scroll {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 260px;
  overflow-y: auto;
}

.pt-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  padding: 5px 8px;
  font-size: 12.5px;
  border-radius: 6px;
}

.pt-row:nth-child(even) {
  background: var(--xs-surface-muted);
}

.pt-head {
  position: sticky;
  top: 0;
  background: #fff;
  font-size: 11.5px;
  color: var(--xs-text-muted);
  z-index: 1;
}

.pt-row .pillar {
  font-family: 'Songti SC', 'STSong', serif;
  font-weight: 600;
}

.pt-row .palace-name {
  color: var(--xs-accent);
}

.warnings {
  border-color: #d08a3a;
  background: #fdf6ec;
  color: #8a5a1c;
}

.markers-title,
.warnings-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--xs-text);
}

.warnings .warnings-title {
  color: #8a5a1c;
}

.markers ul,
.warnings ul {
  margin: 0;
  padding-left: 18px;
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
</style>
