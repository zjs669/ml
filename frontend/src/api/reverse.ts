/** 四柱反查：干支 → 公历日期。免登录、不落库。 */

import { http } from './client'
import type { ReverseSearchIn, ReverseSearchOut } from './types'

export async function reverseSearch(payload: ReverseSearchIn): Promise<ReverseSearchOut> {
  const { data } = await http.post<ReverseSearchOut>('/charts/bazi/reverse-search', payload)
  return data
}

/** 十天干、十二地支：顺序与后端一致，索引奇偶决定阴阳。 */
export const STEMS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸'] as const
export const BRANCHES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'] as const

/** 六十甲子：阳干配阳支、阴干配阴支，共 60 个。 */
export const JIAZI: string[] = Array.from({ length: 60 }, (_, index) => {
  const stem = STEMS[index % 10]
  const branch = BRANCHES[index % 12]
  return `${stem}${branch}`
})

/** 某一柱的全部合法取值：天干索引与地支索引同奇偶。 */
export function candidatesForPillar(stem: string | null, branch: string | null): string[] {
  if (!stem && !branch) return JIAZI
  const stemIndex = stem ? STEMS.indexOf(stem as (typeof STEMS)[number]) : -1
  const branchIndex = branch ? BRANCHES.indexOf(branch as (typeof BRANCHES)[number]) : -1
  return JIAZI.filter((_text, index) => {
    const s = index % 10
    const b = index % 12
    if (stemIndex >= 0 && s !== stemIndex) return false
    if (branchIndex >= 0 && b !== branchIndex) return false
    return true
  })
}
