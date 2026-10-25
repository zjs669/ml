import { http } from './client'
import type { OrderSummary, UsageSnapshot, UserProfile } from './types'

export async function getUsage(): Promise<UsageSnapshot> {
  const { data } = await http.get<UsageSnapshot>('/me/usage')
  return data
}

export async function myOrders(): Promise<{ count: number; items: OrderSummary[] }> {
  const { data } = await http.get<{ count: number; items: OrderSummary[] }>('/me/orders')
  return data
}

export interface LedgerRow {
  id: number
  event_type: string
  units: number
  reference_type: string | null
  reference_id: string | null
  note: string | null
  created_at: string
}

export async function myLedger(): Promise<{ count: number; items: LedgerRow[] }> {
  const { data } = await http.get<{ count: number; items: LedgerRow[] }>('/me/ledger')
  return data
}

export async function updateProfile(displayName: string | null): Promise<UserProfile> {
  const { data } = await http.patch<UserProfile>('/me/profile', { display_name: displayName })
  return data
}

export interface ConsentRow {
  doc_type: string
  doc_version: string
  consent_at: string
  revoked_at: string | null
}

export async function myConsents(): Promise<{ items: ConsentRow[] }> {
  const { data } = await http.get<{ items: ConsentRow[] }>('/me/consents')
  return data
}

export async function exportMyData(): Promise<string> {
  const { data } = await http.get<string>('/me/export', { responseType: 'text' })
  return data
}

export async function deleteAccount(password: string): Promise<void> {
  await http.delete('/me', { data: { password, confirm: 'DELETE' } })
}

export interface FeedbackPayload {
  rating?: number | null
  category?: string
  content?: string
  report_id?: number | null
}

export async function sendFeedback(payload: FeedbackPayload): Promise<{ id: number }> {
  const { data } = await http.post<{ id: number }>('/feedback', payload)
  return data
}
