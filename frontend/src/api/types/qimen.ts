/** 奇门遁甲（domain=qimen）的 chart_facts 形状与表单入参。 */

import type { ChartResult } from './charts'
import type { TermInfo } from './bazi'

export interface QimenPalace {
  number: number
  name: string
  trigram: string
  direction: string
  element: string
  earth_stem: string
  sky_stem: string | null
  extra_sky_stem: string | null
  star: string
  extra_star: string | null
  door: string | null
  deity: string | null
  is_center: boolean
  is_zhifu: boolean
  is_zhishi: boolean
  note?: string
}

export interface QimenFacts {
  cast_at: string
  timezone: string
  pillars: Record<'year' | 'month' | 'day' | 'hour', { stem: string; branch: string; text: string }>
  term: TermInfo
  dun: { type: string; is_yang: boolean; yuan: string; ju: number; text: string }
  fu_tou: { pillar: string; branch: string; yuan: string; date: string }
  xun_kong: { xun_head: string; instrument: string; branches: string[] }
  zhifu: {
    star: string
    instrument: string
    palace: number
    palace_name: string
    landing_palace: number
    landing_name: string
  }
  zhishi: { door: string; palace: number; palace_name: string; steps: number }
  hour_stem_palace: { stem: string; palace: number; palace_name: string }
  ma_star: { branch: string; palace: number; palace_name: string }
  fuyin: { star: boolean; door: boolean }
  palaces: QimenPalace[]
  three_marvels: { stem: string; palace: number; palace_name: string }[]
}

/** 奇门口径：只有一个学派，字段与四柱/紫微/六爻均不相交 */

export interface QimenConvention {
  school?: string
  dun_basis?: string
  yuan_method?: string
  center_palace?: string
  day_boundary?: string
  school_note?: string
}

export interface QimenChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: QimenFacts
  convention: QimenConvention
}

export interface QimenFormInput {
  cast_datetime: string
  timezone: string
  convention: Partial<QimenConvention>
}
