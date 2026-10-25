import { http } from './client'
import type {
  ForgotPasswordResponse,
  ResetPasswordResponse,
  SessionInfo,
  TokenResponse,
  UserProfile,
} from './types'

export interface RegisterPayload {
  email: string
  password: string
  display_name?: string | null
  consent?: { privacy_version?: string; terms_version?: string; accepted?: boolean }
}

export async function register(payload: RegisterPayload): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/register', payload)
  return data
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/login', { email, password })
  return data
}

export async function refresh(): Promise<TokenResponse> {
  const { data } = await http.post<TokenResponse>('/auth/refresh')
  return data
}

export async function logout(): Promise<void> {
  await http.post('/auth/logout')
}

export async function me(): Promise<UserProfile> {
  const { data } = await http.get<UserProfile>('/auth/me')
  return data
}

/** 申请重置密码：无论邮箱是否存在，后端返回同一句话（防枚举）。 */
export async function forgotPassword(email: string): Promise<ForgotPasswordResponse> {
  const { data } = await http.post<ForgotPasswordResponse>('/auth/password/forgot', { email })
  return data
}

/** 用一次性令牌设置新密码；成功后所有设备下线。 */
export async function resetPassword(token: string, password: string): Promise<ResetPasswordResponse> {
  const { data } = await http.post<ResetPasswordResponse>('/auth/password/reset', { token, password })
  return data
}

/** 当前仍然有效的 refresh 会话数 */
export async function sessions(): Promise<SessionInfo> {
  const { data } = await http.get<SessionInfo>('/auth/sessions')
  return data
}

/** 登出全部设备（= 作废所有 refresh 会话并让 token_version 前进） */
export async function revokeSessions(): Promise<SessionInfo> {
  const { data } = await http.delete<SessionInfo>('/auth/sessions')
  return data
}
