import type { RouteRecordRaw } from 'vue-router'

/**
 * 路由表（纯数据，不含 router 实例）。
 *
 * 为什么单独一个文件：`scripts/check-routes.mjs` 要在 Node 里用 memory history
 * 渲染每个路由做冒烟，而 `index.ts` 末尾会 `createWebHistory()` —— 那个函数
 * 一执行就摸 `window`，在 Node 里直接抛错。把表拆出来，冒烟脚本只 import 表。
 */

/** 同构域：路径 → 后端 registry 里的 domain。 */
const GENERIC_DOMAINS: Array<{ path: string; name: string; domain: string; title: string }> = [
  { path: '/almanac', name: 'almanac', domain: 'almanac', title: '黄历' },
  { path: '/xiaoliuren', name: 'xiaoliuren', domain: 'xiaoliuren', title: '小六壬' },
  { path: '/meihua', name: 'meihua', domain: 'meihua', title: '梅花易数' },
  { path: '/daliuren', name: 'daliuren', domain: 'daliuren', title: '大六壬' },
  { path: '/taiyi', name: 'taiyi', domain: 'taiyi', title: '太乙九星' },
  { path: '/tarot', name: 'tarot', domain: 'tarot', title: '塔罗' },
  { path: '/astrology', name: 'astrology', domain: 'astrology', title: '西洋占星' },
  {
    path: '/ziwei-horoscope',
    name: 'ziwei-horoscope',
    domain: 'ziwei_horoscope',
    title: '紫微运限',
  },
  {
    path: '/ziwei-flying',
    name: 'ziwei-flying',
    domain: 'ziwei_flying',
    title: '紫微飞星',
  },
  { path: '/dream', name: 'dream', domain: 'dream', title: '解梦' },
]

/** 导出给渲染冒烟用（`scripts/check-routes.mjs`），也便于单测直接断言路由表。 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/pages/HomePage.vue'),
    meta: { title: '玄枢国学研习台' },
  },
  {
    path: '/tools',
    name: 'tools',
    component: () => import('@/pages/ToolsPage.vue'),
    meta: { title: '工具' },
  },
  {
    path: '/bazi',
    name: 'bazi',
    component: () => import('@/pages/BaziPage.vue'),
    meta: { title: '四柱排盘' },
  },
  {
    path: '/reverse',
    name: 'reverse',
    component: () => import('@/pages/ReversePage.vue'),
    meta: { title: '四柱反查' },
  },
  {
    path: '/ziwei',
    name: 'ziwei',
    component: () => import('@/pages/ZiweiPage.vue'),
    meta: { title: '紫微斗数' },
  },
  {
    path: '/liuyao',
    name: 'liuyao',
    component: () => import('@/pages/LiuyaoPage.vue'),
    meta: { title: '六爻' },
  },
  {
    path: '/qimen',
    name: 'qimen',
    component: () => import('@/pages/QimenPage.vue'),
    meta: { title: '奇门遁甲' },
  },

  // ---- 同构域：共用 DomainChartPage ----
  ...GENERIC_DOMAINS.map((item) => ({
    path: item.path,
    name: item.name,
    component: () => import('@/pages/DomainChartPage.vue'),
    // 把 domain 作为 prop 传进去，组件不必依赖 useRoute() 注入
    props: () => ({ domain: item.domain }),
    meta: { title: item.title, domain: item.domain },
  })),

  {
    path: '/mbti',
    name: 'mbti',
    component: () => import('@/pages/MbtiPage.vue'),
    meta: { title: '性格问卷' },
  },
  {
    path: '/hepan',
    name: 'hepan',
    component: () => import('@/pages/HepanPage.vue'),
    meta: { title: '关系合盘' },
  },
  {
    path: '/face',
    name: 'face',
    component: () => import('@/pages/FacePage.vue'),
    meta: { title: '面相观察', requiresAuth: true },
  },
  {
    path: '/palm',
    name: 'palm',
    component: () => import('@/pages/PalmPage.vue'),
    meta: { title: '手相观察', requiresAuth: true },
  },
  {
    path: '/charts/:id',
    name: 'chart-detail',
    component: () => import('@/pages/ChartDetailPage.vue'),
    meta: { title: '命盘详情', requiresAuth: true },
  },
  {
    path: '/knowledge',
    name: 'knowledge',
    component: () => import('@/pages/KnowledgePage.vue'),
    meta: { title: '知识库' },
  },
  {
    path: '/pricing',
    name: 'pricing',
    component: () => import('@/pages/PricingPage.vue'),
    meta: { title: '套餐与额度' },
  },
  {
    path: '/account',
    name: 'account',
    component: () => import('@/pages/AccountPage.vue'),
    meta: { title: '我的账号', requiresAuth: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { title: '登录 / 注册' },
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('@/pages/ForgotPasswordPage.vue'),
    meta: { title: '找回密码' },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('@/pages/ResetPasswordPage.vue'),
    meta: { title: '设置新密码' },
  },
  {
    path: '/share/:token',
    name: 'share',
    component: () => import('@/pages/SharePage.vue'),
    meta: { title: '分享的命盘' },
  },
  {
    path: '/legal/:doc(privacy|terms|ai|refund|complaint)',
    name: 'legal',
    component: () => import('@/pages/LegalPage.vue'),
    meta: { title: '合规文档' },
  },
  {
    path: '/legal',
    redirect: '/legal/privacy',
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFoundPage.vue'),
    meta: { title: '页面不存在' },
  },
]
