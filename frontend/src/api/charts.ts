import { http } from './client'
import type {
  BaziFormInput,
  ChartListItem,
  ChartOut,
  ChartPage,
  ChartResult,
  SharePreview,
} from './types'

export interface CalculateResponse extends ChartResult {}

function toRequestBody(form: BaziFormInput) {
  return {
    birth_datetime: form.birth_datetime,
    timezone: form.timezone,
    longitude: form.longitude,
    time_known: form.time_known,
    gender: form.gender,
    convention: form.convention,
    // 流年窗口是显式入参：不传后端就不算，保证「同一输入同一结果」
    liunian_start_year: form.liunian_start_year ?? null,
    liunian_years: form.liunian_years ?? 10,
  }
}

/** 免登录排盘：不落库，结果只留在前端内存里。 */
export async function calculate(form: BaziFormInput): Promise<CalculateResponse> {
  const { data } = await http.post<CalculateResponse>('/charts/bazi/calculate', toRequestBody(form))
  return data
}

export async function saveChartFor(
  domain: string,
  payload: Record<string, unknown>,
  title?: string,
  deleteAfterDays?: number | null,
): Promise<ChartOut> {
  const { data } = await http.post<ChartOut>(`/charts/${domain}`, {
    ...payload,
    title: title ?? null,
    delete_after_days: deleteAfterDays ?? null,
  })
  return data
}

/**
 * 通用排盘入口：`domain` 由后端 registry 分发（bazi / ziwei / liuyao / qimen）。
 * 各术数入参不同，因此入参不在这里做类型约束，由调用页自己保证。
 */
export async function calculateFor(
  domain: string,
  payload: Record<string, unknown>,
): Promise<ChartResult> {
  const { data } = await http.post<ChartResult>(`/charts/${domain}/calculate`, payload)
  return data
}

export async function saveChart(
  form: BaziFormInput,
  title?: string,
  deleteAfterDays?: number | null,
): Promise<ChartOut> {
  const { data } = await http.post<ChartOut>('/charts', {
    ...toRequestBody(form),
    title: title ?? null,
    delete_after_days: deleteAfterDays ?? null,
  })
  return data
}

export async function listCharts(page = 1, size = 20, domain?: string): Promise<ChartPage> {
  const { data } = await http.get<ChartPage>('/charts', { params: { page, size, domain } })
  return data
}

export async function getChart(id: number): Promise<ChartOut> {
  const { data } = await http.get<ChartOut>(`/charts/${id}`)
  return data
}

export async function patchChart(
  id: number,
  payload: { title?: string | null; visibility?: 'private' | 'link'; delete_after_days?: number },
): Promise<ChartOut> {
  const { data } = await http.patch<ChartOut>(`/charts/${id}`, payload)
  return data
}

export async function deleteChart(id: number): Promise<void> {
  await http.delete(`/charts/${id}`)
}

export interface NoteItem {
  id: number
  content: string
  created_at: string
}

export async function listNotes(chartId: number): Promise<NoteItem[]> {
  const { data } = await http.get<NoteItem[]>(`/charts/${chartId}/notes`)
  return data
}

export async function addNote(chartId: number, content: string): Promise<NoteItem> {
  const { data } = await http.post<NoteItem>(`/charts/${chartId}/notes`, { content })
  return data
}

export async function deleteNote(chartId: number, noteId: number): Promise<void> {
  await http.delete(`/charts/${chartId}/notes/${noteId}`)
}

export async function exportChart(chartId: number, format: 'md' | 'txt'): Promise<string> {
  const { data } = await http.get<string>(`/charts/${chartId}/export`, {
    params: { format },
    responseType: 'text',
  })
  return data
}

export async function createShare(
  chartId: number,
  expiresInDays = 7,
  redactLevel: 'basic' | 'full' = 'basic',
): Promise<{ token: string; expires_at: string; note: string }> {
  const { data } = await http.post(`/charts/${chartId}/share`, {
    expires_in_days: expiresInDays,
    redact_level: redactLevel,
  })
  return data
}

export async function revokeShare(token: string): Promise<void> {
  await http.delete(`/share/${token}`)
}

export async function previewShare(token: string): Promise<SharePreview> {
  const { data } = await http.get<SharePreview>(`/share/${token}`)
  return data
}

export type { ChartListItem }
