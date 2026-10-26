/** 公共基础类型：位置、深度、来源引用、错误体、四柱口径。 */

export type Position = 'year' | 'month' | 'day' | 'hour'

export type Depth = 'brief' | 'detailed'

export interface SourceRef {
  type: string
  id: string
  note: string
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string | null; details?: unknown }
}

/** 六爻单爻：本卦纳甲六亲六神 + 若为动爻则附变爻信息 */

export interface Convention {
  year_boundary: string
  day_boundary: string
  solar_time: string
  school: string
  five_element_weight: string
  shensha_variant?: string
  day_boundary_note?: string
}
