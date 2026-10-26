/** AI 报告与追问。 */

import type { Depth } from './common'

export interface Observation {
  fact: string
  rule_ids: string[]
  citation_ids: number[]
}

export interface Interpretation {
  claim: string
  citation_ids: number[]
  school_note?: string | null
}

export interface ReportPayload {
  summary: string
  observations: Observation[]
  traditional_interpretations: Interpretation[]
  practical_reflections: string[]
  uncertainties: string[]
  citations: number[]
  safety_note: string
}

export interface Citation {
  chunk_id: number
  title: string
  citation_label: string
  location: string | null
  license_status: string
  snippet: string
}

export interface ReportOut {
  id: number
  chart_id: number | null
  domain: string
  depth: Depth
  status: 'complete' | 'degraded' | string
  model_provider: string
  model_name: string
  skill_version: string
  prompt_version: string
  algorithm_version: string
  chart_snapshot_hash: string
  report: ReportPayload
  citations: Citation[]
  validation: { ok?: boolean; fatal_codes?: string[]; issues?: unknown[]; replayed?: boolean } | null
  created_at: string
}

export interface ReportListItem {
  id: number
  chart_id: number | null
  depth: Depth
  status: string
  created_at: string
  summary: string | null
}

/** 一轮追问的答案：比报告窄，但仍带引用与免责声明 */

export interface FollowupAnswer {
  answer: string
  points: string[]
  citations: number[]
  uncertainties: string[]
  safety_note: string
}

export interface FollowupOut {
  id: number
  report_id: number
  seq: number
  question: string
  answer: FollowupAnswer
  citations: Citation[]
  status: 'complete' | 'degraded' | string
  model_provider: string
  model_name: string
  validation: { ok?: boolean; fatal_codes?: string[] } | null
  created_at: string
}
