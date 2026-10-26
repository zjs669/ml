<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult } from '@/api/types'

/**
 * 西洋占星盘面：四角 + 日月 + 十二宫 + 相位 + **未实现项**。
 *
 * 为什么值得专属渲染（而不是 GenericBoard）：
 * `unavailable` 是合规要求的一部分 —— 用户必须一眼看到「十行星没算」，
 * 混在键值列表里容易被忽略，进而误以为拿到的是完整星盘。
 */
const props = defineProps<{ result: ChartResult }>()

interface Body {
  sign: string
  element: string
  degree_in_sign: number
  longitude: number
  precision?: string
}

const facts = computed(() => props.result.chart_facts as Record<string, any>)

const moment = computed(() => facts.value.moment ?? {})
const place = computed(() => facts.value.place ?? {})
const angles = computed(() => facts.value.angles ?? {})
const planets = computed(() => facts.value.planets ?? {})
const houses = computed<Array<Record<string, any>>>(() => facts.value.houses ?? [])
const aspects = computed<Array<Record<string, any>>>(() => facts.value.aspects ?? [])
const unavailable = computed<string[]>(() => facts.value.unavailable ?? [])

const PLANET_LABEL: Record<string, string> = { sun: '太阳', moon: '月亮' }

function fmt(body: Body | undefined): string {
  if (!body) return '—'
  return `${body.sign} ${body.degree_in_sign.toFixed(2)}°`
}

function aspectName(item: Record<string, any>): string {
  const pair = (item.between as string[] | undefined) ?? []
  const names = pair.map((key) => PLANET_LABEL[key] ?? key)
  return `${names.join(' / ')} · ${item.aspect}`
}
</script>

<template>
  <div class="astro-board">
    <!-- 未实现项放最前：不让人误以为星盘完整 -->
    <div v-if="unavailable.length" class="unavailable">
      <div class="unavailable-title">本版本只算太阳与月亮，以下未实现</div>
      <div class="unavailable-body">
        未计算：{{ unavailable.join('、') }}。
        月亮黄经精度约 ±0.3°，接近星座交界时归属可能翻转。
      </div>
    </div>

    <div class="grid-2">
      <section class="panel">
        <div class="panel-title">时刻与地点</div>
        <dl class="kv">
          <dt>本地时刻</dt>
          <dd>{{ moment.local ?? '—' }}（{{ moment.timezone ?? '—' }}）</dd>
          <dt>世界时</dt>
          <dd>{{ moment.utc ?? '—' }}</dd>
          <dt>儒略日</dt>
          <dd>{{ moment.julian_day_ut ?? '—' }}</dd>
          <dt>经纬度</dt>
          <dd>{{ place.latitude ?? '—' }}° / {{ place.longitude ?? '—' }}°</dd>
        </dl>
      </section>

      <section class="panel">
        <div class="panel-title">四角</div>
        <dl class="kv">
          <dt>上升点 ASC</dt>
          <dd class="strong">{{ fmt(angles.ascendant) }}</dd>
          <dt>天顶 MC</dt>
          <dd class="strong">{{ fmt(angles.midheaven) }}</dd>
          <dt>黄赤交角</dt>
          <dd>{{ angles.obliquity ?? '—' }}°</dd>
          <dt>恒星时</dt>
          <dd>{{ angles.sidereal_degrees ?? '—' }}°</dd>
        </dl>
      </section>
    </div>

    <section class="panel">
      <div class="panel-title">行星（仅日月）</div>
      <div class="planets">
        <div v-for="(body, key) in planets" :key="key" class="planet">
          <span class="planet-name">{{ PLANET_LABEL[String(key)] ?? key }}</span>
          <span class="planet-sign">{{ fmt(body as Body) }}</span>
          <span class="planet-meta">
            {{ (body as Body).element }} · 黄经 {{ (body as Body).longitude.toFixed(2) }}°
          </span>
          <span v-if="(body as Body).precision" class="planet-precision">
            精度 {{ (body as Body).precision }}
          </span>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-title">十二宫（整宫制）</div>
      <div class="houses">
        <div v-for="house in houses" :key="house.house" class="house">
          <span class="house-no">{{ house.house }}</span>
          <span class="house-sign">{{ house.sign }}</span>
          <span class="house-cusp">{{ house.cusps_degree }}°</span>
        </div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-title">主要相位（容许度 {{ facts.aspect_orb ?? '—' }}°）</div>
      <ul v-if="aspects.length" class="aspects">
        <li v-for="(item, index) in aspects" :key="index">
          <span class="aspect-name">{{ aspectName(item) }}</span>
          <span class="aspect-meta">
            实际 {{ item.separation }}°，偏差 {{ item.orb }}°
          </span>
        </li>
      </ul>
      <p v-else class="empty">日月之间没有落在容许度内的主要相位。</p>
    </section>
  </div>
</template>

<style scoped>
.astro-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.unavailable {
  border: 1px solid #e6c98a;
  border-left: 3px solid #c99b45;
  border-radius: 10px;
  background: #fdf7ea;
  padding: 12px 14px;
}

.unavailable-title {
  font-size: 13px;
  font-weight: 600;
  color: #7c5518;
  margin-bottom: 4px;
}

.unavailable-body {
  font-size: 12px;
  line-height: 1.8;
  color: #8a6a3b;
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.panel {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: #fff;
  padding: 14px 16px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
}

.panel-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--xs-accent);
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px dashed var(--xs-border);
}

.kv {
  margin: 0;
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 6px 10px;
  font-size: 13px;
}

.kv dt {
  color: var(--xs-text-muted);
  font-size: 12px;
}

.kv dd {
  margin: 0;
}

.kv dd.strong {
  font-weight: 600;
  color: var(--xs-accent);
}

.planets {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.planet {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--xs-surface-muted);
}

.planet-name {
  font-size: 13px;
  font-weight: 600;
}

.planet-sign {
  font-size: 15px;
  color: var(--xs-accent);
  font-family: 'Songti SC', 'STSong', serif;
}

.planet-meta,
.planet-precision {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.houses {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.house {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  border-radius: 9px;
  background: var(--xs-surface-muted);
  font-size: 12px;
}

.house-no {
  font-size: 10px;
  color: var(--xs-text-muted);
}

.house-sign {
  font-family: 'Songti SC', 'STSong', serif;
}

.house-cusp {
  font-size: 10px;
  color: var(--xs-text-muted);
}

.aspects {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.aspects li {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.aspect-name {
  font-weight: 600;
}

.aspect-meta {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.empty {
  margin: 0;
  font-size: 12px;
  color: var(--xs-text-muted);
}

@media (max-width: 760px) {
  .houses {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
