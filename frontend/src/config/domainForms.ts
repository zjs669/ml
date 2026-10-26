/**
 * 术数表单配置表。
 *
 * 为什么用声明式配置而不是每个域写一个页面：
 * 新增的 8 个确定性域里，表单结构高度同构（时间 / 日期 / 选择 / 文本 + 口径面板），
 * 各写一个页面会得到 8 份 90% 相同的代码。这里把「字段」抽成配置，
 * 由 `GenericChartPage.vue` 统一渲染，差异只落在字段定义上。
 *
 * 注意：`bazi` / `ziwei` / `liuyao` / `qimen` 四个既有页面**不改动** ——
 * 它们的表单有各自的特殊交互（反查、手填六爻、流派面板），
 * 强行统一会把简单页面变复杂，也会破坏已验收的前端契约。
 */

export type FieldKind = 'datetime' | 'date' | 'time' | 'number' | 'text' | 'textarea' | 'select' | 'switch'

export interface FieldDef {
  key: string
  label: string
  kind: FieldKind
  required?: boolean
  placeholder?: string
  /** select 的选项 */
  options?: Array<{ value: string | number; label: string }>
  default?: unknown
  min?: number
  max?: number
  hint?: string
  /** 只在满足条件时显示（用于「农历模式才显示闰月」这类联动） */
  visibleWhen?: { key: string; equals: unknown }
}

export interface DomainFormConfig {
  domain: string
  title: string
  intro: string
  fields: FieldDef[]
  /** 提交前把表单值转成后端入参（处理嵌套与条件字段） */
  build: (values: Record<string, unknown>) => Record<string, unknown>
  /** 保存时的默认标题 */
  defaultTitle: string
}

const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Tokyo',
  'Europe/London',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
].map((value) => ({ value, label: value }))

const TIMEZONE_FIELD: FieldDef = {
  key: 'timezone',
  label: '时区',
  kind: 'select',
  required: true,
  options: TIMEZONES,
  default: 'Asia/Shanghai',
  hint: '所有时间都按这里的钟表时间理解，不做隐式换算。',
}

const QUESTION_FIELD: FieldDef = {
  key: 'question',
  label: '占问（可选）',
  kind: 'textarea',
  placeholder: '不填则只出盘面结构',
  hint: '原文会随命盘保存；可在下方关闭保存。',
  default: '',
}

export const DOMAIN_FORMS: Record<string, DomainFormConfig> = {
  almanac: {
    domain: 'almanac',
    title: '黄历',
    intro: '通书日级条目：宜、忌、值星、星宿、神煞、方位与十二时辰。只列条目，不作吉凶结论。',
    defaultTitle: '黄历',
    fields: [
      { key: 'date', label: '日期', kind: 'date', required: true },
      TIMEZONE_FIELD,
      {
        key: 'birth_date',
        label: '出生日期（可选）',
        kind: 'date',
        hint: '只作对照标注，不改变任何宜忌条目。',
      },
    ],
    build: (values) => ({
      date: values.date,
      timezone: values.timezone,
      birth_date: values.birth_date || null,
    }),
  },

  xiaoliuren: {
    domain: 'xiaoliuren',
    title: '小六壬',
    intro: '月上起大安、日上顺数、时上顺数，三宫递推到断事落点。只出宫位与宫性。',
    defaultTitle: '小六壬',
    fields: [
      {
        key: 'input_mode',
        label: '输入方式',
        kind: 'select',
        required: true,
        options: [
          { value: 'gregorian', label: '公历日期（自动转农历）' },
          { value: 'lunar', label: '手工农历月日' },
        ],
        default: 'gregorian',
      },
      {
        key: 'date',
        label: '起课日期',
        kind: 'datetime',
        required: true,
        visibleWhen: { key: 'input_mode', equals: 'gregorian' },
      },
      {
        key: 'lunar_month',
        label: '农历月',
        kind: 'number',
        min: 1,
        max: 12,
        visibleWhen: { key: 'input_mode', equals: 'lunar' },
      },
      {
        key: 'lunar_day',
        label: '农历日',
        kind: 'number',
        min: 1,
        max: 30,
        visibleWhen: { key: 'input_mode', equals: 'lunar' },
      },
      {
        key: 'is_leap_month',
        label: '是否闰月',
        kind: 'switch',
        default: false,
        visibleWhen: { key: 'input_mode', equals: 'lunar' },
      },
      {
        key: 'hour',
        label: '时辰（0–23 小时）',
        kind: 'number',
        required: true,
        min: 0,
        max: 23,
        default: 12,
        hint: '23:00 起算子时。',
      },
      TIMEZONE_FIELD,
      QUESTION_FIELD,
    ],
    build: (values) => ({
      input_mode: values.input_mode,
      date: values.input_mode === 'gregorian' ? values.date : null,
      lunar_month: values.input_mode === 'lunar' ? Number(values.lunar_month) : null,
      lunar_day: values.input_mode === 'lunar' ? Number(values.lunar_day) : null,
      is_leap_month: values.input_mode === 'lunar' ? Boolean(values.is_leap_month) : false,
      hour: Number(values.hour),
      timezone: values.timezone,
      question: values.question || null,
      store_question: true,
    }),
  },

  tarot: {
    domain: 'tarot',
    title: '塔罗',
    intro: '78 张牌无放回抽取，牌序与正逆位使用独立随机源。只出牌面与位置，不做预测。',
    defaultTitle: '塔罗',
    fields: [
      {
        key: 'spread',
        label: '牌阵',
        kind: 'select',
        required: true,
        options: [
          { value: 'single', label: '单牌' },
          { value: 'three', label: '三牌阵（过去/现在/未来）' },
          { value: 'love', label: '爱情牌阵' },
          { value: 'celtic', label: '凯尔特十字（10 张）' },
          { value: 'horseshoe', label: '马蹄牌阵（7 张）' },
          { value: 'choice', label: '抉择牌阵' },
          { value: 'body_mind_spirit', label: '身心灵' },
          { value: 'situation', label: '情境牌阵' },
          { value: 'yes_no', label: '是与否' },
        ],
        default: 'three',
      },
      {
        key: 'deck',
        label: '牌池',
        kind: 'select',
        required: true,
        options: [
          { value: 'all', label: '全 78 张' },
          { value: 'major', label: '仅大阿卡纳 22 张' },
          { value: 'minor', label: '仅小阿卡纳 56 张' },
        ],
        default: 'all',
      },
      {
        key: 'allow_reversed',
        label: '允许逆位',
        kind: 'switch',
        default: true,
      },
      {
        key: 'reversed_probability',
        label: '逆位概率',
        kind: 'number',
        min: 0,
        max: 1,
        default: 0.35,
        hint: '0 表示全正位，1 表示全逆位。',
      },
      {
        key: 'seed',
        label: '复现种子（可选）',
        kind: 'text',
        placeholder: '留空则按当前时刻派生并回显',
        hint: '同一 seed 同一次抽牌，便于复现与对账。',
      },
      QUESTION_FIELD,
    ],
    build: (values) => ({
      spread: values.spread,
      deck: values.deck,
      allow_reversed: Boolean(values.allow_reversed),
      reversed_probability: Number(values.reversed_probability),
      seed: values.seed || null,
      question: values.question || null,
      store_question: true,
    }),
  },

  meihua: {
    domain: 'meihua',
    title: '梅花易数',
    intro: '起卦 → 本卦 → 互卦/变卦/错卦/综卦 → 体用。只出卦象结构与五行生克方向。',
    defaultTitle: '梅花易数',
    fields: [
      {
        key: 'method',
        label: '起卦法',
        kind: 'select',
        required: true,
        options: [
          { value: 'time', label: '时间起卦' },
          { value: 'numbers', label: '报数（两数 / 三数）' },
          { value: 'text', label: '字占' },
          { value: 'measure', label: '丈尺尺寸' },
          { value: 'direction', label: '方位' },
          { value: 'hexagram', label: '直接指定上下卦' },
        ],
        default: 'time',
      },
      {
        key: 'cast_datetime',
        label: '起卦时间',
        kind: 'datetime',
        required: true,
        visibleWhen: { key: 'method', equals: 'time' },
      },
      {
        key: 'numbers',
        label: '报数（逗号分隔，2 或 3 个）',
        kind: 'text',
        placeholder: '例如 7,13 或 7,13,5',
        visibleWhen: { key: 'method', equals: 'numbers' },
      },
      {
        key: 'text',
        label: '字占原文',
        kind: 'text',
        placeholder: '不超过 40 字',
        visibleWhen: { key: 'method', equals: 'text' },
      },
      {
        key: 'length_value',
        label: '长（寸）',
        kind: 'number',
        min: 1,
        visibleWhen: { key: 'method', equals: 'measure' },
      },
      {
        key: 'width_value',
        label: '宽（寸，可选）',
        kind: 'number',
        min: 1,
        visibleWhen: { key: 'method', equals: 'measure' },
      },
      {
        key: 'direction',
        label: '方位',
        kind: 'select',
        options: ['乾', '兑', '离', '震', '巽', '坎', '艮', '坤'].map((value) => ({ value, label: value })),
        visibleWhen: { key: 'method', equals: 'direction' },
      },
      {
        key: 'upper',
        label: '上卦',
        kind: 'select',
        options: ['乾', '兑', '离', '震', '巽', '坎', '艮', '坤'].map((value) => ({ value, label: value })),
        visibleWhen: { key: 'method', equals: 'hexagram' },
      },
      {
        key: 'lower',
        label: '下卦',
        kind: 'select',
        options: ['乾', '兑', '离', '震', '巽', '坎', '艮', '坤'].map((value) => ({ value, label: value })),
        visibleWhen: { key: 'method', equals: 'hexagram' },
      },
      {
        key: 'moving_line',
        label: '动爻（1–6）',
        kind: 'number',
        min: 1,
        max: 6,
        visibleWhen: { key: 'method', equals: 'hexagram' },
      },
      TIMEZONE_FIELD,
      QUESTION_FIELD,
    ],
    build: (values) => {
      const body: Record<string, unknown> = {
        method: values.method,
        timezone: values.timezone,
        question: values.question || null,
        store_question: true,
      }
      if (values.method === 'time') body.cast_datetime = values.cast_datetime
      if (values.method === 'numbers') {
        body.numbers = String(values.numbers || '')
          .split(/[,，\s]+/)
          .filter(Boolean)
          .map((item) => Number(item))
      }
      if (values.method === 'text') body.text = values.text
      if (values.method === 'measure') {
        body.length_value = Number(values.length_value)
        body.width_value = values.width_value ? Number(values.width_value) : null
      }
      if (values.method === 'direction') body.direction = values.direction
      if (values.method === 'hexagram') {
        body.upper = values.upper
        body.lower = values.lower
        body.moving_line = Number(values.moving_line)
      }
      return body
    },
  },

  taiyi: {
    domain: 'taiyi',
    title: '太乙九星',
    intro: '年/月/日/时四层九星观测。只列星位、五行与方位，不做七十二局推演。',
    defaultTitle: '太乙九星',
    fields: [
      { key: 'date', label: '日期', kind: 'date', required: true },
      {
        key: 'mode',
        label: '主层',
        kind: 'select',
        required: true,
        options: [
          { value: 'year', label: '年盘' },
          { value: 'month', label: '月盘' },
          { value: 'day', label: '日盘' },
          { value: 'hour', label: '时盘' },
        ],
        default: 'day',
      },
      {
        key: 'hour',
        label: '时辰（0–23）',
        kind: 'number',
        min: 0,
        max: 23,
        default: 12,
        hint: '主层选「时盘」时必填。',
      },
      TIMEZONE_FIELD,
      QUESTION_FIELD,
    ],
    build: (values) => ({
      date: values.date,
      mode: values.mode,
      hour: values.mode === 'hour' || values.hour !== '' ? Number(values.hour) : null,
      timezone: values.timezone,
      question: values.question || null,
      store_question: true,
    }),
  },

  daliuren: {
    domain: 'daliuren',
    title: '大六壬',
    intro: '月将加时定天地盘、四课、贼克法三传。复杂课体未实现时会明确标注。',
    defaultTitle: '大六壬',
    fields: [
      { key: 'cast_datetime', label: '起课时间', kind: 'datetime', required: true },
      TIMEZONE_FIELD,
      {
        key: 'month_general',
        label: '手工月将（可选）',
        kind: 'select',
        options: ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥'].map(
          (value) => ({ value, label: value }),
        ),
        hint: '留空则按中气定月将。',
      },
      QUESTION_FIELD,
    ],
    build: (values) => ({
      cast_datetime: values.cast_datetime,
      timezone: values.timezone,
      month_general: values.month_general || null,
      question: values.question || null,
      store_question: true,
    }),
  },

  astrology: {
    domain: 'astrology',
    title: '西洋占星',
    intro: '简化版：太阳/月亮黄经、上升点、天顶与整宫制宫位。十行星未实现。',
    defaultTitle: '西洋占星',
    fields: [
      { key: 'birth_datetime', label: '出生时间', kind: 'datetime', required: true },
      TIMEZONE_FIELD,
      {
        key: 'latitude',
        label: '纬度（北纬为正）',
        kind: 'number',
        required: true,
        min: -66,
        max: 66,
        default: 31.23,
        hint: '极圈内（|纬度| > 66°）上升点可能不存在，会直接拒绝。',
      },
      {
        key: 'longitude',
        label: '经度（东经为正）',
        kind: 'number',
        required: true,
        min: -180,
        max: 180,
        default: 121.47,
      },
      { key: 'time_known', label: '出生时刻已知', kind: 'switch', default: true },
    ],
    build: (values) => ({
      birth_datetime: values.birth_datetime,
      timezone: values.timezone,
      latitude: Number(values.latitude),
      longitude: Number(values.longitude),
      time_known: Boolean(values.time_known),
    }),
  },

  ziwei_horoscope: {
    domain: 'ziwei_horoscope',
    title: '紫微运限',
    intro: '在本命盘上叠六层时间：大限、小限、流年、流月、流日、流时。只给落宫与星曜。',
    defaultTitle: '紫微运限',
    fields: [
      { key: 'birth_datetime', label: '出生时间', kind: 'datetime', required: true },
      TIMEZONE_FIELD,
      {
        key: 'gender',
        label: '性别',
        kind: 'select',
        options: [
          { value: 'male', label: '男' },
          { value: 'female', label: '女' },
          { value: 'unknown', label: '未知（大限方向按阳年顺、阴年逆占位）' },
        ],
        default: 'unknown',
      },
      { key: 'target_date', label: '目标日期', kind: 'datetime', required: true },
      { key: 'target_hour', label: '目标时辰（0–23）', kind: 'number', min: 0, max: 23, default: 12 },
    ],
    build: (values) => ({
      birth_datetime: values.birth_datetime,
      timezone: values.timezone,
      gender: values.gender,
      target_date: values.target_date,
      target_hour: Number(values.target_hour),
    }),
  },

  ziwei_flying: {
    domain: 'ziwei_flying',
    title: '紫微飞星',
    intro: '定向查询：某宫的四化飞到哪、哪些宫飞入某宫、两宫之间是否有飞化连接。',
    defaultTitle: '紫微飞星',
    fields: [
      { key: 'birth_datetime', label: '出生时间', kind: 'datetime', required: true },
      TIMEZONE_FIELD,
      {
        key: 'gender',
        label: '性别',
        kind: 'select',
        options: [
          { value: 'male', label: '男' },
          { value: 'female', label: '女' },
          { value: 'unknown', label: '未知' },
        ],
        default: 'unknown',
      },
      {
        key: 'query_type',
        label: '查询类型',
        kind: 'select',
        required: true,
        options: [
          { value: 'flies_from', label: '某宫飞向哪些宫' },
          { value: 'flies_into', label: '哪些宫飞入某宫' },
          { value: 'flies_to', label: '两宫之间是否有飞化' },
        ],
        default: 'flies_from',
      },
      {
        key: 'from_palace',
        label: '起点宫',
        kind: 'select',
        options: ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'].map(
          (value) => ({ value, label: value }),
        ),
        visibleWhen: { key: 'query_type', equals: 'flies_from' },
      },
      {
        key: 'from_palace',
        label: '起点宫',
        kind: 'select',
        options: ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'].map(
          (value) => ({ value, label: value }),
        ),
        visibleWhen: { key: 'query_type', equals: 'flies_to' },
      },
      {
        key: 'to_palace',
        label: '终点宫',
        kind: 'select',
        options: ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'].map(
          (value) => ({ value, label: value }),
        ),
        visibleWhen: { key: 'query_type', equals: 'flies_into' },
      },
      {
        key: 'to_palace',
        label: '终点宫',
        kind: 'select',
        options: ['命宫', '兄弟', '夫妻', '子女', '财帛', '疾厄', '迁移', '交友', '官禄', '田宅', '福德', '父母'].map(
          (value) => ({ value, label: value }),
        ),
        visibleWhen: { key: 'query_type', equals: 'flies_to' },
      },
      {
        key: 'mutagens',
        label: '四化筛选（留空为全部）',
        kind: 'select',
        options: [
          { value: '', label: '全部四化' },
          { value: '禄', label: '只看禄' },
          { value: '权', label: '只看权' },
          { value: '科', label: '只看科' },
          { value: '忌', label: '只看忌' },
        ],
        default: '',
      },
    ],
    build: (values) => ({
      birth_datetime: values.birth_datetime,
      timezone: values.timezone,
      gender: values.gender,
      query_type: values.query_type,
      from_palace: values.query_type === 'flies_from' || values.query_type === 'flies_to' ? values.from_palace : null,
      to_palace: values.query_type === 'flies_into' || values.query_type === 'flies_to' ? values.to_palace : null,
      mutagens: values.mutagens ? [values.mutagens] : [],
    }),
  },

  dream: {
    domain: 'dream',
    title: '解梦',
    intro: '从梦境描述里抽取意象关键词，列出该意象的民间通行说法。不做解释、不做预示。',
    defaultTitle: '解梦',
    fields: [
      {
        key: 'text',
        label: '梦境描述',
        kind: 'textarea',
        required: true,
        placeholder: '尽量写具体的意象，例如「梦见一条蛇在水边游走」',
        hint: '2–2000 字。',
      },
      {
        key: 'max_keywords',
        label: '最多提取意象数',
        kind: 'number',
        min: 1,
        max: 20,
        default: 8,
      },
      { key: 'include_traditional', label: '显示传统说法', kind: 'switch', default: true },
      { key: 'store_text', label: '保存梦境原文', kind: 'switch', default: true },
    ],
    build: (values) => ({
      text: values.text,
      max_keywords: Number(values.max_keywords),
      include_traditional: Boolean(values.include_traditional),
      store_text: Boolean(values.store_text),
    }),
  },
}
