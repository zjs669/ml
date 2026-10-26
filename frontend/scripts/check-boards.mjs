/**
 * 盘面 SSR 冒烟：把三个新盘面用真实 chart_facts 渲染成 HTML 字符串。
 *
 * 为什么用 SSR 而不是浏览器：这里只验「组件拿到真实数据不崩、关键字段确实出现」，
 * 不验交互与样式。跑一次几秒，比 Playwright 便宜得多。
 */
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus from 'element-plus'
import { readFile } from 'node:fs/promises'

const facts = JSON.parse(await readFile(new URL('../../backend/var/board-facts.json', import.meta.url), 'utf8'))

const boards = {
  almanac: (await import('./src/components/chart/AlmanacBoard.vue')).default,
  tarot: (await import('./src/components/chart/TarotBoard.vue')).default,
  daliuren: (await import('./src/components/chart/DaliurenBoard.vue')).default,
}

const EXPECT = {
  almanac: ['宜', '忌', '值星', '时辰', '方位'],
  tarot: ['牌阵', '正位', '逆位'],
  daliuren: ['月将', '天地盘', '四课', '三传'],
}

let failed = 0
for (const [domain, Board] of Object.entries(boards)) {
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
  const app = createSSRApp({ render: () => h(Board, { result }) })
  app.use(createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }] }))
  app.use(ElementPlus)
  const html = await renderToString(app)
  const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
  const missing = EXPECT[domain].filter((word) => !text.includes(word))
  if (missing.length) {
    console.log('FAIL ' + domain + ': 缺少 ' + missing.join('、'))
    failed += 1
  } else {
    console.log('OK   ' + domain + ': html ' + html.length + 'B, text ' + text.length + 'B')
  }
  console.log('      ' + text.slice(0, 120))
}

if (failed) process.exit(1)
