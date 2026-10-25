/**
 * Axios 封装：
 * - 统一带 Authorization；
 * - 401 时自动 refresh 一次（并发请求共享同一个 refresh promise）；
 * - 所有失败都转成 Element Plus 通知，并把 {code,message,request_id} 呈现给用户。
 */

import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiErrorBody, TokenResponse } from './types'
import { clearToken, getToken, setToken } from './token'

const BASE_URL = import.meta.env.VITE_API_BASE || '/api/v1'

export const http: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  withCredentials: true,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = axios
      // 用裸 axios，避免拦截器递归
      .post<TokenResponse>(`${BASE_URL}/auth/refresh`, null, { withCredentials: true })
      .then((response) => {
        setToken(response.data.access_token)
        return response.data.access_token
      })
      .catch(() => {
        clearToken()
        return null
      })
      .finally(() => {
        refreshing = null
      })
  }
  return refreshing
}

export interface ApiError extends Error {
  code: string
  status: number
  requestId?: string | null
  details?: unknown
}

function toApiError(error: AxiosError<ApiErrorBody>): ApiError {
  const status = error.response?.status ?? 0
  const body = error.response?.data
  const payload = body && typeof body === 'object' && 'error' in body ? body.error : undefined
  const result = new Error(payload?.message || error.message || '请求失败') as ApiError
  result.code = payload?.code || (status ? `HTTP_${status}` : 'NETWORK_ERROR')
  result.status = status
  result.requestId = payload?.request_id
  result.details = payload?.details
  return result
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    const status = error.response?.status
    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/register')

    // 只有「本来带着 access token」的请求才值得去 refresh；
    // 未登录访客的 401 直接失败，避免控制台里留下无意义的 /auth/refresh 报错
    if (status === 401 && original && !original._retried && !isAuthCall && getToken()) {
      original._retried = true
      const token = await refreshAccessToken()
      if (token) {
        original.headers.Authorization = `Bearer ${token}`
        return http.request(original)
      }
      clearToken()
    }

    const apiError = toApiError(error)
    // 401 由页面自己引导登录，不弹重复通知
    if (apiError.status !== 401) {
      ElMessage.error({
        message: apiError.requestId ? `${apiError.message}（请求号 ${apiError.requestId}）` : apiError.message,
        duration: 5000,
        showClose: true,
      })
    }
    return Promise.reject(apiError)
  },
)
