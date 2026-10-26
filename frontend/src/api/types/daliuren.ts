/** 大六壬（domain=daliuren）的 chart_facts 形状。 */

export interface DaliurenPlateRow {
  earth: string
  sky: string
  general: string | null
  sky_element: string
}

export interface DaliurenLesson {
  index: number
  lower: string
  upper: string
  text: string
  note: string
  upper_element: string
  lower_element: string
}

export interface DaliurenChuanItem {
  branch: string
  general?: string
  element?: string
  chang_sheng?: string
  from_lesson?: number
  text?: string
}

export interface DaliurenFacts {
  datetime: { solar: string; lunar: string; timezone: string; hour_branch: string }
  pillars: { year: string; month: string; day: string; hour: string }
  month_general: { branch: string; name: string; source: string; qi: string | null }
  day_night: { value: 'day' | 'night'; rule: string }
  plate: DaliurenPlateRow[]
  four_lessons: DaliurenLesson[]
  san_chuan: {
    first: DaliurenChuanItem
    middle: DaliurenChuanItem
    last: DaliurenChuanItem
    method: string
  } | null
  san_chuan_status: {
    implemented: boolean
    method: string | null
    reason: string | null
    candidates: Array<{ index: number; text: string }>
  }
  shen_sha: {
    tian_ma: string
    jian_chu: string
    lodge: string
    gui_ren: { yang: string; yin: string; used: string }
  }
}
