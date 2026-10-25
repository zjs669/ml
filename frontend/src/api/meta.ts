/** 站点元信息：口径说明、模型状态、技能清单。 */

import { ref } from 'vue'

import { http } from './client'

export interface LlmStatus {
  mode: string
  provider: string
  model: string
  configured: boolean
  disclosure: string
  json_mode: string
  budget_used: number
  budget_limit: number
  budget_exhausted: boolean
  recent: {
    window_hours: number
    calls: number
    failed: number
    success_rate: number | null
  }
}

/**
 * 全局只请求一次：页脚公示与报告徽章都要用它，
 * 每处各发一次请求既浪费也会让两个位置的文案不同步。
 */
const cache = ref<LlmStatus | null>(null)
let inflight: Promise<LlmStatus | null> | null = null

export async function getLlmStatus(force = false): Promise<LlmStatus | null> {
  if (cache.value && !force) return cache.value
  if (!inflight) {
    inflight = http
      .get<LlmStatus>('/meta/llm-status')
      .then((response) => {
        cache.value = response.data
        return response.data
      })
      .catch(() => null)
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

/** 页脚用：运营没填就不展示，绝不留「待填写」之类的占位。 */
export function getCachedDisclosure(): string {
  const text = (cache.value?.disclosure || '').trim()
  return text && text.toLowerCase() !== 'replace_with_secret' ? text : ''
}
