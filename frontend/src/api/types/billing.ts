/** 套餐、订单、支付通道与用量。 */

export interface PlanInfo {
  code: string
  name: string
  amount_minor: number
  amount_text: string
  credits: number
  duration_days: number
  tagline: string
  features: string[]
  purchasable: boolean
  plan_version: string
}

export interface PlansResponse {
  plan_version: string
  currency: string
  plans: PlanInfo[]
  refund_policy: string
  billing_note: string
}

/** 支付通道：`available=false` 的通道在页面上置灰并写明未接入原因 */

export interface PaymentMethod {
  code: string
  label: string
  available: boolean
  note: string
}

export interface BillingConfig {
  mode: 'mock' | 'live'
  currency: string
  plan_version: string
  methods: PaymentMethod[]
  default_method: string | null
  callback_signature: string
  secret_rotated: boolean
  refund_window_days: number
  notice: string
}

export interface UsageSnapshot {
  daily_free_limit: number
  daily_free_used: number
  daily_free_remaining: number
  paid_balance: number
  daily_free_reset_at: string
  can_generate: boolean
  server_time_utc: string
}

export interface OrderSummary {
  order_no: string
  plan_code: string
  plan_name: string
  amount_minor: number
  amount_text: string
  currency: string
  status: string
  provider: string | null
  created_at: string
  paid_at: string | null
}

export interface MockCallback {
  url: string
  header: string
  body_raw: string
  signature: string
  warning: string
}

export interface OrderCreated {
  order: OrderSummary
  mock_callback?: MockCallback
}
