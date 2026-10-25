import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as chartsApi from '@/api/charts'
import type { BaziFormInput, ChartOut, ChartResult } from '@/api/types'

export function defaultBaziForm(): BaziFormInput {
  const now = new Date()
  return {
    birth_datetime: `${now.getFullYear() - 30}-01-01T12:00:00`,
    timezone: 'Asia/Shanghai',
    longitude: null,
    time_known: true,
    gender: 'unknown',
    convention: {},
    // 流年窗口由用户显式给定：默认从今年起的 10 年，保存后随盘一起冻结
    liunian_start_year: now.getFullYear(),
    liunian_years: 10,
  }
}

/**
 * 匿名排盘结果只存在内存（Pinia），刷新即失；
 * 想要长期保存必须显式点"保存命盘"，由后端重新计算后入库。
 */
export const useChartStore = defineStore('chart', () => {
  const form = ref<BaziFormInput>(defaultBaziForm())
  const result = ref<ChartResult | null>(null)
  const loading = ref(false)
  const saved = ref<ChartOut | null>(null)

  async function calculate(): Promise<ChartResult> {
    loading.value = true
    try {
      const data = await chartsApi.calculate(form.value)
      result.value = data
      saved.value = null
      return data
    } finally {
      loading.value = false
    }
  }

  async function save(title: string, deleteAfterDays?: number | null): Promise<ChartOut> {
    loading.value = true
    try {
      const chart = await chartsApi.saveChart(form.value, title, deleteAfterDays)
      saved.value = chart
      return chart
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    form.value = defaultBaziForm()
    result.value = null
    saved.value = null
  }

  return { form, result, loading, saved, calculate, save, reset }
})
