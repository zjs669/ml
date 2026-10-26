/** 六爻（domain=liuyao）的 chart_facts 形状与表单入参。 */

import type { ChartResult } from './charts'

export interface LiuyaoLine {
  position: number
  polarity: string
  najia: string
  stem: string
  branch: string
  element: string
  six_relation: string
  liu_shen: string
  shi: boolean
  ying: boolean
  value?: number
  moving?: boolean
  changed?: { polarity: string; najia: string; element: string; six_relation: string }
}

/** 一卦（本卦或变卦）：卦宫、世应与六爻 */

export interface LiuyaoHexagram {
  name: string
  upper: string
  lower: string
  bits: string
  palace: string
  palace_element: string
  phase: string
  shi: number
  ying: number
  is_pure: boolean
  lines: LiuyaoLine[]
}

export interface LiuyaoFacts {
  method: 'coins' | 'time' | 'manual' | string
  method_label: string
  cast_at: string
  timezone: string
  lunar_date: { year: number; month: number; day: number; is_leap_month: boolean; text: string; year_ganzhi: string }
  hour_branch: string
  day_pillar: { text: string; stem: string; branch: string }
  month_build: { branch: string; jie: string; text: string; source: string }
  xun_kong: string[]
  liu_shen_order: string[]
  seed: number | null
  time_numbers: {
    upper_number: number
    lower_number: number
    moving_position: number
    year_number: number
    month_number: number
    day_number: number
    hour_number: number
  } | null
  question: string | null
  question_stored: boolean
  values: number[]
  moving_lines: number[]
  original: LiuyaoHexagram
  changed: LiuyaoHexagram | null
  mutual: { name: string; upper: string; lower: string; palace: string }
}

/** 六爻口径：字段与四柱、紫微均不相交，因此单独声明 */

export interface LiuyaoConvention {
  school?: string
  day_boundary?: string
  month_basis?: string
  school_note?: string
}

export interface LiuyaoChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: LiuyaoFacts
  convention: LiuyaoConvention
}

export interface LiuyaoFormInput {
  method: 'coins' | 'time' | 'manual'
  cast_datetime: string
  timezone: string
  seed?: number | null
  lines?: number[] | null
  question?: string | null
  store_question: boolean
}

/* ---- 奇门遁甲（domain=qimen 的 chart_facts 形状）---- */

/** 一宫：地盘干、天盘干、星、门、神；中五宫无门无神 */
