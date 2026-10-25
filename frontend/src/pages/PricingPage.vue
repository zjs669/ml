<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import * as billingApi from '@/api/billing'
import { useAuthStore } from '@/stores/auth'
import { useUsageStore } from '@/stores/usage'
import type { BillingConfig, OrderCreated, PlanInfo, PlansResponse } from '@/api/types'

const router = useRouter()
const auth = useAuthStore()
const usage = useUsageStore()

const plans = ref<PlansResponse | null>(null)
const config = ref<BillingConfig | null>(null)
const loading = ref(true)
const buying = ref('')
const lastOrder = ref<OrderCreated | null>(null)
const method = ref('')
const confirmVisible = ref(false)
const pendingPlan = ref<PlanInfo | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [planData, configData] = await Promise.all([billingApi.listPlans(), billingApi.getConfig()])
    plans.value = planData
    config.value = configData
    // 默认选中后端声明的可用通道；都不可用时留空并提示
    method.value = configData.default_method || configData.methods.find((item) => item.available)?.code || ''
  } finally {
    loading.value = false
  }
}

function askBuy(plan: PlanInfo): void {
  if (!auth.isLoggedIn) {
    ElMessage.info('购买需要先登录')
    router.push({ path: '/login', query: { redirect: '/pricing' } })
    return
  }
  if (!method.value) {
    ElMessage.warning('当前没有可用支付通道')
    return
  }
  pendingPlan.value = plan
  confirmVisible.value = true
}

async function confirmPay(): Promise<void> {
  const plan = pendingPlan.value
  if (!plan) return
  buying.value = plan.code
  try {
    const created = await billingApi.createOrder(plan.code)
    lastOrder.value = created
    if (!created.mock_callback) {
      ElMessage.warning('订单已创建，但未返回 Mock 回调（生产环境需接真实支付）')
      return
    }
    const result = await billingApi.runMockCallback(created)
    if (result.status === 'ok' || result.status === 'duplicate') {
      ElMessage.success(`支付成功（Mock 通道），已发放 ${result.credits_granted ?? 0} 次额度`)
    } else {
      ElMessage.warning(`回调状态：${result.status}`)
    }
    await usage.load()
    confirmVisible.value = false
  } catch {
    // 拦截器已提示
  } finally {
    buying.value = ''
  }
}

onMounted(() => {
  void auth.bootstrap()
  void load()
  // 未登录访客不请求额度接口，避免无意义的 401
  if (auth.isLoggedIn) void usage.load()
})
</script>

<template>
  <div class="pricing">
    <div class="page-head">
      <h2>套餐与额度</h2>
      <p>
        当前为<strong>内测阶段</strong>：支付走 Mock 通道，不会产生真实扣款，定价仅用于验证计费链路。
        正式开放前，本页文案会重新核验合规性。
      </p>
    </div>

    <el-skeleton v-if="loading" :rows="5" animated />

    <!-- 支付配置：把「当前能不能真付款」写在明面上，而不是藏在按钮后面 -->
    <section v-if="config" class="pay-config">
      <div class="config-head">
        <span class="config-title">支付配置</span>
        <el-tag :type="config.mode === 'mock' ? 'warning' : 'success'" size="small" effect="plain">
          {{ config.mode === 'mock' ? 'Mock 通道' : '真实通道' }}
        </el-tag>
        <el-tag size="small" effect="plain" type="info">币种 {{ config.currency }}</el-tag>
        <el-tag size="small" effect="plain" type="info">套餐版本 {{ config.plan_version }}</el-tag>
        <el-tag :type="config.secret_rotated ? 'success' : 'danger'" size="small" effect="plain">
          {{ config.secret_rotated ? '回调密钥已轮换' : '回调密钥为默认值' }}
        </el-tag>
      </div>
      <div class="methods">
        <label
          v-for="item in config.methods"
          :key="item.code"
          class="method"
          :class="{ disabled: !item.available, active: method === item.code }"
        >
          <input v-model="method" type="radio" :value="item.code" :disabled="!item.available" />
          <span class="method-body">
            <span class="method-name">
              {{ item.label }}
              <el-tag v-if="!item.available" size="small" type="info" effect="plain">未接入</el-tag>
            </span>
            <span class="method-note">{{ item.note }}</span>
          </span>
        </label>
      </div>
      <p class="config-note">
        {{ config.notice }} 回调验签：<code>{{ config.callback_signature }}</code>；退款窗口
        {{ config.refund_window_days }} 天。
      </p>
    </section>

    <template v-if="!loading && plans">
      <div class="plans">
        <div v-for="plan in plans.plans" :key="plan.code" class="plan" :class="{ free: plan.code === 'free' }">
          <div class="plan-head">
            <span class="plan-name">{{ plan.name }}</span>
            <el-tag v-if="plan.code === 'free'" size="small" type="success" effect="plain">默认可用</el-tag>
            <el-tag v-else-if="plan.code === 'member_month'" size="small" type="warning" effect="plain">推荐</el-tag>
          </div>
          <div class="plan-price">
            <span class="num">{{ plan.amount_text }}</span>
            <span v-if="plan.duration_days > 0" class="unit">/ {{ plan.duration_days }} 天</span>
          </div>
          <div class="tagline">{{ plan.tagline }}</div>
          <ul>
            <li v-for="item in plan.features" :key="item">{{ item }}</li>
          </ul>
          <el-button
            v-if="plan.code === 'free'"
            class="plan-btn ghost"
            @click="router.push('/bazi')"
          >
            开始排盘
          </el-button>
          <el-button
            v-else
            class="plan-btn"
            type="primary"
            :disabled="!plan.purchasable"
            :loading="buying === plan.code"
            @click="askBuy(plan)"
          >
            {{ plan.purchasable ? (config?.mode === 'mock' ? '购买（Mock 支付）' : '立即购买') : '暂不可购买' }}
          </el-button>
        </div>
      </div>

      <div class="notes">
        <div class="note-card">
          <div class="note-title">额度消耗规则</div>
          <ul>
            <li>简版解读：优先消耗每日免费额度，免费额度用完后消耗付费额度。</li>
            <li>详版解读：优先消耗付费额度；没有付费额度时不允许生成，接口直接返回 402。</li>
            <li>生成失败（模型校验不通过并降级）不额外扣费；服务端采用「预扣 → 结算 → 失败退还」三态账本。</li>
            <li>同一个 <code>Idempotency-Key</code> 重复提交只会扣一次费。</li>
          </ul>
        </div>
        <div class="note-card">
          <div class="note-title">退款说明</div>
          <p>{{ plans.refund_policy }}</p>
          <p class="muted">{{ plans.billing_note }}</p>
        </div>
        <div class="note-card">
          <div class="note-title">当前额度</div>
          <p v-if="usage.snapshot">
            每日免费剩余 {{ usage.snapshot.daily_free_remaining }} / {{ usage.snapshot.daily_free_limit }} 次；
            付费余额 {{ usage.snapshot.paid_balance }} 次。
          </p>
          <template v-else>
            <p class="muted">登录后可查看实时额度、订单与扣费流水。</p>
            <el-button size="small" text type="primary" @click="router.push({ path: '/login', query: { redirect: '/pricing' } })">
              去登录 →
            </el-button>
          </template>
        </div>
      </div>

      <el-alert
        v-if="lastOrder"
        type="success"
        :closable="false"
        show-icon
        :title="`最近订单 ${lastOrder.order.order_no}：${lastOrder.order.plan_name} ${lastOrder.order.amount_text}（${lastOrder.order.status}）`"
        :description="lastOrder.mock_callback?.warning"
      />

      <div class="foot">
        套餐版本 {{ plans.plan_version }} · 币种 {{ plans.currency }}。
        本页不构成任何效果承诺：AI 解读属于传统文化研习内容，不提供预测或决策依据。
      </div>
    </template>

    <!-- 下单确认：先把「付多少、得多少、能不能退」说清，再进支付 -->
    <el-dialog v-model="confirmVisible" title="确认订单" width="420px">
      <div v-if="pendingPlan" class="confirm">
        <div class="confirm-row">
          <span class="k">套餐</span><span class="v">{{ pendingPlan.name }}</span>
        </div>
        <div class="confirm-row">
          <span class="k">金额</span>
          <span class="v strong">{{ pendingPlan.amount_text }}</span>
        </div>
        <div class="confirm-row">
          <span class="k">到账额度</span><span class="v">{{ pendingPlan.credits }} 次{{ pendingPlan.duration_days > 0 ? `（${pendingPlan.duration_days} 天内有效）` : '' }}</span>
        </div>
        <div class="confirm-row">
          <span class="k">支付方式</span>
          <span class="v">{{ config?.methods.find((item) => item.code === method)?.label || '—' }}</span>
        </div>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          :title="config?.mode === 'mock' ? '这是内测 Mock 支付，不会真实扣款' : '将跳转真实支付通道'"
          description="额度发放后可在「我的账号 · 额度流水」核对；生成失败会自动退还。"
        />
      </div>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="buying === pendingPlan?.code" @click="confirmPay">
          确认支付
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pricing {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head h2 {
  margin: 0 0 6px;
  font-size: 22px;
  letter-spacing: 1px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
  max-width: 760px;
}

.plans {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  align-items: stretch;
}

.plan {
  border: 1px solid var(--xs-border);
  border-radius: 14px;
  background: #fff;
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.plan:hover {
  box-shadow: var(--xs-shadow);
  transform: translateY(-1px);
}

.plan.free {
  background: var(--xs-surface-muted);
  box-shadow: none;
}

.plan-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plan-name {
  font-weight: 600;
  font-size: 15px;
}

.plan-price .num {
  font-size: 26px;
  font-weight: 600;
  color: var(--xs-accent);
}

.plan-price .unit {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-left: 4px;
}

.tagline {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.plan ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
  color: var(--xs-text-muted);
  flex: 1;
}

.plan-btn {
  width: 100%;
}

/* 免费套餐的按钮：白底 + 细边框，与旁边两个主按钮区分开 */
.plan-btn.ghost {
  border-color: rgba(138, 106, 59, 0.45);
  color: var(--xs-accent);
  background: #fff;
}

.notes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.note-card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.note-title {
  font-weight: 600;
  color: var(--xs-text);
  margin-bottom: 6px;
}

.note-card ul {
  margin: 0;
  padding-left: 18px;
}

.note-card p {
  margin: 0 0 6px;
}

.muted {
  font-size: 12px;
}

.foot {
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.8;
  border-top: 1px dashed var(--xs-border);
  padding-top: 10px;
}

.pay-config {
  border: 1px solid var(--xs-border);
  border-radius: 14px;
  background: #fff;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.config-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.config-title {
  font-weight: 600;
  font-size: 14px;
  margin-right: 4px;
}

.methods {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.method {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  background: #fff;
}

.method.active {
  border-color: var(--xs-accent);
  background: #fdfaf3;
}

.method.disabled {
  cursor: not-allowed;
  opacity: 0.6;
  border-style: dashed;
}

.method input {
  margin-top: 3px;
  accent-color: var(--xs-accent);
}

.method-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.method-name {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.method-note {
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
  /* 通道说明偏长，超过两行就省略，避免三列卡片高度被一行长文撑歪 */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.config-note {
  margin: 0;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.8;
}

.confirm {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.confirm-row .k {
  color: var(--xs-text-muted);
}

.confirm-row .v.strong {
  color: var(--xs-accent);
  font-weight: 600;
}

@media (max-width: 1000px) {
  .plans,
  .methods {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .plans,
  .methods {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
