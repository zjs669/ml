/** 知识库检索结果。 */

export interface KnowledgeHit {
  chunk_id: number
  topic: string
  title: string
  citation_label: string
  location: string | null
  license_status: string
  snippet: string
  score: number
}

export interface KnowledgeChunkDetail extends KnowledgeHit {
  content: string
  approval_status: string
  content_hash: string
  source: {
    id: number | null
    title: string | null
    author: string | null
    edition: string | null
    license_status: string | null
    status: string | null
  }
}
