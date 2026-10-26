/** 四柱八字（domain=bazi）的 chart_facts 形状与表单入参。 */

import type { Convention, Position } from './common'

export interface HiddenStem {
  stem: string
  level: string
  weight: number
  element: string
  ten_god: string
}

export interface PillarFact {
  stem: string
  branch: string
  text: string
  stem_element: string
  stem_polarity: string
  branch_element: string
  ten_god: string
  uncertain?: boolean
  hidden_stems: HiddenStem[]
  /** 纳音（如「屋上土」） */
  nayin?: string
  /** 本柱旬空二支 */
  xun_kong?: string[]
  /** 地势：日干对本支的十二长生位 */
  dishi?: string
  /** 自坐：本柱干对本支的十二长生位 */
  zizuo?: string
}

/** 神煞命中项：只报位置，不评价吉凶 */

export interface ShenshaItem {
  name: string
  positions: Position[]
  basis: string
  source_ref: string
  variant?: boolean
}

export interface ShenshaFacts {
  items: ShenshaItem[]
  by_pillar: Record<Position, string[]>
  variant: string
}

export interface TermInfo {
  name: string
  instant_utc: string
  local: string
  timezone: string
  source: string
}

export interface DayunItem {
  index: number
  pillar: string
  start_age_years: number
  end_age_years: number
  start_year: number
}

export interface DayunFacts {
  computed: boolean
  reason?: string
  forward?: boolean
  rule?: string
  start_offset_days?: number
  start_age?: { years: number; months: number; days: number; text: string }
  start_datetime_estimate?: string
  error_bound?: string
  list?: DayunItem[]
}

export interface TriggeredRule {
  rule_id: string
  relation: string
  topic: string
  label: string
  note: string
  positions: Position[]
  priority: number
  source_ref: string
  version: string
  system: string
  scope: string
  members: string[]
  duplicated_branches?: Record<string, Position[]>
}

export interface IncompleteRelation {
  rule_id: string
  relation: string
  members_present: string[]
  positions: Position[]
  note: string
  source_ref: string
}

export interface ConflictItem {
  type: string
  positions: Position[]
  relations: string[]
  rule_ids: string[]
  note: string
}

export interface RelationsAnalysis {
  rules: TriggeredRule[]
  incomplete: IncompleteRelation[]
  conflicts: ConflictItem[]
  summary: Record<string, number>
  count: number
}

/** 一柱流年：干支 + 十神 + 虚岁 + 所属大运 + 立春交节 */

export interface LiunianItem {
  year: number
  pillar: string
  stem: string
  branch: string
  stem_element: string
  branch_element: string
  ten_god: string
  virtual_age: number
  lichun_local: string
  dayun_pillar: string | null
  dayun_index: number | null
}

export interface LiunianFacts {
  start_year: number
  years: number
  /** 年界口径：lichun / lichun_day，与年柱保持一致 */
  boundary_rule?: string
  rule: string
  list: LiunianItem[]
}

export interface ChartFacts {
  pillars: Record<Position, PillarFact>
  order: Position[]
  day_master: { stem: string; element: string; polarity: string }
  ten_gods: Record<string, string>
  five_elements_count: {
    raw: Record<string, number>
    weighted: Record<string, number>
    missing: string[]
    weight_rule: string
  }
  jieqi: {
    prev: TermInfo
    next: TermInfo
    minutes_to_prev: number
    minutes_to_next: number
  }
  dayun: DayunFacts
  /** 流年窗口：只有入参给了 liunian_start_year 才存在 */
  liunian?: LiunianFacts
  /** 神煞：与关系规则分开，不参与 rule_id 校验 */
  shensha?: ShenshaFacts
  solar_time_adjust: {
    applied: boolean
    delta_minutes: number
    longitude?: number
    method: string
  }
  hour_confidence: string
  timezone: string
  relations?: RelationsAnalysis
}

export interface BaziFormInput {
  birth_datetime: string
  timezone: string
  longitude: number | null
  time_known: boolean
  gender: 'male' | 'female' | 'unknown'
  convention: Partial<Convention>
  /** 可选：流年窗口起始年；不传则不计算流年 */
  liunian_start_year?: number | null
  /** 流年条数，默认 10 */
  liunian_years?: number
}

/* ---- 四柱反查（干支 → 公历日期）---- */
