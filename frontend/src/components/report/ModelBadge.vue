<script setup lang="ts">
/**
 * 模型标识徽章：让用户一眼看出「这份解读是真模型写的」还是「演示模板」。
 * 不猜、不美化——只要后端报告 `configured=false` 或 provider=fallback，就明说。
 */
import { computed, onMounted, ref } from 'vue'

import * as metaApi from '@/api/meta'

const props = defineProps<{
  /** 报告实际使用的 provider；fallback 表示降级模板 */
  provider?: string
  /** 报告实际使用的模型名 */
  model?: string
  /** 是否降级 */
  degraded?: boolean
}>()

const status = ref<metaApi.LlmStatus | null>(null)

onMounted(async () => {
  try {
    status.value = await metaApi.getLlmStatus()
  } catch {
    status.value = null
  }
})

const isMock = computed(() => {
  if (props.provider) return props.provider === 'mock' || props.provider === 'fallback'
  return !status.value?.configured
})

const label = computed(() => {
  if (props.provider === 'fallback') return '降级模板（未使用模型输出）'
  if (isMock.value) return '演示模型（Mock，内容为事实模板）'
  return `真实模型 · ${props.model || status.value?.model || '未知'}`
})

const tagType = computed(() => {
  if (props.provider === 'fallback' || props.degraded) return 'warning'
  return isMock.value ? 'info' : 'success'
})

const tooltip = computed(() => {
  if (!status.value) return label.value
  const parts = [
    `模式：${status.value.mode}`,
    `模型：${status.value.model}`,
    `JSON 模式：${status.value.json_mode}`,
    `今日调用：${status.value.budget_used}/${status.value.budget_limit || '不限'}`,
  ]
  if (status.value.recent.calls) {
    const rate = status.value.recent.success_rate
    parts.push(
      `近 ${status.value.recent.window_hours} 小时：${status.value.recent.calls} 次调用${
        rate === null ? '' : `，成功率 ${(rate * 100).toFixed(0)}%`
      }`,
    )
  }
  if (status.value.budget_exhausted) parts.push('今日模型调用预算已用尽，新解读会走降级模板')
  return parts.join('\n')
})
</script>

<template>
  <el-tooltip :content="tooltip" placement="bottom" effect="dark">
    <el-tag size="small" :type="tagType" effect="plain" class="model-badge">{{ label }}</el-tag>
  </el-tooltip>
</template>

<style scoped>
.model-badge {
  cursor: help;
  white-space: normal;
}
</style>
