/**
 * 路由渲染冒烟：用 memory history 真渲染每个域路由，确认不是空白页。
 *
 * 为什么需要它：SPA 对任何路径都返回 index.html（200），HTTP 状态码不能证明
 * 「这个路由的组件真的渲染出了表单」。这里 SSR 渲染一遍，断言每页出现预期标题 ——
 * 尤其验证「10 个同构域共用 DomainChartPage + props 传 domain」这条链没断：
 * 漏传 domain 或配置表缺键时组件会抛错，这里立刻红。
 *
 * 必须用 `vite.smoke.config.ts`（关掉依赖预打包）：默认配置会把 vue 预打包到
 * `node_modules/.vite/deps`，与源码 import 的 vue 形成双实例，
 * `renderSlot` 会抛 `Cannot read properties of null (reading 'ce')`。
 */
import { h } from 'vue'
import { RouterView, createRouter, createMemoryHistory } from 'vue-router'
import { renderToString } from '@vue/server-renderer'

import { createSmokeApp } from './smoke-app.mjs'
import { routes } from '../src/router/routes.ts'

/** 路径 → 该页必须出现的词。 */
const EXPECT = {
  '/almanac': ['黄历', '日期'],
  '/xiaoliuren': ['小六壬'],
  '/meihua': ['梅花易数'],
  '/daliuren': ['大六壬'],
  '/taiyi': ['太乙'],
  '/tarot': ['塔罗'],
  '/astrology': ['西洋占星'],
  '/ziwei-horoscope': ['紫微运限'],
  '/ziwei-flying': ['紫微飞星'],
  '/dream': ['解梦'],
  '/tools': ['工具', '命理排盘'],
  '/': ['玄枢国学研习台'],
}

let failed = 0

for (const [path, words] of Object.entries(EXPECT)) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()

  const app = createSmokeApp({ render: () => h(RouterView) })
  app.use(router)

  let text = ''
  try {
    const html = await renderToString(app)
    text = html
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  } catch (error) {
    console.log('FAIL ' + path + ': 渲染抛错 ' + error.message)
    failed += 1
    continue
  }

  const missing = words.filter((word) => !text.includes(word))
  if (missing.length) {
    console.log('FAIL ' + path + ': 缺少 ' + missing.join('、') + ' | ' + text.slice(0, 120))
    failed += 1
  } else {
    console.log('OK   ' + path.padEnd(18) + ' text ' + text.length + 'B')
  }
}

const total = Object.keys(EXPECT).length
console.log('\n' + (total - failed) + '/' + total + ' 路由通过')
process.exit(failed ? 1 : 0)
