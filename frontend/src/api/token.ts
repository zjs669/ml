/** 访问令牌的最小持有者：避免 axios 与 pinia store 相互 import 造成循环依赖。 */

const STORAGE_KEY = 'xuanshu.access_token'

let cached: string | null = sessionStorage.getItem(STORAGE_KEY)

export function getToken(): string | null {
  return cached
}

export function setToken(token: string): void {
  cached = token
  sessionStorage.setItem(STORAGE_KEY, token)
}

export function clearToken(): void {
  cached = null
  sessionStorage.removeItem(STORAGE_KEY)
}
