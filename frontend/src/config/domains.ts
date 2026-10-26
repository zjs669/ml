/**
 * 全站术数入口的唯一事实来源。
 *
 * 为什么集中到一处：原先同一份清单在三个地方各维护一份 ——
 * `ToolsPage` 里 19 个对象、`HomePage` 里 5 个对象、`router` 里 19 条记录。
 * 新增一个域要改三处，漏改就会出现「工具页有、导航没有」这种半上线状态
 * （本轮反馈的「新增功能上方没用」就是这么来的）。
 *
 * 现在：新增域 = 后端 `registry.py` 登记 + 本文件加一条。导航、首页、工具页、
 * 路由表全部由本文件派生，不再各写一份。
 *
 * 注意：`domain` 字段对确定性域必须与后端 `GET /api/v1/meta/domains` 一致；
 * `reverse` / `face` / `palm` 是页面级能力（反查是 bazi 的反向运算，
 * 视觉域不在 registry 里），用页面级 key，前端不把它们当成排盘域。
 */

export type DomainGroup = '命理排盘' | '起局占断' | '西式与问卷' | '视觉分析'

export interface DomainEntry {
  /** 路由与内部标识 */
  key: string
  /** 后端 registry 里的 domain；页面级能力为 null */
  domain: string | null
  path: string
  label: string
  /** 单字徽标，比图标库轻，也更符合术数主题 */
  mark: string
  group: DomainGroup
  desc: string
  note: string
  requiresAuth?: boolean
}

export const DOMAIN_GROUPS: DomainGroup[] = ['命理排盘', '起局占断', '西式与问卷', '视觉分析']

export const DOMAIN_ENTRIES: DomainEntry[] = [
  // ---- 命理排盘 ----
  {
    key: 'bazi',
    domain: 'bazi',
    path: '/bazi',
    label: '四柱八字',
    mark: '柱',
    group: '命理排盘',
    desc: '公历输入 → 四柱、藏干、十神、五行加权、大运、节气交节，配合关系规则与带引用的 AI 解读。',
    note: '确定性引擎 + 规则引擎 + 报告校验链全部可用',
  },
  {
    key: 'reverse',
    domain: null,
    path: '/reverse',
    label: '四柱反查',
    mark: '逆',
    group: '命理排盘',
    desc: '已知干支反推公历日期：四柱 / 日柱任填，按时辰窗口与换日口径精确回推。',
    note: '与正排严格互逆，500 例往返一致；免登录可用',
  },
  {
    key: 'ziwei',
    domain: 'ziwei',
    path: '/ziwei',
    label: '紫微斗数',
    mark: '紫',
    group: '命理排盘',
    desc: '农历年月日时 → 十二宫、五行局、十四主星、辅星、生年四化与大限。',
    note: '三合派单一口径，安星法逐步断言 + 10 例手推基准',
  },
  {
    key: 'ziwei-horoscope',
    domain: 'ziwei_horoscope',
    path: '/ziwei-horoscope',
    label: '紫微运限',
    mark: '限',
    group: '命理排盘',
    desc: '在本命盘上叠六层时间：大限、小限、流年、流月、流日、流时，逐层给出落宫与星曜。',
    note: '斗君法起流月，逐层落宫可独立复算',
  },
  {
    key: 'ziwei-flying',
    domain: 'ziwei_flying',
    path: '/ziwei-flying',
    label: '紫微飞星',
    mark: '飞',
    group: '命理排盘',
    desc: '定向查询宫干四化：某宫飞向哪些宫、哪些宫飞入某宫、两宫之间是否有飞化连接。',
    note: '复用本命盘的 48 条宫干四化，不另立四化表',
  },
  {
    key: 'hepan',
    domain: 'hepan',
    path: '/hepan',
    label: '关系合盘',
    mark: '合',
    group: '命理排盘',
    desc: '两张四柱盘拼到一起，复用单盘 66 条关系规则判定跨盘与盘内交互。',
    note: '只列触发的规则，不判断关系好坏',
  },

  // ---- 起局占断 ----
  {
    key: 'liuyao',
    domain: 'liuyao',
    path: '/liuyao',
    label: '六爻',
    mark: '爻',
    group: '起局占断',
    desc: '铜钱 / 时间 / 手动三种起卦 → 本卦、动爻、变卦、互卦，附纳甲、六亲、六神、世应与旬空。',
    note: '京房纳甲单一口径，14 例手推基准 + 八宫变爻法独立校验',
  },
  {
    key: 'qimen',
    domain: 'qimen',
    path: '/qimen',
    label: '奇门遁甲',
    mark: '门',
    group: '起局占断',
    desc: '起局时刻 → 阴阳遁与局数、地盘三奇六仪、天盘九星、八门、八神，附旬空、马星与伏吟判断。',
    note: '时家转盘拆补法单一口径，12 例手推基准 + 三盘环序独立重算',
  },
  {
    key: 'daliuren',
    domain: 'daliuren',
    path: '/daliuren',
    label: '大六壬',
    mark: '六',
    group: '起局占断',
    desc: '月将加时定天地盘、十二天将、四课与三传，附天马、建除与长生。',
    note: '主干已上线：昴星、别责、八专三类课体未实现，遇到会明确标注',
  },
  {
    key: 'meihua',
    domain: 'meihua',
    path: '/meihua',
    label: '梅花易数',
    mark: '梅',
    group: '起局占断',
    desc: '六种起卦法（时间/报数/字占/丈尺/方位/指定），出本卦、互卦、变卦、错卦、综卦与体用五行。',
    note: '复用六爻的六十四卦表，体用只列生克方向',
  },
  {
    key: 'xiaoliuren',
    domain: 'xiaoliuren',
    path: '/xiaoliuren',
    label: '小六壬',
    mark: '壬',
    group: '起局占断',
    desc: '月上起大安、日上顺数、时上顺数，三宫递推到断事落点，支持公历与手工农历。',
    note: '六宫递推单一口径，闰月按本月重数（可切顺延）',
  },
  {
    key: 'taiyi',
    domain: 'taiyi',
    path: '/taiyi',
    label: '太乙九星',
    mark: '太',
    group: '起局占断',
    desc: '年/月/日/时四层九星观测：编号、太乙名、五行、方位与传统吉凶分类。',
    note: '只做九星观测：七十二局与主客算未实现',
  },
  {
    key: 'almanac',
    domain: 'almanac',
    path: '/almanac',
    label: '黄历',
    mark: '历',
    group: '起局占断',
    desc: '通书日级条目：宜、忌、值星、星宿、神煞、方位与十二时辰吉凶，含二十八星宿与九星。',
    note: '条目原样呈现，不做择日推荐；黄历按自然日换日',
  },

  // ---- 西式与问卷 ----
  {
    key: 'tarot',
    domain: 'tarot',
    path: '/tarot',
    label: '塔罗',
    mark: '塔',
    group: '西式与问卷',
    desc: '78 张牌无放回抽取，9 种牌阵，正逆位与牌序使用独立随机源，seed 可复现。',
    note: '牌面关键词自编，牌面图片不随仓库分发',
  },
  {
    key: 'astrology',
    domain: 'astrology',
    path: '/astrology',
    label: '西洋占星',
    mark: '星',
    group: '西式与问卷',
    desc: '太阳与月亮视黄经、上升点、天顶、整宫制十二宫与主要相位。',
    note: '简化版：十行星与 Placidus 等宫制未实现，接口会显式列出缺项',
  },
  {
    key: 'mbti',
    domain: 'mbti',
    path: '/mbti',
    label: '性格问卷',
    mark: '问',
    group: '西式与问卷',
    desc: '自编 40 题四维倾向问卷，四维独立计票，平票记为未分化（X）。',
    note: '非官方 MBTI 量表，精简版仅供参考',
  },
  {
    key: 'dream',
    domain: 'dream',
    path: '/dream',
    label: '解梦',
    mark: '梦',
    group: '西式与问卷',
    desc: '从梦境描述里抽取意象关键词，按类别列出民间通行说法。',
    note: '不做解释、不做预示、不做心理诊断',
  },

  // ---- 视觉分析 ----
  {
    key: 'face',
    domain: null,
    path: '/face',
    label: '面相观察',
    mark: '面',
    group: '视觉分析',
    desc: '上传面部照片，按天庭、眼、鼻、口、颧颊等分区做形态描述性整理。',
    note: '视觉模型逐次计费，图片剥 EXIF 后按留存策略删除',
    requiresAuth: true,
  },
  {
    key: 'palm',
    domain: null,
    path: '/palm',
    label: '手相观察',
    mark: '掌',
    group: '视觉分析',
    desc: '上传手掌照片，按掌型、三大主线、掌丘做形态描述性整理。',
    note: '视觉模型逐次计费，图片剥 EXIF 后按留存策略删除',
    requiresAuth: true,
  },
]

/** 按分组返回，顺序与 `DOMAIN_GROUPS` 一致；组内保持声明顺序。 */
export function entriesByGroup(): Array<{ group: DomainGroup; items: DomainEntry[] }> {
  return DOMAIN_GROUPS.map((group) => ({
    group,
    items: DOMAIN_ENTRIES.filter((item) => item.group === group),
  }))
}

export function findEntry(path: string): DomainEntry | undefined {
  return DOMAIN_ENTRIES.find((item) => item.path === path)
}

/** 导航高亮：子路径（如 `/charts/12`）不算命中，避免误亮。 */
export function isActive(currentPath: string, entryPath: string): boolean {
  return currentPath === entryPath
}
