/**
 * SSR 渲染冒烟共用：创建 app 并装好 pinia / element-plus / id 提供器。
 *
 * 为什么要给 Element Plus 提供 ID / Z-INDEX：
 * 它在 SSR 下要求 `app.provide(ID_INJECTION_KEY, ...)`，否则每个表单组件都会
 * 打一条 `ElementPlusError: [IdInjection] Looks like you are using server rendering`，
 * 几十条警告会把真正的 FAIL 行淹掉。这两个 key 只是给 SSR 一个确定性起点。
 */
import { createSSRApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus, { ID_INJECTION_KEY, ZINDEX_INJECTION_KEY } from 'element-plus'

export function createSmokeApp(root) {
  const app = createSSRApp(root)
  app.use(createPinia())
  app.use(ElementPlus)
  app.provide(ID_INJECTION_KEY, { prefix: 1000, current: 0 })
  app.provide(ZINDEX_INJECTION_KEY, { current: 0 })
  return app
}
