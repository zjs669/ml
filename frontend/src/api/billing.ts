import { http } from './client'
import type { BillingConfig, OrderCreated, PlansResponse } from './types'

export async function listPlans(): Promise<PlansResponse> {
  const { data } = await http.get<PlansResponse>('/billing/plans')
  return data
}

/** 支付配置：模式、可用通道、回调验签方式（不含任何密钥）。 */
export async function getConfig(): Promise<BillingConfig> {
  const { data } = await http.get<BillingConfig>('/billing/config')
  return data
}

export async function createOrder(planCode: string): Promise<OrderCreated> {
  const { data } = await http.post<OrderCreated>('/billing/orders', { plan_code: planCode })
  return data
}

/** Mock 回调：内测环境的"支付成功"，带 HMAC 签名，链路上与真实回调一致。 */
export async function runMockCallback(order: OrderCreated): Promise<{ status: string; credits_granted?: number }> {
  if (!order.mock_callback) {
    throw new Error('后端未返回 Mock 回调信息（生产环境不会返回）')
  }
  // 后端返回的是 "/api/v1/billing/webhooks/mock" 这类以站点根为基准的路径，
  // 而 http 实例已带 baseURL，直接透传会拼成 /api/v1/api/v1/...，这里先剥掉前缀。
  const path = order.mock_callback.url.replace(/^\/api\/v1/, '')
  const { data } = await http.post<{ status: string; credits_granted?: number }>(path, order.mock_callback.body_raw, {
    headers: {
      [order.mock_callback.header]: order.mock_callback.signature,
      'Content-Type': 'application/json',
    },
    transformRequest: [(value) => value],
  })
  return data
}
