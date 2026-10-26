/** 性格问卷题库：题目与维度定义都由后端提供。 */

import { http } from './client'

export interface MbtiQuestion {
  id: string
  dimension: string
  text: string
  option_a: string
  option_b: string
}

export interface MbtiDimensionDef {
  dimension: string
  name: string
  poles: Record<string, string>
}

export interface MbtiBank {
  bank_version: string
  dimensions: MbtiDimensionDef[]
  questions: MbtiQuestion[]
  school_note: string
}

export async function getBank(): Promise<MbtiBank> {
  const { data } = await http.get<MbtiBank>('/mbti/questions')
  return data
}
