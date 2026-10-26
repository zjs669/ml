/**
 * 盘面 SSR 冒烟：用真实 chart_facts 把每个专属盘面渲染成 HTML。
 *
 * 为什么用 SSR 而不是浏览器：这里只验「组件拿到真实数据不崩、关键字段确实出现」，
 * 不验交互与样式。跑一次几秒，比 Playwright 便宜得多。
 *
 * 覆盖范围必须与 `ChartBoard.vue` 的 `BOARDS` 登记表一致：
 * 有专属盘面就要有样本，否则「新增盘面忘了验」只能靠人记。
 */
import { h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createRouter, createMemoryHistory } from 'vue-router'
import { readFile } from 'node:fs/promises'

import { createSmokeApp } from './smoke-app.mjs'

const facts = JSON.parse(
  await readFile(new URL('../../backend/var/board-facts.json', import.meta.url), 'utf8'),
)

const boards = {
  almanac: (await import('./src/components/chart/AlmanacBoard.vue')).default,
  tarot: (await import('./src/components/chart/TarotBoard.vue')).default,
  daliuren: (await import('./src/components/chart/DaliurenBoard.vue')).default,
  astrology: (await import('./src/components/chart/AstrologyBoard.vue')).default,
  meihua: (await import('./src/components/chart/MeihuaBoard.vue')).default,
}

/** 每个盘面必须出现的词。少一个就说明该块没渲染出来。 */
const EXPECT = {
  almanac: ['宜', '忌', '值星', '时辰', '方位'],
  tarot: ['牌阵', '正位', '逆位'],
  daliuren: ['月将', '天地盘', '四课', '三传'],
  astrology: ['上升点', '天顶', '十二宫', '相位', '未计算'],
  meihua: ['本卦', '互卦', '变卦', '错卦', '综卦', '体用'],
}

let failed = 0
let checked = 0

for (const [domain, Board] of Object.entries(boards)) {
  if (!facts[domain]) {
    console.log('FAIL ' + domain + ': board-facts.json 里没有该域样本，先跑 scripts.dump_board_facts')
    failed += 1
    continue
  }
  const result = {
    domain,
    algorithm_version: 'ssr-check',
    input_summary: {},
    convention: {},
    chart_facts: facts[domain],
    triggered_rules: [],
    warnings: [],
    source_refs: [],
  }
  const app = createSmokeApp({ render: () => h(Board, { result }) })
  app.use(
    createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div/>' } }],
    }),
  )
  const html = await renderToString(app)
  const text = html
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  const missing = EXPECT[domain].filter((word) => !text.includes(word))
  if (missing.length) {
    console.log('FAIL ' + domain + ': 缺少 ' + missing.join('、'))
    failed += 1
  } else {
    checked += 1
    console.log('OK   ' + domain + ': html ' + html.length + 'B, text ' + text.length + 'B')
  }
  console.log('      ' + text.slice(0, 120))
}

console.log('\n' + checked + '/' + Object.keys(boards).length + ' 个盘面通过')
if (failed) process.exit(1)
