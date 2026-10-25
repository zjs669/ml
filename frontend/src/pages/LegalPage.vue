<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

interface Section {
  heading: string
  paragraphs?: string[]
  list?: string[]
}

interface LegalDoc {
  title: string
  version: string
  updated: string
  intro: string
  sections: Section[]
}

const DOCS: Record<string, LegalDoc> = {
  privacy: {
    title: '隐私政策',
    version: 'V1 草案（2026-10-24.v1）',
    updated: '2026-10-24',
    intro:
      '本政策适用于玄枢国学研习台内测版本。我们按「最小必要」原则收集信息：只收集完成排盘与报告所必需的数据，并提供删除与导出通道。',
    sections: [
      {
        heading: '一、我们收集什么',
        list: [
          '账号信息：邮箱、密码哈希（使用 Argon2id，不保存明文）、昵称（可选）。',
          '排盘输入：出生时间、时区、经度（仅真太阳时口径时使用）、性别选项。',
          '生成内容：命盘快照、关系规则触发记录、AI 报告及其引用来源。',
          '你主动填写的内容：命盘标题、笔记、反馈评分与说明。',
          '技术日志：请求 ID、接口路径、状态码、耗时；不含请求正文与出生完整日期。',
        ],
      },
      {
        heading: '二、我们不收集什么',
        list: [
          '不要求实名、身份证、手机号、住址。',
          '不读取你的通讯录、相册、定位等设备权限数据。',
          '不使用第三方广告或行为追踪 SDK。',
          '不把你的笔记内容上传给模型。',
        ],
      },
      {
        heading: '三、数据如何使用',
        list: [
          '用于计算排盘事实、生成并校验报告、结算额度。',
          '用于排查故障与安全审计（仅使用脱敏后的技术日志）。',
          '不用于模型训练；你的输入与输出默认不进入任何训练集。',
        ],
      },
      {
        heading: '四、数据交给谁',
        list: [
          'AI 服务提供方：仅接收排盘事实快照、触发的规则 ID 与知识库片段，不含账号信息。',
          '支付服务方：内测阶段为 Mock 通道，不涉及真实支付信息。',
          '除上述必要处理方与法律强制要求外，不向第三方提供你的数据。',
        ],
      },
      {
        heading: '五、保存期限',
        list: [
          '命盘与报告：默认长期保存直到你删除；可设置「按日自动删除」。',
          '删除账号：进入待清理状态，30 天后物理删除。',
          '支付与额度流水：因对账需要保留，与账号解绑后仅保留最小必要字段。',
        ],
      },
      {
        heading: '六、你的权利',
        list: [
          '查询与导出：在「我的账号」页可一键导出全部数据（JSON）。',
          '更正：可修改昵称与命盘标题。',
          '删除：可删除单份命盘、笔记，或整体注销账号。',
          '撤回同意：撤回后相关功能可能不可用，但不影响撤回前的处理合法性。',
        ],
      },
      {
        heading: '七、安全措施',
        list: [
          '密码使用 Argon2id 哈希，访问令牌有效期 15 分钟，刷新令牌存于 httpOnly Cookie。',
          '越权访问他人命盘返回 404（避免探测）。',
          '密钥仅通过环境变量注入，不写入代码仓库与前端产物。',
        ],
      },
      {
        heading: '八、联系方式',
        paragraphs: ['隐私相关问题可通过「投诉与联系」页提交，我们会在 15 个工作日内答复。'],
      },
    ],
  },
  terms: {
    title: '用户协议',
    version: 'V1 草案（2026-10-24.v1）',
    updated: '2026-10-24',
    intro: '使用本服务即表示你已阅读并同意本协议。若不同意，请停止使用。',
    sections: [
      {
        heading: '一、服务性质',
        list: [
          '本服务提供传统文化研习工具：确定性排盘、关系规则查询与带引用的 AI 解释。',
          '本站内容属于文化知识普及，不构成医疗、法律、投资、婚恋、心理等任何专业建议。',
          '不得将本服务用于疾病诊断、博彩、算命收费、诈骗或其他违法用途。',
        ],
      },
      {
        heading: '二、账号',
        list: [
          '你需要提供有效邮箱以注册账号，并对账号下的行为负责。',
          '不得批量注册、共享账号、绕过额度限制或攻击服务。',
          '发现异常登录可立即修改密码或注销账号。',
        ],
      },
      {
        heading: '三、内容与知识产权',
        list: [
          '排盘结果与报告可供你个人研习使用；转述时须保留「AI 生成」标识与本站出处。',
          '知识库文本来自公版古籍或自撰摘要，逐条登记许可状态。',
          '不得抓取、镜像、批量导出本站知识库用于商业用途。',
        ],
      },
      {
        heading: '四、额度与付费',
        list: [
          '免费额度按自然日刷新；付费额度按订单发放，不自动续费。',
          '内测阶段支付为演示通道，不产生真实扣款。',
          '生成失败不额外扣费；额度流水可在「我的账号」中查询。',
        ],
      },
      {
        heading: '五、免责与限制',
        list: [
          '我们不承诺任何预测准确性，也不对依据本站内容作出的决定承担责任。',
          'AI 输出可能包含错误或不适用于你具体情况的表述，请自行判断。',
          '因不可抗力、网络故障、第三方服务中断导致的服务不可用，我们将尽力恢复但不承担赔偿责任。',
        ],
      },
      {
        heading: '六、协议变更',
        paragraphs: ['协议更新会在本页公布版本号与生效日期；重大变更会在站内提示并要求重新确认。'],
      },
    ],
  },
  ai: {
    title: 'AI 使用说明',
    version: 'V1（2026-10-24.v1）',
    updated: '2026-10-24',
    intro:
      '本站把「算」和「说」严格分开：事实由确定性引擎计算，解释由 AI 生成，再由服务端逐项校验。下面是这套机制的完整说明。',
    sections: [
      {
        heading: '一、哪些是算出来的，哪些是写出来的',
        list: [
          '算出来的：四柱干支、藏干与权重、十神、五行统计、节气交节时刻、大运起运与排布、关系规则触发结果。',
          '写出来的：报告中的传统解释、现实反思建议与不确定项表述。',
          '报告的每一个观测项都必须挂上已触发的规则 ID 与真实存在的知识库引用。',
        ],
      },
      {
        heading: '二、服务端会拦住什么',
        list: [
          '引用伪造：引用了知识库中不存在的 chunk_id。',
          '规则越界：观测项声明了本盘未触发的 rule_id。',
          '事实改写：正文出现了盘面中不存在的干支组合。',
          '绝对化表述：必然、一定会、注定、改命等断言。',
          '专业越界：疾病诊断、投资指令、法律结论、赌博彩票内容。',
        ],
      },
      {
        heading: '三、校验失败会怎样',
        list: [
          '先做一次受控重试；仍不通过则切换为降级模板，并在报告顶部明确标注。',
          '降级模板只陈述盘面事实与「知识库依据不足」，不编造解释。',
          '降级不额外扣费。',
        ],
      },
      {
        heading: '四、你的输入如何被使用',
        list: [
          '上传给模型的只有排盘事实快照、触发的规则 ID、知识库片段与口径标识。',
          '不上传邮箱、昵称、笔记正文、订单与支付数据。',
          '不用于训练；如未来提供「同意用于改进」的选项，将默认关闭并单独取得同意。',
        ],
      },
      {
        heading: '五、如何判断一份报告是否可信',
        list: [
          '看顶部是否有「降级」标识。',
          '看引用列表是否每条都能点开看到书名、版本与章节。',
          '看不确定项是否明确写出时辰不详、交节临界或口径差异。',
        ],
      },
    ],
  },
  refund: {
    title: '退款说明',
    version: 'V1（2026-10-24.v1）',
    updated: '2026-10-24',
    intro: '内测阶段支付为演示通道，不产生真实扣款；以下规则为正式开放后的拟定方案，开放前会重新核验。',
    sections: [
      {
        heading: '一、额度与订单',
        list: [
          '单次报告套餐：按次发放额度，未使用的额度长期有效。',
          '会员套餐：按自然月发放额度池，到期未使用部分不结转。',
          '订单状态与额度发放记录可在「我的账号」中查询。',
        ],
      },
      {
        heading: '二、可退款情形',
        list: [
          '订单已支付但额度未到账，且经核查确属平台问题。',
          '同一订单被重复扣款（幂等校验失败导致的重复支付）。',
          '服务在有效期内持续不可用超过 72 小时且无法修复。',
        ],
      },
      {
        heading: '三、不可退款情形',
        list: [
          '额度已实际消耗（已生成报告）。',
          '因输入信息有误导致结果与预期不同（排盘口径已在结果中回显）。',
          '对 AI 解释的准确性存在主观异议，但报告已通过服务端校验且未降级。',
        ],
      },
      {
        heading: '四、申请方式',
        paragraphs: [
          '通过「投诉与联系」提交订单号与问题描述。我们会在 5 个工作日内答复，退款原路返回。',
        ],
      },
    ],
  },
  complaint: {
    title: '投诉与联系',
    version: 'V1（2026-10-24.v1）',
    updated: '2026-10-24',
    intro: '如果你发现内容错误、违规表述或服务问题，请通过以下通道反馈，我们会留痕并逐条处理。',
    sections: [
      {
        heading: '一、可投诉的事项',
        list: [
          '排盘结果与公开资料不符（请附出生时间、口径与期望结果）。',
          '报告出现绝对化、恐吓性或专业越界表述。',
          '引用了不存在或未授权的知识来源。',
          '账号、额度、订单相关的问题。',
          '隐私与数据删除相关的请求。',
        ],
      },
      {
        heading: '二、处理时限',
        list: [
          '内容类问题：3 个工作日内给出核查结论。',
          '订单与退款：5 个工作日内答复。',
          '隐私与数据删除：15 个工作日内完成处理。',
        ],
      },
      {
        heading: '三、反馈入口',
        paragraphs: [
          '在命盘详情页可以针对具体报告提交评分与错误说明；也可以发送邮件至 support@example.invalid（内测期间为占位地址）。',
          '所有处理动作都会写入审计日志，包含时间、操作人、处理结论。',
        ],
      },
      {
        heading: '四、不接受的事项',
        paragraphs: [
          '本站不提供个人命运预测、疾病诊断、投资建议、法律意见与博彩相关咨询，此类请求会被拒绝。',
        ],
      },
    ],
  },
}

const route = useRoute()

const docKey = computed(() => String(route.params.doc ?? 'privacy'))
const doc = computed(() => DOCS[docKey.value] ?? DOCS.privacy)

const links = [
  { key: 'privacy', label: '隐私政策' },
  { key: 'terms', label: '用户协议' },
  { key: 'ai', label: 'AI 使用说明' },
  { key: 'refund', label: '退款说明' },
  { key: 'complaint', label: '投诉与联系' },
]
</script>

<template>
  <div class="legal">
    <aside class="side">
      <div class="side-title">合规文档</div>
      <router-link
        v-for="item in links"
        :key="item.key"
        :to="`/legal/${item.key}`"
        class="side-link"
        :class="{ active: item.key === docKey }"
      >
        {{ item.label }}
      </router-link>
      <div class="side-foot">
        内测版本，文档为草案，正式开放前将重新核验合规性。
      </div>
    </aside>

    <article class="doc">
      <h2>{{ doc.title }}</h2>
      <div class="meta">
        <el-tag size="small" effect="plain">{{ doc.version }}</el-tag>
        <span>更新日期：{{ doc.updated }}</span>
      </div>
      <p class="intro">{{ doc.intro }}</p>

      <section v-for="section in doc.sections" :key="section.heading">
        <h3>{{ section.heading }}</h3>
        <p v-for="(para, index) in section.paragraphs ?? []" :key="index">{{ para }}</p>
        <ul v-if="section.list">
          <li v-for="item in section.list" :key="item">{{ item }}</li>
        </ul>
      </section>
    </article>
  </div>
</template>

<style scoped>
.legal {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 22px;
  align-items: start;
}

.side {
  position: sticky;
  top: 12px;
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.side-title {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-bottom: 4px;
}

.side-link {
  font-size: 13px;
  color: var(--xs-text);
  text-decoration: none;
  padding: 6px 8px;
  border-radius: 8px;
}

.side-link:hover {
  background: var(--xs-surface-muted);
}

.side-link.active {
  background: var(--xs-surface-muted);
  color: var(--xs-accent);
  font-weight: 600;
}

.side-foot {
  margin-top: 10px;
  font-size: 11px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.doc {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 22px 26px;
}

.doc h2 {
  margin: 0 0 10px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.intro {
  margin: 14px 0;
  font-size: 13px;
  line-height: 1.9;
  color: var(--xs-text-muted);
  background: var(--xs-surface-muted);
  border-radius: 10px;
  padding: 12px 14px;
}

.doc section {
  margin-top: 18px;
}

.doc h3 {
  margin: 0 0 8px;
  font-size: 15px;
}

.doc p,
.doc li {
  font-size: 13px;
  line-height: 1.95;
  color: var(--xs-text);
}

.doc ul {
  margin: 0;
  padding-left: 20px;
}

@media (max-width: 820px) {
  .legal {
    grid-template-columns: 1fr;
  }

  .side {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .side-foot {
    width: 100%;
  }
}
</style>
