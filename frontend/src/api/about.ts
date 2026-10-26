/** 站点统计与版本信息：`GET /meta/about`。

原先前端 0 处调用这个接口，导致首页把「关系规则 48 条」硬编码在模板里，
而后端实际是 66 条。数字类信息一律从这里取，不在 Vue 里写死。
*/

import { http } from './client'

export interface AboutInfo {
  app_name: string
  algorithm_version: string
  relations_rule_version: string
  relations_rule_count: number
  prompt_version: string
  llm_mode: string
  skills: { skill_key: string; version: string; title: string }[]
  approved_chunks: number
  legal: { privacy_version: string; terms_version: string }
  ai_notice: string
  supported_domains: string[]
  planned_domains: string[]
}

let cache: AboutInfo | null = null
let inflight: Promise<AboutInfo | null> | null = null

/** 全局只请求一次：首页与关于区块都要用，数字必须来自同一份快照。 */
export async function getAbout(force = false): Promise<AboutInfo | null> {
  if (cache && !force) return cache
  if (!inflight) {
    inflight = http
      .get<AboutInfo>('/meta/about')
      .then((response) => {
        cache = response.data
        return response.data
      })
      .catch(() => null)
      .finally(() => {
        inflight = null
      })
  }
  return inflight
}
