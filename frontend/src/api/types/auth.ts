/** 账号、令牌与会话。 */

export interface UserProfile {
  id: number
  email: string | null
  display_name: string | null
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: UserProfile
}

export interface ForgotPasswordResponse {
  message: string
  expires_in_minutes: number
  /** 仅开发环境（APP_ENV=development 且 MAIL_MODE=console）返回，生产恒为 null */
  debug_reset_url: string | null
}

export interface ResetPasswordResponse {
  message: string
  signed_out_all: boolean
}

export interface SessionInfo {
  active_sessions: number
}
