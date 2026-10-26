<script setup lang="ts">
import { useRouter } from 'vue-router'

interface ToolCard {
  key: string
  name: string
  /** 卡片左上角的单字徽标，比图标库轻，也更符合术数主题 */
  mark: string
  desc: string
  status: 'online' | 'planned'
  note?: string
  route?: string
}

const router = useRouter()

const TOOLS: ToolCard[] = [
  {
    key: 'bazi',
    name: '四柱八字',
    mark: '柱',
    desc: '公历输入 → 四柱、藏干、十神、五行加权、大运、节气交节，配合关系规则与带引用的 AI 解读。',
    status: 'online',
    note: '已上线：确定性引擎 + 规则引擎 + 报告校验链全部可用',
    route: '/bazi',
  },
  {
    key: 'reverse',
    name: '四柱反查',
    mark: '逆',
    desc: '已知干支反推公历日期：四柱 / 日柱任填，按时辰窗口与换日口径精确回推。',
    status: 'online',
    note: '已上线：与正排严格互逆，500 例往返一致；免登录可用',
    route: '/reverse',
  },
  {
    key: 'ziwei',
    name: '紫微斗数',
    mark: '紫',
    desc: '农历年月日时 → 十二宫、五行局、十四主星、辅星、生年四化与大限。',
    status: 'online',
    note: '已上线：三合派单一口径，安星法逐步断言 + 10 例手推基准',
    route: '/ziwei',
  },
  {
    key: 'liuyao',
    name: '六爻',
    mark: '爻',
    desc: '铜钱 / 时间 / 手动三种起卦 → 本卦、动爻、变卦、互卦，附纳甲、六亲、六神、世应与旬空。',
    status: 'online',
    note: '已上线：京房纳甲单一口径，14 例手推基准 + 八宫变爻法独立校验',
    route: '/liuyao',
  },
  {
    key: 'qimen',
    name: '奇门遁甲',
    mark: '门',
    desc: '起局时刻 → 阴阳遁与局数、地盘三奇六仪、天盘九星、八门、八神，附旬空、马星与伏吟判断。',
    status: 'online',
    note: '已上线：时家转盘拆补法单一口径，12 例手推基准 + 三盘环序独立重算',
    route: '/qimen',
  },
  {
    key: 'almanac',
    name: '黄历',
    mark: '历',
    desc: '通书日级条目：宜、忌、值星、星宿、神煞、方位与十二时辰吉凶，含二十八星宿与九星。',
    status: 'online',
    note: '已上线：条目原样呈现，不做择日推荐；黄历按自然日换日',
    route: '/almanac',
  },
  {
    key: 'xiaoliuren',
    name: '小六壬',
    mark: '壬',
    desc: '月上起大安、日上顺数、时上顺数，三宫递推到断事落点，支持公历与手工农历。',
    status: 'online',
    note: '已上线：六宫递推单一口径，闰月按本月重数（可切顺延）',
    route: '/xiaoliuren',
  },
  {
    key: 'meihua',
    name: '梅花易数',
    mark: '梅',
    desc: '六种起卦法（时间/报数/字占/丈尺/方位/指定），出本卦、互卦、变卦、错卦、综卦与体用五行。',
    status: 'online',
    note: '已上线：复用六爻的六十四卦表，体用只列生克方向',
    route: '/meihua',
  },
  {
    key: 'daliuren',
    name: '大六壬',
    mark: '六',
    desc: '月将加时定天地盘、十二天将、四课与贼克法三传，附天马、建除与长生。',
    status: 'online',
    note: '已上线（主干）：涉害/遥克/昴星等复杂课体未实现，遇到会明确标注',
    route: '/daliuren',
  },
  {
    key: 'taiyi',
    name: '太乙九星',
    mark: '太',
    desc: '年/月/日/时四层九星观测：编号、太乙名、五行、方位与传统吉凶分类。',
    status: 'online',
    note: '已上线（九星观测）：七十二局与主客算未实现',
    route: '/taiyi',
  },
  {
    key: 'ziwei-horoscope',
    name: '紫微运限',
    mark: '限',
    desc: '在本命盘上叠六层时间：大限、小限、流年、流月、流日、流时，逐层给出落宫与星曜。',
    status: 'online',
    note: '已上线：斗君法起流月，逐层落宫可独立复算',
    route: '/ziwei-horoscope',
  },
  {
    key: 'ziwei-flying',
    name: '紫微飞星',
    mark: '飞',
    desc: '定向查询宫干四化：某宫飞向哪些宫、哪些宫飞入某宫、两宫之间是否有飞化连接。',
    status: 'online',
    note: '已上线：复用本命盘的 48 条宫干四化，不另立四化表',
    route: '/ziwei-flying',
  },
  {
    key: 'tarot',
    name: '塔罗',
    mark: '塔',
    desc: '78 张牌无放回抽取，9 种牌阵，正逆位与牌序使用独立随机源，seed 可复现。',
    status: 'online',
    note: '已上线：牌面关键词自编，牌面图片不随仓库分发',
    route: '/tarot',
  },
  {
    key: 'astrology',
    name: '西洋占星',
    mark: '星',
    desc: '太阳与月亮视黄经、上升点、天顶、整宫制十二宫与主要相位。',
    status: 'online',
    note: '简化版：十行星与 Placidus 等宫制未实现，接口会显式列出缺项',
    route: '/astrology',
  },
  {
    key: 'hepan',
    name: '关系合盘',
    mark: '合',
    desc: '两张四柱盘拼到一起，复用单盘 66 条关系规则判定跨盘与盘内交互。',
    status: 'online',
    note: '已上线：只列触发的规则，不判断关系好坏',
    route: '/hepan',
  },
  {
    key: 'mbti',
    name: '性格问卷',
    mark: '问',
    desc: '自编 40 题四维倾向问卷，四维独立计票，平票记为未分化（X）。',
    status: 'online',
    note: '已上线：非官方 MBTI 量表，精简版仅供参考',
    route: '/mbti',
  },
  {
    key: 'dream',
    name: '解梦',
    mark: '梦',
    desc: '从梦境描述里抽取意象关键词，按类别列出民间通行说法。',
    status: 'online',
    note: '已上线：不做解释、不做预示、不做心理诊断',
    route: '/dream',
  },
  {
    key: 'face',
    name: '面相观察',
    mark: '面',
    desc: '上传面部照片，按天庭、眼、鼻、口、颧颊等分区做形态描述性整理。',
    status: 'online',
    note: '需登录：视觉模型逐次计费，图片剥 EXIF 后按留存策略删除',
    route: '/face',
  },
  {
    key: 'palm',
    name: '手相观察',
    mark: '掌',
    desc: '上传手掌照片，按掌型、三大主线、掌丘做形态描述性整理。',
    status: 'online',
    note: '需登录：视觉模型逐次计费，图片剥 EXIF 后按留存策略删除',
    route: '/palm',
  },
]
</script>

<template>
  <div class="tools">
    <div class="page-head">
      <h2>工具</h2>
      <p>只展示已跑通验收的模块。标注「计划中」的模块不提供入口，也不接受预约式承诺。</p>
    </div>

    <div class="cards">
      <div v-for="tool in TOOLS" :key="tool.key" class="card" :class="tool.status">
        <div class="card-head">
          <span class="mark">{{ tool.mark }}</span>
          <span class="name">{{ tool.name }}</span>
          <el-tag v-if="tool.status === 'online'" size="small" type="success" effect="plain">已上线</el-tag>
          <el-tag v-else size="small" type="info" effect="plain">计划中</el-tag>
        </div>
        <p class="desc">{{ tool.desc }}</p>
        <p class="note">{{ tool.note }}</p>
        <div v-if="tool.route" class="card-foot">
          <el-button size="small" plain @click="router.push(tool.route!)">
            {{ tool.key === 'reverse' ? '进入反查' : tool.key === 'qimen' ? '进入排局' : '进入排盘' }}
            <span class="arrow">→</span>
          </el-button>
        </div>
        <div v-else class="card-foot muted">暂未开放</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tools {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head h2 {
  margin: 0 0 6px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.card {
  border: 1px solid var(--xs-border);
  border-radius: 14px;
  background: #fff;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.card:hover {
  box-shadow: var(--xs-shadow);
  transform: translateY(-1px);
}

.card.planned {
  background: var(--xs-surface-muted);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mark {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  background: #f6f1e6;
  color: var(--xs-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 16px;
}

.name {
  font-weight: 600;
  font-size: 15px;
  flex: 1;
}

.desc {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.note {
  margin: 0;
  font-size: 12px;
  line-height: 1.75;
  color: var(--xs-text-muted);
  padding-top: 8px;
  border-top: 1px dashed var(--xs-border);
}

.card-foot {
  margin-top: auto;
  padding-top: 10px;
}

.arrow {
  margin-left: 4px;
}

.card-foot.muted {
  font-size: 12px;
  color: #a0a0a0;
}

@media (max-width: 1100px) {
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
