import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
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
  {
    path: '/almanac',
    name: 'almanac',
    component: () => import('@/pages/AlmanacPage.vue'),
    meta: { title: '黄历' },
  },
  {
    path: '/xiaoliuren',
    name: 'xiaoliuren',
    component: () => import('@/pages/XiaoliurenPage.vue'),
    meta: { title: '小六壬' },
  },
  {
    path: '/tarot',
    name: 'tarot',
    component: () => import('@/pages/TarotPage.vue'),
    meta: { title: '塔罗' },
  },
  {
    path: '/meihua',
    name: 'meihua',
    component: () => import('@/pages/MeihuaPage.vue'),
    meta: { title: '梅花易数' },
  },
  {
    path: '/taiyi',
    name: 'taiyi',
    component: () => import('@/pages/TaiyiPage.vue'),
    meta: { title: '太乙九星' },
  },
  {
    path: '/daliuren',
    name: 'daliuren',
    component: () => import('@/pages/DaliurenPage.vue'),
    meta: { title: '大六壬' },
  },
  {
    path: '/astrology',
    name: 'astrology',
    component: () => import('@/pages/AstrologyPage.vue'),
    meta: { title: '西洋占星' },
  },
  {
    path: '/ziwei-horoscope',
    name: 'ziwei-horoscope',
    component: () => import('@/pages/ZiweiHoroscopePage.vue'),
    meta: { title: '紫微运限' },
  },
  {
    path: '/ziwei-flying',
    name: 'ziwei-flying',
    component: () => import('@/pages/ZiweiFlyingPage.vue'),
    meta: { title: '紫微飞星' },
  },
  {
    path: '/dream',
    name: 'dream',
    component: () => import('@/pages/DreamPage.vue'),
    meta: { title: '解梦' },
  },
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

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()
  if (to.meta.requiresAuth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = title ? `${title} · 玄枢国学研习台` : '玄枢国学研习台'
})

export default router
