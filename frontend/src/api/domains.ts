/** 已接入的术数清单：由后端 registry 提供，前端不硬编码域名与流派。 */

import { ref } from 'vue'

import { http } from './client'

export interface DomainInfo {
  domain: string
  label: string
  kind: 'deterministic' | 'generative'
  schools: string[]
  requires_media: boolean
}

const cache = ref<DomainInfo[] | null>(null)
let inflight: Promise<DomainInfo[]> | null = null

/**
 * 全局只请求一次：工具页、路由守卫、盘面分发器都要用它，
 * 各页各发一次既浪费，也会让「已上线清单」在两次渲染之间不一致。
 */
export async function getDomains(force = false): Promise<DomainInfo[]> {
  if (cache.value && !force) return cache.value
  if (!inflight) {
    inflight = http
      .get<{ domains: DomainInfo[]; count: number }>('/meta/domains')
      .then((response) => {
        cache.value = response.data.domains
        return response.data.domains
      })
      .catch(() => [])
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}

export function domainLabel(domain: string): string {
  return cache.value?.find((item) => item.domain === domain)?.label ?? domain
}
