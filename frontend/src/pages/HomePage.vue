<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { knowledgeStats, type KnowledgeStats } from '@/api/knowledge'

const router = useRouter()
const stats = ref<KnowledgeStats | null>(null)

onMounted(async () => {
  try {
    stats.value = await knowledgeStats()
  } catch {
    stats.value = null
  }
})

const ENTRIES = [
  { to: '/bazi', mark: '柱', name: '四柱八字', desc: '四柱 · 藏干 · 十神 · 大运' },
  { to: '/reverse', mark: '逆', name: '四柱反查', desc: '干支 → 公历日期与时窗' },
  { to: '/ziwei', mark: '紫', name: '紫微斗数', desc: '十二宫 · 十四主星 · 四化' },
  { to: '/liuyao', mark: '爻', name: '六爻', desc: '本卦变卦 · 纳甲 · 六亲' },
  { to: '/qimen', mark: '门', name: '奇门遁甲', desc: '九宫 · 星门神 · 旬空马星' },
]

const FEATURES = [
  {
    title: '确定性排盘',
    body: '四柱、藏干、十神、五行加权、大运与节气交节全部由自研算法计算，同一输入永远得到同一结果，并回显算法版本。',
  },
  {
    title: '规则驱动的关系判断',
    body: '六合、三合、三会、六冲、相刑、相害、相破、天干合冲逐条给出 rule_id 与来源，只陈述触发事实，不生成吉凶结论。',
  },
  {
    title: 'AI 只做解释',
    body: '模型拿到的是排盘事实与知识库片段，输出经服务端校验：引用必须真实存在、干支不得改写、绝对化与专业越界表述会被拦截。',
  },
  {
    title: '口径可切换可存档',
    body: '立春边界、换日规则、真太阳时全部可选，选择随命盘存档，报告与导出文本都标注所用口径。',
  },
]
</script>

<template>
  <div class="home">
    <section class="hero">
      <div class="hero-main">
        <h1>玄枢国学研习台</h1>
        <p class="tagline">把传统术数拆成<span class="hl">可核验的事实</span>与<span class="hl">可追溯的解释</span>——排盘由算法算，解释由 AI 写，对错由你查。</p>
        <div class="actions">
          <el-button type="primary" size="large" @click="router.push('/bazi')">免费排盘（免登录）</el-button>
          <el-button size="large" @click="router.push('/knowledge')">先看知识库</el-button>
        </div>
        <p class="hero-foot">
          当前为内测版本：四柱八字、四柱反查、紫微斗数、六爻、奇门遁甲均已开放，支付为演示用 Mock 通道，不产生真实扣款。
        </p>
      </div>
      <div class="hero-side">
        <div class="stat">
          <span class="stat-label">已审核知识片段</span>
          <span class="stat-num">{{ stats?.approved_chunks ?? '—' }}</span>
        </div>
        <div class="stat">
          <span class="stat-label">已登记关系规则</span>
          <span class="stat-num">48</span>
        </div>
        <div class="stat">
          <span class="stat-label">可切换口径维度</span>
          <span class="stat-num">4</span>
        </div>
        <p class="stat-note">数字均为实时统计，口径见知识库与口径说明</p>
      </div>
    </section>

    <section class="entries-block">
      <div class="section-head">
        <h2>选一个术数开始</h2>
        <p>四术数都已开放，排盘免登录；保存命盘与生成解读才需要账号。</p>
      </div>
      <div class="entries">
        <button v-for="entry in ENTRIES" :key="entry.to" class="entry" @click="router.push(entry.to)">
          <span class="entry-mark">{{ entry.mark }}</span>
          <span class="entry-body">
            <span class="entry-name">{{ entry.name }}</span>
            <span class="entry-desc">{{ entry.desc }}</span>
          </span>
        </button>
      </div>
    </section>

    <section class="features">
      <div v-for="(item, index) in FEATURES" :key="item.title" class="feature">
        <div class="feature-index">{{ String(index + 1).padStart(2, '0') }}</div>
        <div class="feature-title">{{ item.title }}</div>
        <div class="feature-body">{{ item.body }}</div>
      </div>
    </section>

    <section class="disclaimer">
      <div class="disclaimer-title">重要说明</div>
      <ul>
        <li>本站内容属于传统文化研习与知识普及，<strong>不构成医疗、法律、投资、婚恋等任何专业建议</strong>，也不用于疾病诊断、彩票赌博、命运预测。</li>
        <li>AI 生成内容已在页面与导出文本中显式标识；模型输出仅供研习参考，请勿据此做出重大决定。</li>
        <li>排盘结果依赖你填写的出生时间与地点，输入有误会导致结果不同；时辰不详时系统会明确标注。</li>
        <li>你可以随时删除自己的命盘、笔记与账号；删除后关联报告同步失效。</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.hero {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(240px, 320px);
  gap: 24px;
  background:
    radial-gradient(1200px 380px at 8% -20%, #fffdf7 0%, rgba(255, 253, 247, 0) 60%),
    linear-gradient(135deg, #fdfbf6 0%, #f3efe4 100%);
  border: 1px solid var(--xs-border);
  border-radius: 22px;
  padding: 36px 40px;
  box-shadow: 0 18px 44px rgba(120, 98, 60, 0.1);
}

/* 两团柔光：只作装饰，不抢正文，也不影响点击 */
.hero::before,
.hero::after {
  content: '';
  position: absolute;
  z-index: -1;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(2px);
}

.hero::before {
  width: 420px;
  height: 420px;
  right: -120px;
  top: -180px;
  background: radial-gradient(circle, rgba(194, 154, 94, 0.26) 0%, rgba(194, 154, 94, 0) 68%);
  animation: xs-float 14s ease-in-out infinite;
}

.hero::after {
  width: 300px;
  height: 300px;
  left: -110px;
  bottom: -160px;
  background: radial-gradient(circle, rgba(110, 138, 150, 0.2) 0%, rgba(110, 138, 150, 0) 70%);
  animation: xs-float 18s ease-in-out infinite reverse;
}

@keyframes xs-float {
  0%,
  100% {
    transform: translate3d(0, 0, 0);
  }
  50% {
    transform: translate3d(-14px, 12px, 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .hero::before,
  .hero::after {
    animation: none;
  }
}

.hero-main h1 {
  margin: 0 0 12px;
  font-size: 34px;
  letter-spacing: 4px;
  line-height: 1.28;
  background: linear-gradient(120deg, #2f2b26 0%, #6f5327 55%, #a98550 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.tagline {
  margin: 0;
  font-size: 15.5px;
  line-height: 1.95;
  color: var(--xs-text-muted);
  max-width: 640px;
  /* 避免末尾只剩一个孤字 */
  text-wrap: pretty;
}

.hl {
  color: var(--xs-accent);
  font-weight: 600;
}

.actions {
  margin-top: 22px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-foot {
  margin: 14px 0 0;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.hero-side {
  /* 三行合到一张卡里：比三张窄卡竖向堆叠更整，也不容易被拉得又高又瘦 */
  background:
    radial-gradient(300px 160px at 100% 0%, #fffdf7 0%, rgba(255, 253, 247, 0) 70%),
    #fff;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  padding: 10px 18px 12px;
  box-shadow: 0 12px 28px rgba(120, 98, 60, 0.1);
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.stat {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 0;
}

.stat + .stat {
  border-top: 1px dashed var(--xs-border);
}

.stat-num {
  font-size: 24px;
  font-weight: 600;
  background: linear-gradient(120deg, #8a6a3b 0%, #c29a5e 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.stat-label {
  font-size: 12.5px;
  color: var(--xs-text-muted);
}

.stat-note {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--xs-text-muted);
  line-height: 1.6;
}

.features {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

/* ---- 术数入口 ---- */
.section-head {
  margin-bottom: 12px;
}

.section-head h2 {
  margin: 0 0 4px;
  font-size: 17px;
  letter-spacing: 1px;
}

.section-head p {
  margin: 0;
  font-size: 12.5px;
  color: var(--xs-text-muted);
}

.entries {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
}

.entry {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: linear-gradient(160deg, #ffffff 0%, #fcfaf4 100%);
  padding: 14px 16px;
  cursor: pointer;
  font: inherit;
  color: inherit;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.22s ease, transform 0.22s ease, border-color 0.22s ease;
}

.entry::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(120deg, rgba(194, 154, 94, 0.18), rgba(194, 154, 94, 0) 60%);
  opacity: 0;
  transition: opacity 0.22s ease;
  pointer-events: none;
}

.entry:hover {
  border-color: rgba(138, 106, 59, 0.45);
  box-shadow: var(--xs-shadow-hover);
  transform: translateY(-3px);
}

.entry:hover::after {
  opacity: 1;
}

.entry-mark {
  position: relative;
  z-index: 1;
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 11px;
  background: linear-gradient(135deg, #f8f3e7 0%, #efe4cd 100%);
  color: #7a5a2c;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 19px;
  box-shadow: inset 0 0 0 1px rgba(138, 106, 59, 0.14);
}

.entry-body {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.entry-name {
  font-size: 14px;
  font-weight: 600;
}

.entry-desc {
  font-size: 11.5px;
  color: var(--xs-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feature {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: linear-gradient(160deg, #ffffff 0%, #fcfaf5 100%);
  padding: 18px 20px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.22s ease, transform 0.22s ease, border-color 0.22s ease;
}

.feature::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, #c29a5e, #8a6a3b);
  opacity: 0;
  transition: opacity 0.22s ease;
}

.feature:hover {
  border-color: rgba(138, 106, 59, 0.35);
  box-shadow: var(--xs-shadow-hover);
  transform: translateY(-2px);
}

.feature:hover::before {
  opacity: 1;
}

.feature-index {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 2px;
  color: var(--xs-accent);
  opacity: 0.65;
  margin-bottom: 6px;
  font-variant-numeric: tabular-nums;
}

.feature-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 8px;
}

.feature-body {
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.disclaimer {
  border: 1px dashed var(--xs-border);
  border-radius: 12px;
  background: #fbfaf6;
  padding: 18px 20px;
}

.disclaimer-title {
  font-weight: 600;
  margin-bottom: 8px;
}

.disclaimer ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}

@media (max-width: 1100px) {
  .entries {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .hero {
    grid-template-columns: 1fr;
    padding: 24px;
  }

  .features {
    grid-template-columns: 1fr;
  }

  .entries {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .entries {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
