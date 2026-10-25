<script setup lang="ts">
import { computed } from 'vue'

import { useUsageStore } from '@/stores/usage'
import type { Depth } from '@/api/types'

/**
 * 额度徽标：必须在点击「AI 解读」**之前**出现，
 * 同时说清将消耗多少额度、会上传哪些数据项（对应文档的数据最小化要求）。
 */
const props = defineProps<{
  depth: Depth
  /** 是否显示"将上传的数据项"清单 */
  showUpload?: boolean
}>()

const usage = useUsageStore()

const snapshot = computed(() => usage.snapshot)

const costText = computed(() => {
  if (props.depth === 'brief') return '1 次（优先使用每日免费额度）'
  return '1 次详版额度（优先使用付费额度）'
})

/** 预估剩余：详版优先扣付费余额，简版优先扣每日免费。 */
const remainingText = computed(() => {
  const snap = snapshot.value
  if (!snap) return '未加载（点击后由服务端判定）'
  if (props.depth === 'detailed') {
    if (snap.paid_balance > 0) return `付费余额 ${snap.paid_balance} 次，本次用 1 次`
    if (snap.daily_free_remaining > 0) return `无付费余额，将使用每日免费额度 ${snap.daily_free_remaining} 次中的 1 次`
    return '付费余额与每日免费额度均为 0，需要先购买套餐'
  }
  if (snap.daily_free_remaining > 0) return `每日免费剩余 ${snap.daily_free_remaining} / ${snap.daily_free_limit} 次`
  if (snap.paid_balance > 0) return `今日免费已用完，改扣付费余额 ${snap.paid_balance} 次中的 1 次`
  return '今日免费已用完且无付费余额'
})

const willBlock = computed(() => {
  const snap = snapshot.value
  if (!snap) return false
  if (props.depth === 'detailed') return snap.paid_balance <= 0 && snap.daily_free_remaining <= 0
  return snap.daily_free_remaining <= 0 && snap.paid_balance <= 0
})

const UPLOAD_ITEMS = [
  '四柱干支与藏干、十神（排盘事实快照）',
  '命盘触发的规则 ID 与来源标记',
  '知识库检索命中的片段正文',
  '本次选择的口径标识（立春/换日/真太阳时）',
]
</script>

<template>
  <div class="quota-badge" :class="{ blocked: willBlock }">
    <div class="line">
      <span class="k">本次将消耗</span>
      <span class="v">{{ costText }}</span>
    </div>
    <div class="line">
      <span class="k">额度现状</span>
      <span class="v">{{ remainingText }}</span>
    </div>
    <div v-if="showUpload" class="upload">
      <div class="upload-title">将上传给模型的数据项（不含邮箱、姓名等身份信息）</div>
      <ul>
        <li v-for="item in UPLOAD_ITEMS" :key="item">{{ item }}</li>
      </ul>
      <div class="upload-foot">
        不上传：账号信息、笔记正文、订单与支付数据；模型输出经服务端校验后才会保存。
      </div>
    </div>
    <div v-if="willBlock" class="warning">当前额度不足，请先到「套餐」页购买，或等次日免费额度刷新。</div>
  </div>
</template>

<style scoped>
.quota-badge {
  border: 1px dashed var(--xs-border);
  border-radius: 10px;
  background: var(--xs-surface-muted);
  padding: 10px 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--xs-text-muted);
}

.quota-badge.blocked {
  border-color: #d08a3a;
  background: #fdf6ec;
}

.line {
  display: flex;
  gap: 8px;
}

.k {
  flex: 0 0 58px;
  color: var(--xs-text-muted);
}

.v {
  flex: 1;
  color: var(--xs-text);
}

.upload {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--xs-border);
}

.upload-title {
  margin-bottom: 4px;
}

.upload ul {
  margin: 0;
  padding-left: 18px;
}

.upload-foot {
  margin-top: 4px;
}

.warning {
  margin-top: 8px;
  color: #a45f22;
}
</style>
