<script setup lang="ts">
import { computed } from 'vue'

import type { ChartResult, TarotFacts } from '@/api/types'

/**
 * 塔罗盘面：按牌阵位置排卡片，正位/逆位用翻转与底色区分。
 *
 * 设计取舍：
 * - 不做「牌面插画」：仓库不携带任何版权牌图，画一个假图比留空更糟；
 * - 位置名直接取自后端，前端不硬编码牌阵定义；
 * - 正逆位用「文字 + 旋转 180°」双重标识，不单靠颜色（色盲可用性）。
 */
const props = defineProps<{ result: ChartResult }>()

const facts = computed(() => props.result.chart_facts as unknown as TarotFacts)

const SUIT_LABELS: Record<string, string> = {
  major: '大阿卡纳',
  wands: '权杖',
  cups: '圣杯',
  swords: '宝剑',
  pentacles: '星币',
}

/** 牌阵越大，卡片越窄；单牌时给足展示空间 */
const columns = computed(() => {
  const count = facts.value.cards.length
  if (count <= 1) return 1
  if (count <= 3) return count
  if (count <= 7) return 4
  return 5
})
</script>

<template>
  <div class="tarot-board">
    <div class="head">
      <div class="title">
        <span class="spread">{{ facts.spread.name }}</span>
        <span class="sub">{{ facts.spread.card_count }} 张 · {{ facts.deck.used }}</span>
      </div>
      <div class="tags">
        <el-tag size="small" effect="plain">
          {{ facts.draw.allow_reversed ? `逆位概率 ${facts.draw.reversed_probability}` : '仅正位' }}
        </el-tag>
        <el-tag v-if="facts.draw.auto_seed" size="small" type="warning" effect="plain">
          种子自动派生
        </el-tag>
        <el-tag size="small" type="info" effect="plain">{{ facts.draw.seed }}</el-tag>
      </div>
    </div>

    <div class="cards" :style="{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }">
      <div
        v-for="card in facts.cards"
        :key="card.position"
        class="card"
        :class="{ reversed: card.orientation === 'reversed' }"
      >
        <div class="position">{{ card.position }}</div>
        <div class="face" :class="card.suit">
          <div class="num">{{ card.number ?? '—' }}</div>
          <div class="name">{{ card.name_cn }}</div>
          <div class="en">{{ card.name }}</div>
        </div>
        <div class="meta">
          <el-tag size="small" effect="plain">{{ SUIT_LABELS[card.suit] ?? card.suit }}</el-tag>
          <el-tag
            size="small"
            :type="card.orientation === 'reversed' ? 'danger' : 'success'"
            effect="plain"
          >
            {{ card.orientation_cn }}
          </el-tag>
        </div>
        <div class="keywords">
          <span v-for="word in card.keywords" :key="word" class="kw">{{ word }}</span>
        </div>
      </div>
    </div>

    <p class="note">
      牌面为结构示意，不携带任何版权牌图。关键词为自编简表，只作牌面参考，不构成预测。
    </p>
  </div>
</template>

<style scoped>
.tarot-board {
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

.spread {
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

.cards {
  display: grid;
  gap: 12px;
}

.card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: var(--xs-surface);
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.position {
  font-size: 12px;
  color: var(--xs-text-muted);
  text-align: center;
}

.face {
  border-radius: 10px;
  background: linear-gradient(160deg, #fbf7ee, #f2ead9);
  border: 1px solid var(--xs-border);
  padding: 14px 8px;
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 108px;
  justify-content: center;
  transition: transform 0.2s ease;
}

/* 逆位用旋转 + 文字双重标识，不单靠颜色 */
.card.reversed .face {
  transform: rotate(180deg);
  background: linear-gradient(160deg, #f6eeee, #ece0e0);
}

.face.major {
  border-color: var(--xs-accent);
}

.num {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.name {
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 16px;
  color: var(--xs-text);
}

.en {
  font-size: 10px;
  color: var(--xs-text-muted);
  letter-spacing: 0.02em;
}

.meta {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  justify-content: center;
}

.keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

.kw {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--xs-accent-soft);
  font-size: 11px;
}

.note {
  margin: 0;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.8;
}
</style>
