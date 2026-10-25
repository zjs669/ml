/** 与后端 `/api/v1` 契约一一对应的类型定义。 */

export type Position = 'year' | 'month' | 'day' | 'hour'
export type Depth = 'brief' | 'detailed'

export interface HiddenStem {
  stem: string
  level: string
  weight: number
  element: string
  ten_god: string
}

export interface PillarFact {
  stem: string
  branch: string
  text: string
  stem_element: string
  stem_polarity: string
  branch_element: string
  ten_god: string
  uncertain?: boolean
  hidden_stems: HiddenStem[]
  /** 纳音（如「屋上土」） */
  nayin?: string
  /** 本柱旬空二支 */
  xun_kong?: string[]
  /** 地势：日干对本支的十二长生位 */
  dishi?: string
  /** 自坐：本柱干对本支的十二长生位 */
  zizuo?: string
}

/** 神煞命中项：只报位置，不评价吉凶 */
export interface ShenshaItem {
  name: string
  positions: Position[]
  basis: string
  source_ref: string
  variant?: boolean
}

export interface ShenshaFacts {
  items: ShenshaItem[]
  by_pillar: Record<Position, string[]>
  variant: string
}

export interface TermInfo {
  name: string
  instant_utc: string
  local: string
  timezone: string
  source: string
}

export interface DayunItem {
  index: number
  pillar: string
  start_age_years: number
  end_age_years: number
  start_year: number
}

export interface DayunFacts {
  computed: boolean
  reason?: string
  forward?: boolean
  rule?: string
  start_offset_days?: number
  start_age?: { years: number; months: number; days: number; text: string }
  start_datetime_estimate?: string
  error_bound?: string
  list?: DayunItem[]
}

export interface TriggeredRule {
  rule_id: string
  relation: string
  topic: string
  label: string
  note: string
  positions: Position[]
  priority: number
  source_ref: string
  version: string
  system: string
  scope: string
  members: string[]
  duplicated_branches?: Record<string, Position[]>
}

export interface IncompleteRelation {
  rule_id: string
  relation: string
  members_present: string[]
  positions: Position[]
  note: string
  source_ref: string
}

export interface ConflictItem {
  type: string
  positions: Position[]
  relations: string[]
  rule_ids: string[]
  note: string
}

export interface RelationsAnalysis {
  rules: TriggeredRule[]
  incomplete: IncompleteRelation[]
  conflicts: ConflictItem[]
  summary: Record<string, number>
  count: number
}

/** 一柱流年：干支 + 十神 + 虚岁 + 所属大运 + 立春交节 */
export interface LiunianItem {
  year: number
  pillar: string
  stem: string
  branch: string
  stem_element: string
  branch_element: string
  ten_god: string
  virtual_age: number
  lichun_local: string
  dayun_pillar: string | null
  dayun_index: number | null
}

export interface LiunianFacts {
  start_year: number
  years: number
  /** 年界口径：lichun / lichun_day，与年柱保持一致 */
  boundary_rule?: string
  rule: string
  list: LiunianItem[]
}

export interface ChartFacts {
  pillars: Record<Position, PillarFact>
  order: Position[]
  day_master: { stem: string; element: string; polarity: string }
  ten_gods: Record<string, string>
  five_elements_count: {
    raw: Record<string, number>
    weighted: Record<string, number>
    missing: string[]
    weight_rule: string
  }
  jieqi: {
    prev: TermInfo
    next: TermInfo
    minutes_to_prev: number
    minutes_to_next: number
  }
  dayun: DayunFacts
  /** 流年窗口：只有入参给了 liunian_start_year 才存在 */
  liunian?: LiunianFacts
  /** 神煞：与关系规则分开，不参与 rule_id 校验 */
  shensha?: ShenshaFacts
  solar_time_adjust: {
    applied: boolean
    delta_minutes: number
    longitude?: number
    method: string
  }
  hour_confidence: string
  timezone: string
  relations?: RelationsAnalysis
}

export interface Convention {
  year_boundary: string
  day_boundary: string
  solar_time: string
  school: string
  five_element_weight: string
  shensha_variant?: string
  day_boundary_note?: string
}

export interface SourceRef {
  type: string
  id: string
  note: string
}

export interface ChartResult {
  domain: string
  algorithm_version: string
  input_summary: Record<string, unknown>
  convention: Convention
  chart_facts: ChartFacts
  triggered_rules: TriggeredRule[]
  warnings: string[]
  source_refs: SourceRef[]
}

export interface ChartOut extends ChartResult {
  id: number
  title: string | null
  created_at: string
  updated_at: string
}

export interface ChartListItem {
  id: number
  title: string | null
  domain: string
  created_at: string
  algorithm_version: string
  day_master: string | null
  pillars_text: string | null
}

export interface ChartPage {
  items: ChartListItem[]
  total: number
  page: number
  size: number
}

export interface Observation {
  fact: string
  rule_ids: string[]
  citation_ids: number[]
}

export interface Interpretation {
  claim: string
  citation_ids: number[]
  school_note?: string | null
}

export interface ReportPayload {
  summary: string
  observations: Observation[]
  traditional_interpretations: Interpretation[]
  practical_reflections: string[]
  uncertainties: string[]
  citations: number[]
  safety_note: string
}

export interface Citation {
  chunk_id: number
  title: string
  citation_label: string
  location: string | null
  license_status: string
  snippet: string
}

export interface ReportOut {
  id: number
  chart_id: number | null
  domain: string
  depth: Depth
  status: 'complete' | 'degraded' | string
  model_provider: string
  model_name: string
  skill_version: string
  prompt_version: string
  algorithm_version: string
  chart_snapshot_hash: string
  report: ReportPayload
  citations: Citation[]
  validation: { ok?: boolean; fatal_codes?: string[]; issues?: unknown[]; replayed?: boolean } | null
  created_at: string
}

export interface ReportListItem {
  id: number
  chart_id: number | null
  depth: Depth
  status: string
  created_at: string
  summary: string | null
}

/** 一轮追问的答案：比报告窄，但仍带引用与免责声明 */
export interface FollowupAnswer {
  answer: string
  points: string[]
  citations: number[]
  uncertainties: string[]
  safety_note: string
}

export interface FollowupOut {
  id: number
  report_id: number
  seq: number
  question: string
  answer: FollowupAnswer
  citations: Citation[]
  status: 'complete' | 'degraded' | string
  model_provider: string
  model_name: string
  validation: { ok?: boolean; fatal_codes?: string[] } | null
  created_at: string
}

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

export interface SharePreview {
  title: string | null
  domain: string
  pillars_text: string
  chart_facts: ChartFacts
  triggered_rules: TriggeredRule[]
  warnings: string[]
  algorithm_version: string
  convention: Convention
  expires_at: string
}

export interface BaziFormInput {
  birth_datetime: string
  timezone: string
  longitude: number | null
  time_known: boolean
  gender: 'male' | 'female' | 'unknown'
  convention: Partial<Convention>
  /** 可选：流年窗口起始年；不传则不计算流年 */
  liunian_start_year?: number | null
  /** 流年条数，默认 10 */
  liunian_years?: number
}

/* ---- 四柱反查（干支 → 公历日期）---- */

export interface PillarQuery {
  year?: string | null
  month?: string | null
  day?: string | null
  hour?: string | null
}

export interface ReverseSearchIn {
  pillars: PillarQuery
  range_start: string
  range_end: string
  timezone: string
  longitude?: number | null
  convention: Partial<Convention>
  limit?: number
  offset?: number
}

export interface ReverseCandidate {
  date: string
  hour_windows: string[]
  pillars: Record<string, string>
  confidence: 'exact' | 'partial'
  notes: string[]
}

export interface ReverseSearchOut {
  query: Record<string, string | null>
  convention: Record<string, unknown>
  searched_days: number
  total_matches: number
  truncated: boolean
  offset: number
  limit: number
  candidates: ReverseCandidate[]
  diagnosis: string[]
  warnings: string[]
  algorithm_version: string
}

/* ---- 紫微斗数（domain=ziwei 的 chart_facts 形状）---- */

export interface ZiweiLunarDate {
  year: number
  month: number
  day: number
  is_leap_month: boolean
  month_name: string
  day_name: string
  text: string
}

export interface ZiweiTransformationInPalace {
  type: string
  star: string
}

export interface ZiweiPalace {
  order: number
  name: string
  branch: string
  heavenly_stem: string
  is_body: boolean
  main_stars: string[]
  aux_stars: string[]
  /** 杂曜：天刑、红鸾、华盖等，只作事实陈列。旧盘（扩充前保存）没有该字段 */
  minor_stars?: string[]
  stars: string[]
  /** 长生十二神之一（旧盘没有） */
  life_cycle?: string | null
  /** 博士十二神之一（旧盘没有） */
  bo_shi?: string | null
  /** 将前十二神 */
  jiang_qian?: string
  /** 岁前十二神 */
  sui_qian?: string
  /** 自化：本宫宫干四化仍落本宫的类型 */
  self_hua?: string[]
  /** 小限岁数（每 12 年一个） */
  xiaoxian_ages?: number[]
  /** 流年虚岁 */
  liunian_ages?: number[]
  /** 三方四正四宫名 */
  sanfang?: string[]
  transformations: ZiweiTransformationInPalace[]
  dayun: { start_age: number; end_age: number }
}

export interface ZiweiTransformation {
  type: string
  star: string
  palace: string
  branch: string
}

export interface ZiweiDayunItem {
  index: number
  palace: string
  branch: string
  start_age: number
  end_age: number
}

export interface ZiweiFacts {
  lunar_date: ZiweiLunarDate
  solar_date: string
  year_ganzhi: string
  year_zodiac: string
  hour_branch: string
  hour_known: boolean
  five_element_bureau: {
    element: string
    number: number
    name: string
    life_palace_nayin: string
  }
  life_palace: { branch: string; heavenly_stem: string; text: string; palace: string }
  body_palace: { branch: string; palace: string }
  ziwei_star: { branch: string; palace: string }
  si_hua: Record<string, string>
  palaces: ZiweiPalace[]
  transformations: ZiweiTransformation[]
  /** 宫干四化：12 宫 × 4 化 = 48 条，飞星层（旧盘没有） */
  palace_transformations?: ZiweiPalaceTransformation[]
  /** 仅入参给了 review_age 时存在 */
  dayun_transformation?: ZiweiPeriodTransformation
  /** 仅入参给了 review_year 时存在 */
  liunian_transformation?: ZiweiPeriodTransformation
  dayun: ZiweiDayunItem[]
  dayun_forward: boolean
  /** 流年表：年份 / 虚岁 / 干支 / 流年命宫 */
  liunian_table?: ZiweiLiunianRow[]
  /** 飞星串联：只列链路，不推事件 */
  flying?: ZiweiFlying
  timezone: string
}

export interface ZiweiLiunianRow {
  year: number
  virtual_age: number
  pillar: string
  palace: string
}

export interface ZiweiFlyingHop {
  palace: string
  type: string
  star: string
  to_palace: string
}

export interface ZiweiFlyingChain {
  start_palace: string
  start_stem: string
  hops: ZiweiFlyingHop[]
  cycle: boolean
}

export interface ZiweiFlying {
  depth: number
  starts: string[]
  chains: ZiweiFlyingChain[]
  truncated: boolean
  rule: string
}

/** 飞星四化：某个宫的宫干把哪颗星化成了什么，落在哪个宫 */
export interface ZiweiPalaceTransformation {
  from_palace: string
  stem: string
  type: string
  star: string
  to_palace: string
  to_branch: string
}

/** 大限 / 流年四化：只描述这一层用哪个宫干推出来的四化 */
export interface ZiweiPeriodTransformation {
  stem: string
  branch?: string
  palace: string
  items: ZiweiTransformation[]
  age?: number
  year?: number
  ganzhi?: string
}

/** 紫微口径：字段与四柱完全不相交，因此单独声明，不复用 `Convention`。 */
export interface ZiweiConvention {
  calendar_basis?: string
  year_boundary?: string
  school?: string
  leap_month?: string
  zi_hour?: string
  school_note?: string
}

export interface ZiweiChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: ZiweiFacts
  convention: ZiweiConvention
}

export interface ZiweiFormInput {
  calendar: 'gregorian' | 'lunar'
  birth_datetime: string
  is_leap_month: boolean
  timezone: string
  time_known: boolean
  gender: 'male' | 'female' | 'unknown'
  /** 可选：虚岁，给了才算大限四化 */
  review_age?: number | null
  /** 可选：农历年，给了才算流年四化 */
  review_year?: number | null
  /** 飞星串联深度，默认 2 */
  flying_depth?: 1 | 2 | 3
}

export interface ApiErrorBody {
  error: { code: string; message: string; request_id?: string | null; details?: unknown }
}

/** 六爻单爻：本卦纳甲六亲六神 + 若为动爻则附变爻信息 */
export interface LiuyaoLine {
  position: number
  polarity: string
  najia: string
  stem: string
  branch: string
  element: string
  six_relation: string
  liu_shen: string
  shi: boolean
  ying: boolean
  value?: number
  moving?: boolean
  changed?: { polarity: string; najia: string; element: string; six_relation: string }
}

/** 一卦（本卦或变卦）：卦宫、世应与六爻 */
export interface LiuyaoHexagram {
  name: string
  upper: string
  lower: string
  bits: string
  palace: string
  palace_element: string
  phase: string
  shi: number
  ying: number
  is_pure: boolean
  lines: LiuyaoLine[]
}

export interface LiuyaoFacts {
  method: 'coins' | 'time' | 'manual' | string
  method_label: string
  cast_at: string
  timezone: string
  lunar_date: { year: number; month: number; day: number; is_leap_month: boolean; text: string; year_ganzhi: string }
  hour_branch: string
  day_pillar: { text: string; stem: string; branch: string }
  month_build: { branch: string; jie: string; text: string; source: string }
  xun_kong: string[]
  liu_shen_order: string[]
  seed: number | null
  time_numbers: {
    upper_number: number
    lower_number: number
    moving_position: number
    year_number: number
    month_number: number
    day_number: number
    hour_number: number
  } | null
  question: string | null
  question_stored: boolean
  values: number[]
  moving_lines: number[]
  original: LiuyaoHexagram
  changed: LiuyaoHexagram | null
  mutual: { name: string; upper: string; lower: string; palace: string }
}

/** 六爻口径：字段与四柱、紫微均不相交，因此单独声明 */
export interface LiuyaoConvention {
  school?: string
  day_boundary?: string
  month_basis?: string
  school_note?: string
}

export interface LiuyaoChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: LiuyaoFacts
  convention: LiuyaoConvention
}

export interface LiuyaoFormInput {
  method: 'coins' | 'time' | 'manual'
  cast_datetime: string
  timezone: string
  seed?: number | null
  lines?: number[] | null
  question?: string | null
  store_question: boolean
}

/* ---- 奇门遁甲（domain=qimen 的 chart_facts 形状）---- */

/** 一宫：地盘干、天盘干、星、门、神；中五宫无门无神 */
export interface QimenPalace {
  number: number
  name: string
  trigram: string
  direction: string
  element: string
  earth_stem: string
  sky_stem: string | null
  extra_sky_stem: string | null
  star: string
  extra_star: string | null
  door: string | null
  deity: string | null
  is_center: boolean
  is_zhifu: boolean
  is_zhishi: boolean
  note?: string
}

export interface QimenFacts {
  cast_at: string
  timezone: string
  pillars: Record<'year' | 'month' | 'day' | 'hour', { stem: string; branch: string; text: string }>
  term: TermInfo
  dun: { type: string; is_yang: boolean; yuan: string; ju: number; text: string }
  fu_tou: { pillar: string; branch: string; yuan: string; date: string }
  xun_kong: { xun_head: string; instrument: string; branches: string[] }
  zhifu: {
    star: string
    instrument: string
    palace: number
    palace_name: string
    landing_palace: number
    landing_name: string
  }
  zhishi: { door: string; palace: number; palace_name: string; steps: number }
  hour_stem_palace: { stem: string; palace: number; palace_name: string }
  ma_star: { branch: string; palace: number; palace_name: string }
  fuyin: { star: boolean; door: boolean }
  palaces: QimenPalace[]
  three_marvels: { stem: string; palace: number; palace_name: string }[]
}

/** 奇门口径：只有一个学派，字段与四柱/紫微/六爻均不相交 */
export interface QimenConvention {
  school?: string
  dun_basis?: string
  yuan_method?: string
  center_palace?: string
  day_boundary?: string
  school_note?: string
}

export interface QimenChartResult extends Omit<ChartResult, 'chart_facts' | 'convention'> {
  chart_facts: QimenFacts
  convention: QimenConvention
}

export interface QimenFormInput {
  cast_datetime: string
  timezone: string
  convention: Partial<QimenConvention>
}
