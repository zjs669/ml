<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as metaApi from '@/api/meta'
import { DOMAIN_ENTRIES, entriesByGroup } from '@/config/domains'
import { useAuthStore } from '@/stores/auth'
import { useUsageStore } from '@/stores/usage'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const usage = useUsageStore()

/**
 * 一级导航只放「跨域」入口。
 * 术数入口统一收进「排盘」下拉 —— 16 个域 + 反查 + 面相 + 手相共 19 项，
 * 平铺会换行，也会让「黄历」和「四柱」看起来同等重要。
 */
const NAV = [
  { to: '/', label: '首页' },
  { to: '/tools', label: '工具' },
  { to: '/knowledge', label: '知识库' },
  { to: '/pricing', label: '套餐' },
]

/** 下拉里的分组，与 config/domains.ts 同一份数据。 */
const domainGroups = entriesByGroup()

/** 当前路径是否落在某个术数入口下（用于给「排盘」加高亮）。 */
const inDomain = computed(() => DOMAIN_ENTRIES.some((item) => item.path === route.path))

const activePath = computed(() => route.path)

const quotaText = computed(() => {
  const snap = usage.snapshot
  if (!snap) return ''
  return `免费 ${snap.daily_free_remaining} · 付费 ${snap.paid_balance}`
})

/** 模型公示：只有运营真的填了才展示，不留占位。 */
const disclosure = computed(() => metaApi.getCachedDisclosure())

async function onLogout(): Promise<void> {
  await auth.logout()
  usage.clear()
  router.push('/')
}

function go(path: string): void {
  router.push(path)
}

onMounted(async () => {
  await auth.bootstrap()
  if (auth.isLoggedIn) await usage.load()
  await metaApi.getLlmStatus().catch(() => null)
})
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="header-inner">
        <router-link to="/" class="brand">
          <span class="brand-mark">玄</span>
          <span class="brand-text">玄枢国学研习台</span>
        </router-link>

        <nav class="nav">
          <router-link
            v-for="item in NAV.slice(0, 2)"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ active: activePath === item.to }"
          >
            {{ item.label }}
          </router-link>

          <el-dropdown trigger="hover" placement="bottom-start" popper-class="nav-dropdown">
            <span class="nav-link dropdown-trigger" :class="{ active: inDomain }">
              排盘
              <span class="caret">▾</span>
            </span>
            <template #dropdown>
              <div class="dropdown-body">
                <div v-for="bucket in domainGroups" :key="bucket.group" class="dropdown-group">
                  <div class="dropdown-group-title">{{ bucket.group }}</div>
                  <button
                    v-for="entry in bucket.items"
                    :key="entry.key"
                    class="dropdown-item"
                    :class="{ current: activePath === entry.path }"
                    @click="go(entry.path)"
                  >
                    <span class="dropdown-mark">{{ entry.mark }}</span>
                    <span class="dropdown-label">{{ entry.label }}</span>
                    <span v-if="entry.requiresAuth" class="dropdown-lock">需登录</span>
                  </button>
                </div>
              </div>
            </template>
          </el-dropdown>

          <router-link
            v-for="item in NAV.slice(2)"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ active: activePath === item.to }"
          >
            {{ item.label }}
          </router-link>
        </nav>

        <div class="account">
          <template v-if="auth.isLoggedIn">
            <router-link to="/pricing" class="quota">{{ quotaText }}</router-link>
            <router-link to="/account" class="nav-link">我的账号</router-link>
            <el-button size="small" text @click="onLogout">退出</el-button>
          </template>
          <template v-else>
            <router-link to="/login" class="nav-link">登录</router-link>
          </template>
        </div>
      </div>

      <div class="ai-banner">
        本站 AI 生成内容已在页面与导出文本中显式标识 · 内容仅供传统文化研习参考，不构成任何专业建议
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <footer class="app-footer">
      <div class="footer-inner">
        <div class="footer-col">
          <div class="footer-title">关于</div>
          <p>
            玄枢国学研习台：确定性排盘 + 规则引擎 + 可校验的 AI 解释。已开放 16 个术数：
            四柱八字与反查、紫微斗数（三合派，含运限与飞星）、六爻（京房纳甲）、奇门遁甲（时家转盘拆补）、
            大六壬、梅花易数、小六壬、太乙九星、黄历、塔罗、西洋占星、关系合盘、性格问卷、解梦，
            以及面相与手相两个视觉域。内测阶段收取的是 Mock 支付，不产生真实扣款。
          </p>
        </div>
        <div class="footer-col">
          <div class="footer-title">术数入口</div>
          <router-link v-for="entry in DOMAIN_ENTRIES" :key="entry.key" :to="entry.path">
            {{ entry.label }}
          </router-link>
        </div>
        <div class="footer-col">
          <div class="footer-title">合规</div>
          <router-link to="/legal/privacy">隐私政策</router-link>
          <router-link to="/legal/terms">用户协议</router-link>
          <router-link to="/legal/ai">AI 使用说明</router-link>
          <router-link to="/legal/refund">退款说明</router-link>
          <router-link to="/legal/complaint">投诉与联系</router-link>
          <router-link to="/forgot-password">账号找回</router-link>
        </div>
        <div class="footer-col">
          <div class="footer-title">声明</div>
          <p>
            本站不提供疾病诊断、法律意见、投资建议与博彩相关内容。排盘结果取决于你填写的出生时间与地点，口径差异已在结果中回显。
          </p>
        </div>
      </div>
      <div class="footer-bottom">
        © 2026 玄枢国学研习台 · 内测版本 V1
        <span v-if="disclosure"> · {{ disclosure }}</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--xs-bg);
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(252, 250, 245, 0.82);
  backdrop-filter: blur(14px) saturate(1.15);
  border-bottom: 1px solid rgba(227, 222, 209, 0.9);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.7) inset, 0 10px 30px rgba(120, 98, 60, 0.06);
}

.header-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 10px 20px;
  display: flex;
  align-items: center;
  gap: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: var(--xs-text);
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: linear-gradient(135deg, #8a6a3b 0%, #b48d55 55%, #d9b87c 100%);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 18px;
  box-shadow: 0 6px 16px rgba(138, 106, 59, 0.3), 0 0 0 1px rgba(255, 255, 255, 0.35) inset;
}

.brand-text {
  font-weight: 600;
  letter-spacing: 1.5px;
}

.nav {
  display: flex;
  gap: 4px;
  flex: 1;
  flex-wrap: wrap;
}

.nav-link {
  font-size: 13px;
  color: var(--xs-text-muted);
  text-decoration: none;
  padding: 6px 11px;
  border-radius: 999px;
  transition: color 0.16s ease, background 0.16s ease, box-shadow 0.16s ease;
}

.nav-link:hover {
  background: rgba(138, 106, 59, 0.08);
  color: var(--xs-accent);
}

.nav-link.active {
  color: #6f5327;
  font-weight: 600;
  background: linear-gradient(135deg, rgba(138, 106, 59, 0.16), rgba(194, 154, 94, 0.12));
  box-shadow: inset 0 0 0 1px rgba(138, 106, 59, 0.18);
}

.nav-link.active:hover {
  text-decoration: none;
}

.account {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quota {
  font-size: 12px;
  color: #6f5327;
  text-decoration: none;
  background: linear-gradient(135deg, rgba(138, 106, 59, 0.12), rgba(194, 154, 94, 0.16));
  border-radius: 999px;
  padding: 4px 11px;
  box-shadow: inset 0 0 0 1px rgba(138, 106, 59, 0.14);
}

.ai-banner {
  font-size: 11px;
  color: #7c5518;
  background: linear-gradient(90deg, #fdf6ec 0%, #fbf1e0 50%, #fdf6ec 100%);
  text-align: center;
  padding: 5px 10px;
  border-top: 1px solid #f2e5cf;
  letter-spacing: 0.2px;
}

.app-main {
  flex: 1;
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 22px 20px 40px;
}

.app-footer {
  border-top: 1px solid var(--xs-border);
  background: #fff;
}

.footer-inner {
  max-width: 1240px;
  margin: 0 auto;
  padding: 22px 20px 10px;
  display: grid;
  grid-template-columns: 1.5fr 0.9fr 0.9fr 1.2fr;
  gap: 18px;
}

/* 术数入口有 19 条，单列会拉得比其它列长一倍 */
.footer-col:nth-child(2) a {
  display: inline-block;
  width: 50%;
}

.footer-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.footer-col p {
  margin: 0;
  font-size: 12px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.footer-col a {
  display: block;
  font-size: 12px;
  color: var(--xs-text-muted);
  text-decoration: none;
  line-height: 1.95;
}

.footer-col a:hover {
  color: var(--xs-accent);
}

.footer-bottom {
  text-align: center;
  font-size: 11px;
  color: var(--xs-text-muted);
  padding: 10px 0 16px;
}


.dropdown-trigger {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  user-select: none;
}

.caret {
  font-size: 9px;
  opacity: 0.65;
  transform: translateY(-1px);
}

.dropdown-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(160px, 1fr));
  gap: 4px 10px;
  padding: 8px 6px;
  max-height: 70vh;
  overflow-y: auto;
}

.dropdown-group-title {
  font-size: 11px;
  color: var(--xs-text-muted);
  letter-spacing: 0.6px;
  padding: 8px 10px 4px;
  border-bottom: 1px dashed var(--xs-border);
  margin-bottom: 2px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 7px 10px;
  border-radius: 9px;
  cursor: pointer;
  font-size: 13px;
  color: var(--xs-text);
  text-align: left;
  transition: background 0.15s ease, color 0.15s ease;
}

.dropdown-item:hover {
  background: rgba(138, 106, 59, 0.09);
  color: var(--xs-accent);
}

.dropdown-item.current {
  background: linear-gradient(135deg, rgba(138, 106, 59, 0.16), rgba(194, 154, 94, 0.12));
  font-weight: 600;
  color: #6f5327;
}

.dropdown-mark {
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 7px;
  background: #f6f1e6;
  color: var(--xs-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 12px;
}

.dropdown-label {
  flex: 1;
}

.dropdown-lock {
  font-size: 10px;
  color: var(--xs-text-muted);
  background: var(--xs-surface-muted);
  border-radius: 999px;
  padding: 1px 6px;
}

@media (max-width: 720px) {
  .header-inner {
    flex-wrap: wrap;
    gap: 8px;
  }

  .nav {
    order: 3;
    width: 100%;
  }
}
</style>
