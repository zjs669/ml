import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getUsage } from '@/api/me'
import type { Depth, UsageSnapshot } from '@/api/types'

/**
 * 额度缓存：生成报告前乐观扣减、失败回滚，最终仍以后端快照为准。
 * 这里只做展示优化，真正的扣费判定永远在服务端。
 */
export const useUsageStore = defineStore('usage', () => {
  const snapshot = ref<UsageSnapshot | null>(null)
  const loading = ref(false)

  const freeRemaining = computed(() => snapshot.value?.daily_free_remaining ?? 0)
  const paidBalance = computed(() => snapshot.value?.paid_balance ?? 0)
  const canGenerateBrief = computed(() => (snapshot.value?.can_generate ?? false) === true)

  async function load(): Promise<UsageSnapshot | null> {
    loading.value = true
    try {
      snapshot.value = await getUsage()
      return snapshot.value
    } catch {
      return null
    } finally {
      loading.value = false
    }
  }

  function clear(): void {
    snapshot.value = null
  }

  /** 返回回滚函数：调用方在请求失败时回滚。 */
  function optimisticDeduct(depth: Depth): () => void {
    const current = snapshot.value
    if (!current) return () => undefined
    const backup = { ...current }

    if (depth === 'detailed' && current.paid_balance > 0) {
      snapshot.value = { ...current, paid_balance: current.paid_balance - 1 }
    } else if (current.daily_free_remaining > 0) {
      snapshot.value = {
        ...current,
        daily_free_remaining: current.daily_free_remaining - 1,
        daily_free_used: current.daily_free_used + 1,
      }
    }

    return () => {
      snapshot.value = backup
    }
  }

  return { snapshot, loading, freeRemaining, paidBalance, canGenerateBrief, load, clear, optimisticDeduct }
})
