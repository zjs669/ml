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
