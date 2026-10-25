import { http } from './client'
import type { Depth, FollowupOut, ReportListItem, ReportOut } from './types'

export async function generateReport(
  chartId: number,
  options: { depth: Depth; topic?: string | null; skillKey?: string | null; idempotencyKey: string },
): Promise<ReportOut> {
  const { data } = await http.post<ReportOut>(
    `/charts/${chartId}/reports`,
    { depth: options.depth, topic: options.topic ?? null, skill_key: options.skillKey ?? null },
    { headers: { 'Idempotency-Key': options.idempotencyKey } },
  )
  return data
}

export async function getReport(id: number): Promise<ReportOut> {
  const { data } = await http.get<ReportOut>(`/reports/${id}`)
  return data
}

export async function listReports(chartId: number): Promise<ReportListItem[]> {
  const { data } = await http.get<ReportListItem[]>(`/charts/${chartId}/reports`)
  return data
}

/** 幂等键由「用户动作」决定：同一份盘 + 同一深度 + 同一分钟 = 同一次点击。 */
export function buildIdempotencyKey(chartId: number | string, depth: Depth): string {
  const minute = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '')
  const random = Math.random().toString(36).slice(2, 8)
  return `web-${chartId}-${depth}-${minute}-${random}`
}

/** 追问：只能针对某一份已生成的报告，不扣额度但受限流与日预算约束。 */
export async function askFollowup(reportId: number, question: string): Promise<FollowupOut> {
  const { data } = await http.post<FollowupOut>(`/reports/${reportId}/followups`, { question })
  return data
}

export async function listFollowups(reportId: number): Promise<FollowupOut[]> {
  const { data } = await http.get<FollowupOut[]>(`/reports/${reportId}/followups`)
  return data
}
