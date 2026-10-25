<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import * as chartsApi from '@/api/charts'
import * as meApi from '@/api/me'
import { useAuthStore } from '@/stores/auth'
import { useUsageStore } from '@/stores/usage'
import type { ChartListItem, OrderSummary, UsageSnapshot } from '@/api/types'

const router = useRouter()
const auth = useAuthStore()
const usage = useUsageStore()

const tab = ref('charts')

const charts = ref<ChartListItem[]>([])
const total = ref(0)
const page = ref(1)
const size = 10
const chartsLoading = ref(false)

const orders = ref<OrderSummary[]>([])
const ledger = ref<meApi.LedgerRow[]>([])
const consents = ref<meApi.ConsentRow[]>([])
const snapshot = ref<UsageSnapshot | null>(null)

const displayName = ref('')
const profileSaving = ref(false)

const deletePassword = ref('')
const deleting = ref(false)

async function loadCharts(): Promise<void> {
  chartsLoading.value = true
  try {
    const data = await chartsApi.listCharts(page.value, size)
    charts.value = data.items
    total.value = data.total
  } finally {
    chartsLoading.value = false
  }
}

async function loadAll(): Promise<void> {
  await auth.bootstrap()
  if (!auth.isLoggedIn) return
  displayName.value = auth.user?.display_name ?? ''
  snapshot.value = await usage.load()
  const [orderData, ledgerData, consentData] = await Promise.all([
    meApi.myOrders(),
    meApi.myLedger(),
    meApi.myConsents(),
  ])
  orders.value = orderData.items
  ledger.value = ledgerData.items
  consents.value = consentData.items
  await loadCharts()
}

async function saveProfile(): Promise<void> {
  profileSaving.value = true
  try {
    const updated = await meApi.updateProfile(displayName.value || null)
    auth.setUser(updated)
    ElMessage.success('资料已更新')
  } finally {
    profileSaving.value = false
  }
}

async function downloadExport(): Promise<void> {
  const text = await meApi.exportMyData()
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'xuanshu-export.json'
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出你的全部数据（JSON）')
}

function openChart(row: ChartListItem): void {
  router.push(`/charts/${row.id}`)
}

async function deleteChart(id: number): Promise<void> {
  await ElMessageBox.confirm('删除后命盘与关联报告将不可访问。确定删除？', '删除命盘', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
  })
  await chartsApi.deleteChart(id)
  ElMessage.success('已删除')
  await loadCharts()
}

async function removeAccount(): Promise<void> {
  if (!deletePassword.value) {
    ElMessage.warning('请输入当前密码以确认注销')
    return
  }
  await ElMessageBox.confirm(
    '注销后账号进入待清理状态，30 天后物理删除；期间可联系管理员恢复。确定继续？',
    '注销账号',
    { type: 'warning', confirmButtonText: '确认注销', cancelButtonText: '取消' },
  )
  deleting.value = true
  try {
    await meApi.deleteAccount(deletePassword.value)
    ElMessage.success('账号已注销，即将退出登录')
    await auth.logout()
    router.push('/')
  } finally {
    deleting.value = false
  }
}

onMounted(async () => {
  await loadAll()
})
</script>

<template>
  <div class="account">
    <div class="page-head">
      <h2>我的账号</h2>
      <p>这里可以管理命盘、查看额度与订单、导出或删除你的数据。</p>
    </div>

    <el-empty v-if="!auth.isLoggedIn" description="请先登录后查看账号信息">
      <el-button type="primary" @click="router.push({ path: '/login', query: { redirect: '/account' } })">
        去登录
      </el-button>
    </el-empty>

    <template v-else>
      <div class="profile-card">
        <div class="profile-row">
          <span class="k">邮箱</span>
          <span class="v">{{ auth.user?.email }}</span>
        </div>
        <div class="profile-row">
          <span class="k">昵称</span>
          <span class="v input-row">
            <el-input v-model="displayName" placeholder="未设置" maxlength="80" style="width: 200px" />
            <el-button size="small" :loading="profileSaving" @click="saveProfile">保存</el-button>
          </span>
        </div>
        <div class="profile-row">
          <span class="k">注册时间</span>
          <span class="v">{{ auth.user?.created_at?.slice(0, 19) }}</span>
        </div>
        <div v-if="snapshot" class="profile-row">
          <span class="k">额度</span>
          <span class="v">
            每日免费 {{ snapshot.daily_free_remaining }} / {{ snapshot.daily_free_limit }} 次（重置时间
            {{ snapshot.daily_free_reset_at }}），付费余额 {{ snapshot.paid_balance }} 次
          </span>
        </div>
        <div class="profile-actions">
          <el-button size="small" @click="downloadExport">导出我的数据</el-button>
          <el-button size="small" @click="router.push('/pricing')">购买套餐</el-button>
          <el-button size="small" type="danger" plain @click="auth.logout().then(() => router.push('/'))">
            退出登录
          </el-button>
        </div>
      </div>

      <el-tabs v-model="tab">
        <el-tab-pane label="我的命盘" name="charts">
          <el-skeleton v-if="chartsLoading" :rows="3" animated />
          <el-empty v-else-if="!charts.length" description="还没有保存的命盘">
            <el-button type="primary" @click="router.push('/bazi')">去排盘</el-button>
          </el-empty>
          <template v-else>
            <el-table :data="charts" size="small" @row-click="openChart">
              <el-table-column prop="title" label="标题" min-width="140">
                <template #default="{ row }">{{ row.title || '未命名命盘' }}</template>
              </el-table-column>
              <el-table-column prop="pillars_text" label="四柱" min-width="160" />
              <el-table-column prop="day_master" label="日主" width="80" />
              <el-table-column prop="algorithm_version" label="算法版本" width="120" />
              <el-table-column prop="created_at" label="保存时间" width="170">
                <template #default="{ row }">{{ row.created_at.slice(0, 16) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="120">
                <template #default="{ row }">
                  <el-button size="small" text type="danger" @click.stop="deleteChart(row.id)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="pager">
              <el-pagination
                v-model:current-page="page"
                layout="prev, pager, next, total"
                :page-size="size"
                :total="total"
                @current-change="loadCharts"
              />
            </div>
          </template>
        </el-tab-pane>

        <el-tab-pane label="订单" name="orders">
          <el-empty v-if="!orders.length" description="还没有订单" :image-size="60" />
          <el-table v-else :data="orders" size="small">
            <el-table-column prop="order_no" label="订单号" min-width="180" />
            <el-table-column prop="plan_name" label="套餐" width="130" />
            <el-table-column prop="amount_text" label="金额" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column prop="created_at" label="创建时间" width="170">
              <template #default="{ row }">{{ row.created_at.slice(0, 16) }}</template>
            </el-table-column>
            <el-table-column prop="paid_at" label="支付时间" width="170">
              <template #default="{ row }">{{ row.paid_at ? row.paid_at.slice(0, 16) : '—' }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="额度流水" name="ledger">
          <p class="tab-hint">
            账本采用「预扣 / 结算 / 退还 / 发放」四类事件，净额为可用额度；同一幂等键的重复请求只记一次。
          </p>
          <el-empty v-if="!ledger.length" description="暂无流水" :image-size="60" />
          <el-table v-else :data="ledger" size="small">
            <el-table-column prop="created_at" label="时间" width="180">
              <template #default="{ row }">{{ row.created_at.slice(0, 19) }}</template>
            </el-table-column>
            <el-table-column prop="event_type" label="事件" width="100" />
            <el-table-column prop="units" label="变动" width="80" />
            <el-table-column prop="reference_type" label="关联类型" width="120" />
            <el-table-column prop="reference_id" label="关联 ID" width="120" />
            <el-table-column prop="note" label="备注" min-width="180" />
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="协议留痕" name="consents">
          <p class="tab-hint">注册时同意的协议版本与时间会留痕，撤回同意后相应权益随之变更。</p>
          <el-empty v-if="!consents.length" description="暂无协议留痕" :image-size="60" />
          <el-table v-else :data="consents" size="small">
            <el-table-column prop="doc_type" label="协议" width="160" />
            <el-table-column prop="doc_version" label="版本" width="160" />
            <el-table-column prop="consent_at" label="同意时间" width="180">
              <template #default="{ row }">{{ row.consent_at.slice(0, 19) }}</template>
            </el-table-column>
            <el-table-column prop="revoked_at" label="撤回时间" width="180">
              <template #default="{ row }">{{ row.revoked_at ? row.revoked_at.slice(0, 19) : '—' }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="删除账号" name="danger">
          <div class="danger-card">
            <div class="danger-title">注销账号</div>
            <p>
              注销后账号进入待清理状态，30 天后物理删除；期间你的命盘、报告与笔记均不可访问。
              若只是想清除某一份命盘，请到「我的命盘」里单独删除。
            </p>
            <div class="danger-row">
              <el-input v-model="deletePassword" type="password" placeholder="输入当前密码确认" style="width: 240px" show-password />
              <el-button type="danger" :loading="deleting" @click="removeAccount">注销账号</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<style scoped>
.account {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head h2 {
  margin: 0 0 6px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.profile-card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13px;
}

.profile-row {
  display: flex;
  gap: 10px;
  align-items: center;
}

.profile-row .k {
  flex: 0 0 72px;
  color: var(--xs-text-muted);
}

.profile-row .v {
  flex: 1;
}

.input-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.profile-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 6px;
}

.pager {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.tab-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.danger-card {
  border: 1px solid #e8b6b0;
  border-radius: 12px;
  background: #fdf3f2;
  padding: 16px 18px;
  font-size: 13px;
  line-height: 1.85;
  color: #7d3a34;
}

.danger-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.danger-row {
  display: flex;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}
</style>
