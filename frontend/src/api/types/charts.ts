/** 命盘通用外壳：ChartResult 及列表 / 分享。 */

import type { ChartFacts, TriggeredRule } from './bazi'
import type { Convention, SourceRef } from './common'

export interface ChartResult {
  domain: string
  algorithm_version: string
  input_summary: Record<string, unknown>
  convention: Convention
  chart_facts: ChartFacts
  triggered_rules: TriggeredRule[]
  warnings: string[]
  source_refs: SourceRef[]
}

export interface ChartOut extends ChartResult {
  id: number
  title: string | null
  created_at: string
  updated_at: string
}

export interface ChartListItem {
  id: number
  title: string | null
  domain: string
  created_at: string
  algorithm_version: string
  day_master: string | null
  pillars_text: string | null
}

export interface ChartPage {
  items: ChartListItem[]
  total: number
  page: number
  size: number
}

export interface SharePreview {
  title: string | null
  domain: string
  pillars_text: string
  chart_facts: ChartFacts
  triggered_rules: TriggeredRule[]
  warnings: string[]
  algorithm_version: string
  convention: Convention
  expires_at: string
}
