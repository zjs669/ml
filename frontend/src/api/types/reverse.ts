/** 四柱反查（干支 → 公历日期）。 */

import type { Convention } from './common'

export interface PillarQuery {
  year?: string | null
  month?: string | null
  day?: string | null
  hour?: string | null
}

export interface ReverseSearchIn {
  pillars: PillarQuery
  range_start: string
  range_end: string
  timezone: string
  longitude?: number | null
  convention: Partial<Convention>
  limit?: number
  offset?: number
}

export interface ReverseCandidate {
  date: string
  hour_windows: string[]
  pillars: Record<string, string>
  confidence: 'exact' | 'partial'
  notes: string[]
}

export interface ReverseSearchOut {
  query: Record<string, string | null>
  convention: Record<string, unknown>
  searched_days: number
  total_matches: number
  truncated: boolean
  offset: number
  limit: number
  candidates: ReverseCandidate[]
  diagnosis: string[]
  warnings: string[]
  algorithm_version: string
}

/* ---- 紫微斗数（domain=ziwei 的 chart_facts 形状）---- */
