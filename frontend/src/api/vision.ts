/** 面相 / 手相：上传图片做视觉分析。 */

import { http } from './client'

export interface VisionType {
  id: string
  name: string
  description: string
}

export interface VisionTypes {
  face: { types: VisionType[]; disclaimer: string }
  palm: { types: VisionType[]; hand_types: Record<string, string>; disclaimer: string }
  max_bytes: number
}

export interface VisionResult {
  chart_id: number
  title: string | null
  domain: string
  algorithm_version: string
  media: {
    sha256: string
    mime: string
    width: number
    height: number
    size_bytes: number
    delete_after: string | null
  }
  chart_facts: Record<string, unknown>
  warnings: string[]
  source_refs: Array<Record<string, unknown>>
  degraded: boolean
  degraded_reason: string | null
  result?: Record<string, unknown>
  usage?: {
    provider: string
    model: string
    input_tokens: number | null
    output_tokens: number | null
    latency_ms: number
  }
}

export async function getTypes(): Promise<VisionTypes> {
  const { data } = await http.get<VisionTypes>('/vision/types')
  return data
}

export async function analyze(
  kind: 'face' | 'palm',
  file: File,
  options: {
    analysisType: string
    handType?: string
    question?: string
    storeQuestion?: boolean
    idempotencyKey: string
  },
): Promise<VisionResult> {
  const body = new FormData()
  body.append('file', file)
  body.append('analysis_type', options.analysisType)
  if (options.handType) body.append('hand_type', options.handType)
  if (options.question) body.append('question', options.question)
  body.append('store_question', String(options.storeQuestion ?? true))

  const { data } = await http.post<VisionResult>(`/vision/${kind}/analyze`, body, {
    headers: { 'Idempotency-Key': options.idempotencyKey },
  })
  return data
}
