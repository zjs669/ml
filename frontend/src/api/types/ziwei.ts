/** 紫微斗数（domain=ziwei）的 chart_facts 形状与表单入参。 */

import type { ChartResult } from './charts'

export interface ZiweiLunarDate {
  year: number
  month: number
  day: number
  is_leap_month: boolean
  month_name: string
  day_name: string
  text: string
}

export interface ZiweiTransformationInPalace {
  type: string
  star: string
}

export interface ZiweiPalace {
  order: number
  name: string
  branch: string
  heavenly_stem: string
  is_body: boolean
  main_stars: string[]
  aux_stars: string[]
  /** 杂曜：天刑、红鸾、华盖等，只作事实陈列。旧盘（扩充前保存）没有该字段 */
  minor_stars?: string[]
  stars: string[]
  /** 长生十二神之一（旧盘没有） */
  life_cycle?: string | null
  /** 博士十二神之一（旧盘没有） */
  bo_shi?: string | null
  /** 将前十二神 */
  jiang_qian?: string
  /** 岁前十二神 */
  sui_qian?: string
  /** 自化：本宫宫干四化仍落本宫的类型 */
  self_hua?: string[]
  /** 小限岁数（每 12 年一个） */
  xiaoxian_ages?: number[]
  /** 流年虚岁 */
  liunian_ages?: number[]
  /** 三方四正四宫名 */
  sanfang?: string[]
  transformations: ZiweiTransformationInPalace[]
  dayun: { start_age: number; end_age: number }
}

export interface ZiweiTransformation {
  type: string
  star: string
  palace: string
  branch: string
}

export interface ZiweiDayunItem {
  index: number
  palace: string
  branch: string
  start_age: number
  end_age: number
}

export interface ZiweiFacts {
  lunar_date: ZiweiLunarDate
  solar_date: string
  year_ganzhi: string
  year_zodiac: string
  hour_branch: string
  hour_known: boolean
  five_element_bureau: {
    element: string
    number: number
    name: string
    life_palace_nayin: string
  }
  life_palace: { branch: string; heavenly_stem: string; text: string; palace: string }
  body_palace: { branch: string; palace: string }
  ziwei_star: { branch: string; palace: string }
  si_hua: Record<string, string>
  palaces: ZiweiPalace[]
  transformations: ZiweiTransformation[]
  /** 宫干四化：12 宫 × 4 化 = 48 条，飞星层（旧盘没有） */
  palace_transformations?: ZiweiPalaceTransformation[]
  /** 仅入参给了 review_age 时存在 */
  dayun_transformation?: ZiweiPeriodTransformation
  /** 仅入参给了 review_year 时存在 */
  liunian_transformation?: ZiweiPeriodTransformation
  dayun: ZiweiDayunItem[]
  dayun_forward: boolean
  /** 流年表：年份 / 虚岁 / 干支 / 流年命宫 */
  liunian_table?: ZiweiLiunianRow[]
  /** 飞星串联：只列链路，不推事件 */
  flying?: ZiweiFlying
  timezone: string
}

export interface ZiweiLiunianRow {
  year: number
  virtual_age: number
  pillar: string
  palace: string
}

export interface ZiweiFlyingHop {
  palace: string
  type: string
  star: string
  to_palace: string
}

export interface ZiweiFlyingChain {
  start_palace: string
  start_stem: string
  hops: ZiweiFlyingHop[]
  cycle: boolean
}

export interface ZiweiFlying {
  depth: number
  starts: string[]
  chains: ZiweiFlyingChain[]
  truncated: boolean
  rule: string
}

/** 飞星四化：某个宫的宫干把哪颗星化成了什么，落在哪个宫 */

export interface ZiweiPalaceTransformation {
  from_palace: string
  stem: string
  type: string
  star: string
  to_palace: string
  to_branch: string
}

/** 大限 / 流年四化：只描述这一层用哪个宫干推出来的四化 */

export interface ZiweiPeriodTransformation {
  stem: string
  branch?: string
  palace: string
  items: ZiweiTransformation[]
  age?: number
  year?: number
  ganzhi?: string
}

/** 紫微口径：字段与四柱完全不相交，因此单独声明，不复用 `Convention`。 */

export interface ZiweiConvention {
  calendar_basis?: string
  year_boundary?: string
  school?: string
  leap_month?: string
  zi_hour?: string
  school_note?: string
}

export interface ZiweiChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: ZiweiFacts
  convention: ZiweiConvention
}

export interface ZiweiFormInput {
  calendar: 'gregorian' | 'lunar'
  birth_datetime: string
  is_leap_month: boolean
  timezone: string
  time_known: boolean
  gender: 'male' | 'female' | 'unknown'
  /** 可选：虚岁，给了才算大限四化 */
  review_age?: number | null
  /** 可选：农历年，给了才算流年四化 */
  review_year?: number | null
  /** 飞星串联深度，默认 2 */
  flying_depth?: 1 | 2 | 3
}
