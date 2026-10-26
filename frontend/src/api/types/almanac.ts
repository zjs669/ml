/** 黄历（domain=almanac）的 chart_facts 形状。 */

export interface AlmanacPosition {
  branch: string
  desc: string
}

export interface AlmanacHourSlot {
  index: number
  ganzhi: string
  yi: string[]
  ji: string[]
  chong: string
  sha: string
  tian_shen_luck: string
}

export interface AlmanacFacts {
  date: {
    solar: string
    timezone: string
    weekday: number
    weekday_name: string
  }
  lunar_date: {
    text: string
    year: number
    month: number
    day: number
    is_leap_month: boolean
    year_ganzhi: string
    month_ganzhi: string
    day_ganzhi: string
    year_zodiac: string
  }
  day_pillar: {
    ganzhi: string
    na_yin: string
    zhi_xing: string
    tian_shen_luck: string
  }
  yi: string[]
  ji: string[]
  ji_shen: string[]
  xiong_sha: string[]
  chong: { desc: string; sheng_xiao: string; gan: string }
  sha_direction: string
  xiu: { name: string; luck: string; zheng: string; animal: string; song: string }
  nine_star: {
    full: string
    number: string
    color: string
    element: string
    position: string
    position_desc: string
    xuan_kong: { name: string; luck: string }
    qi_men: { name: string; luck: string }
    tai_yi: { name: string; type: string }
    bei_dou: string
  }
  positions: Record<string, AlmanacPosition>
  hour_slots: AlmanacHourSlot[]
  personal?: {
    birth_date: string
    birth_day_ganzhi: string
    birth_year_ganzhi: string
    birth_zodiac: string
    note: string
  }
}
