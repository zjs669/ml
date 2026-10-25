import { http } from './client'
import type { KnowledgeChunkDetail, KnowledgeHit } from './types'

export interface SearchResponse {
  query: string
  count: number
  items: KnowledgeHit[]
}

export async function searchKnowledge(query: string, domain = 'bazi'): Promise<SearchResponse> {
  const { data } = await http.get<SearchResponse>('/knowledge/search', { params: { q: query, domain } })
  return data
}

export async function getChunk(chunkId: number): Promise<KnowledgeChunkDetail> {
  const { data } = await http.get<KnowledgeChunkDetail>(`/knowledge/chunks/${chunkId}`)
  return data
}

export interface KnowledgeStats {
  approved_chunks?: number
  topics?: { topic: string; count: number }[]
  [key: string]: unknown
}

export async function knowledgeStats(): Promise<KnowledgeStats> {
  const { data } = await http.get<KnowledgeStats>('/knowledge/stats')
  return data
}
