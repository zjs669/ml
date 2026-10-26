<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult } from '@/api/types'

/**
 * 梅花易数盘面：五卦并列（本/互/变/错/综）+ 体用生克。
 *
 * 为什么值得专属渲染（而不是 GenericBoard）：五个卦的**关系**是本域的核心，
 * 键值列表只能一个卦一个卦地看，看不出「本卦动二爻得变卦」这条链。
 *
 * 爻位画法：`bits` 从初爻到上爻，渲染时倒序（上爻在最上），
 * 与纸面卦象一致。动爻加圆点标记。
 */
const props = defineProps<{ result: ChartResult }>()

interface HexBlock {
  name: string
  upper: string
  lower: string
  bits: string
  palace: string
  palace_element: string
  phase: string
  moving_line: number | null
}

const facts = computed(() => props.result.chart_facts as Record<string, any>)

const method = computed(() => facts.value.method ?? '')
const casting = computed(() => facts.value.casting ?? {})
const bodyUse = computed(() => facts.value.body_use ?? {})

const HEX_ORDER: Array<{ key: string; label: string; hint: string }> = [
  { key: 'original', label: '本卦', hint: '起卦所得' },
  { key: 'mutual', label: '互卦', hint: '二三四爻为下、三四五爻为上' },
  { key: 'changed', label: '变卦', hint: '动爻变后所得' },
  { key: 'opposite', label: '错卦', hint: '六爻全变' },
  { key: 'reversed', label: '综卦', hint: '六爻上下颠倒' },
]

const blocks = computed(() =>
  HEX_ORDER.map((item) => ({ ...item, hex: facts.value[item.key] as HexBlock | undefined })).filter(
    (item) => item.hex,
  ),
)

const METHOD_LABEL: Record<string, string> = {
  time: '时间起卦',
  numbers: '报数起卦',
  text: '字占起卦',
  measure: '丈尺起卦',
  direction: '方位起卦',
  hexagram: '指定卦',
}

/** 从上爻到初爻，便于按纸面顺序渲染。 */
function linesTopDown(bits: string): Array<{ position: number; yang: boolean }> {
  const chars = bits.split('')
  return chars
    .map((bit, index) => ({ position: index + 1, yang: bit === '1' }))
    .reverse()
}

const POSITION_NAME = ['初', '二', '三', '四', '五', '上']
</script>

<template>
  <div class="meihua-board">
    <div class="casting-row">
      <span class="casting-method">{{ METHOD_LABEL[method] ?? method }}</span>
      <span v-if="casting.upper_number !== undefined" class="casting-detail">
        上卦数 {{ casting.upper_number }} · 下卦数 {{ casting.lower_number }} ·
        动爻 {{ casting.moving_line }}
      </span>
    </div>

    <div class="hex-row">
      <section v-for="item in blocks" :key="item.key" class="hex-card" :class="{ primary: item.key === 'original' }">
        <div class="hex-head">
          <span class="hex-label">{{ item.label }}</span>
          <span class="hex-hint">{{ item.hint }}</span>
        </div>

        <div class="hex-body">
          <div class="hex-lines">
            <div
              v-for="line in linesTopDown(item.hex!.bits)"
              :key="line.position"
              class="line"
              :class="{ moving: item.hex!.moving_line === line.position }"
            >
              <span class="line-name">{{ POSITION_NAME[line.position - 1] }}</span>
              <span class="line-shape">
                <template v-if="line.yang">
                  <span class="bar solid" />
                </template>
                <template v-else>
                  <span class="bar half" />
                  <span class="bar half" />
                </template>
              </span>
              <span class="line-mark">{{ item.hex!.moving_line === line.position ? '●' : '' }}</span>
            </div>
          </div>

          <div class="hex-meta">
            <div class="hex-name">{{ item.hex!.name }}</div>
            <div class="hex-trigrams">{{ item.hex!.upper }}上 {{ item.hex!.lower }}下</div>
            <div class="hex-palace">
              {{ item.hex!.palace }}宫（{{ item.hex!.palace_element }}）· {{ item.hex!.phase }}
            </div>
          </div>
        </div>
      </section>
    </div>

    <section class="body-use">
      <div class="bu-title">体用</div>
      <div class="bu-grid">
        <div class="bu-item">
          <span class="bu-label">体</span>
          <span class="bu-value">{{ bodyUse.body?.trigram }} · {{ bodyUse.body?.element }}</span>
        </div>
        <div class="bu-item">
          <span class="bu-label">用</span>
          <span class="bu-value">{{ bodyUse.use?.trigram }} · {{ bodyUse.use?.element }}</span>
        </div>
        <div class="bu-item accent">
          <span class="bu-label">体用关系</span>
          <span class="bu-value">{{ bodyUse.relation }}</span>
        </div>
        <div class="bu-item">
          <span class="bu-label">变卦之"用"</span>
          <span class="bu-value">{{ bodyUse.changed_use?.trigram }} · {{ bodyUse.changed_use?.element }}</span>
        </div>
        <div class="bu-item accent">
          <span class="bu-label">变后关系</span>
          <span class="bu-value">{{ bodyUse.changed_relation }}</span>
        </div>
      </div>
      <p class="bu-note">只列五行与生克方向，不判断吉凶，也不推应期。</p>
    </section>
  </div>
</template>

<style scoped>
.meihua-board {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.casting-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 12px;
  color: var(--xs-text-muted);
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--xs-border);
}

.casting-method {
  font-weight: 600;
  color: var(--xs-accent);
}

.hex-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}

.hex-card {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: #fff;
  padding: 12px 14px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
}

.hex-card.primary {
  border-color: rgba(138, 106, 59, 0.45);
  background: linear-gradient(160deg, #ffffff 0%, #fcfaf4 100%);
  box-shadow: var(--xs-shadow);
}

.hex-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding-bottom: 6px;
  margin-bottom: 8px;
  border-bottom: 1px dashed var(--xs-border);
}

.hex-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--xs-accent);
}

.hex-hint {
  font-size: 10px;
  color: var(--xs-text-muted);
}

.hex-body {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.hex-lines {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: none;
}

.line {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 12px;
}

.line-name {
  font-size: 9px;
  color: var(--xs-text-muted);
  width: 10px;
  text-align: center;
}

.line-shape {
  display: flex;
  gap: 4px;
  width: 52px;
}

.bar {
  height: 5px;
  border-radius: 2px;
  background: #4a4038;
}

.bar.solid {
  width: 52px;
}

.bar.half {
  width: 22px;
}

.line.moving .bar {
  background: var(--xs-accent);
}

.line-mark {
  font-size: 9px;
  color: var(--xs-accent);
  width: 8px;
}

.hex-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.hex-name {
  font-size: 15px;
  font-family: 'Songti SC', 'STSong', serif;
  letter-spacing: 1px;
}

.hex-trigrams,
.hex-palace {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.body-use {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: #fff;
  padding: 14px 16px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
}

.bu-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--xs-accent);
  padding-bottom: 8px;
  margin-bottom: 10px;
  border-bottom: 1px dashed var(--xs-border);
}

.bu-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.bu-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 9px 12px;
  border-radius: 10px;
  background: var(--xs-surface-muted);
}

.bu-item.accent {
  background: var(--xs-accent-soft);
}

.bu-label {
  font-size: 11px;
  color: var(--xs-text-muted);
}

.bu-value {
  font-size: 14px;
  font-weight: 600;
}

.bu-note {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--xs-text-muted);
}
</style>
