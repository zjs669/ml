<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import QuotaBadge from '@/components/common/QuotaBadge.vue'
import ModelBadge from '@/components/report/ModelBadge.vue'
import ReportSections from '@/components/report/ReportSections.vue'
import * as chartsApi from '@/api/charts'
import * as reportsApi from '@/api/reports'
import { useUsageStore } from '@/stores/usage'
import type { ChartOut, Depth, FollowupOut, ReportListItem, ReportOut } from '@/api/types'

const route = useRoute()
const router = useRouter()
const usage = useUsageStore()

const chartId = computed(() => Number(route.params.id))

const chart = ref<ChartOut | null>(null)
const loading = ref(false)
const notFound = ref(false)

const reports = ref<ReportListItem[]>([])
const report = ref<ReportOut | null>(null)
const reportLoading = ref(false)
const depth = ref<Depth>('brief')

const notes = ref<chartsApi.NoteItem[]>([])
const noteDraft = ref('')

/* ---- 追问 ---- */
const followups = ref<FollowupOut[]>([])
const followupDraft = ref('')
const followupLoading = ref(false)

const shareToken = ref<string | null>(null)
const shareExpires = ref<string | null>(null)

const titleDraft = ref('')

async function loadChart(): Promise<void> {
  loading.value = true
  notFound.value = false
  try {
    const data = await chartsApi.getChart(chartId.value)
    chart.value = data
    titleDraft.value = data.title ?? ''
    await Promise.all([loadReports(), loadNotes()])
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function loadReports(): Promise<void> {
  try {
    reports.value = await reportsApi.listReports(chartId.value)
  } catch {
    reports.value = []
  }
}

async function loadNotes(): Promise<void> {
  try {
    notes.value = await chartsApi.listNotes(chartId.value)
  } catch {
    notes.value = []
  }
}

async function openReport(id: number): Promise<void> {
  reportLoading.value = true
  try {
    report.value = await reportsApi.getReport(id)
    await loadFollowups()
  } catch {
    report.value = null
    followups.value = []
  } finally {
    reportLoading.value = false
  }
}

async function loadFollowups(): Promise<void> {
  if (!report.value) {
    followups.value = []
    return
  }
  try {
    followups.value = await reportsApi.listFollowups(report.value.id)
  } catch {
    followups.value = []
  }
}

/** 追问不扣额度：后端按「原报告 + 原盘面 + 原引用」回答，并受限流与日预算约束。 */
async function ask(): Promise<void> {
  if (!report.value) return
  const question = followupDraft.value.trim()
  if (!question) return
  followupLoading.value = true
  try {
    const turn = await reportsApi.askFollowup(report.value.id, question)
    followups.value = [...followups.value, turn]
    followupDraft.value = ''
  } catch {
    // 拦截器已提示具体原因
  } finally {
    followupLoading.value = false
  }
}

async function generate(): Promise<void> {
  if (!chart.value) return
  reportLoading.value = true
  const rollback = usage.optimisticDeduct(depth.value)
  try {
    const created = await reportsApi.generateReport(chartId.value, {
      depth: depth.value,
      idempotencyKey: reportsApi.buildIdempotencyKey(chartId.value, depth.value),
    })
    report.value = created
    followups.value = []
    await loadReports()
    ElMessage.success(created.status === 'degraded' ? '已生成（降级模板）：模型输出未通过校验' : '报告已生成')
  } catch {
    rollback()
  } finally {
    reportLoading.value = false
    await usage.load()
  }
}

async function renameChart(): Promise<void> {
  if (!chart.value) return
  const updated = await chartsApi.patchChart(chartId.value, { title: titleDraft.value || null })
  chart.value = updated
  ElMessage.success('标题已更新')
}

async function exportAs(format: 'md' | 'txt'): Promise<void> {
  const text = await chartsApi.exportChart(chartId.value, format)
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `chart-${chartId.value}.${format}`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('已导出，文件头部包含 AI 生成内容标识')
}

async function share(): Promise<void> {
  const data = await chartsApi.createShare(chartId.value, 7, 'basic')
  shareToken.value = data.token
  shareExpires.value = data.expires_at
  const link = `${window.location.origin}/share/${data.token}`
  try {
    await navigator.clipboard.writeText(link)
    ElMessage.success('分享链接已复制（仅显示这一次，请妥善保存）')
  } catch {
    ElMessage.info('分享链接已生成，请手动复制')
  }
}

async function revoke(): Promise<void> {
  if (!shareToken.value) return
  await chartsApi.revokeShare(shareToken.value)
  shareToken.value = null
  shareExpires.value = null
  ElMessage.success('分享链接已撤销')
}

async function addNote(): Promise<void> {
  if (!noteDraft.value.trim()) return
  await chartsApi.addNote(chartId.value, noteDraft.value.trim())
  noteDraft.value = ''
  await loadNotes()
}

async function removeNote(id: number): Promise<void> {
  await chartsApi.deleteNote(chartId.value, id)
  await loadNotes()
}

async function removeChart(): Promise<void> {
  await ElMessageBox.confirm(
    '删除后命盘与关联报告将不可访问，且无法恢复。确定删除？',
    '删除命盘',
    { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
  )
  await chartsApi.deleteChart(chartId.value)
  ElMessage.success('命盘已删除')
  router.push('/account')
}

const shareLink = computed(() =>
  shareToken.value ? `${window.location.origin}/share/${shareToken.value}` : '',
)

/** 降级原因取 uncertainties 的第一条（后端已按 reason_kind 分好文案）。 */
const degradedReason = computed(() => report.value?.report.uncertainties?.[0] || '模型未能给出合规输出。')

/**
 * 两类降级给不同引导。混在一起时，用户会把「这个问题超出本报告材料」
 * 误读成「系统坏了」——前者重试一百次也没用，后者重做报告纯属浪费。
 */
function degradedTitle(kind?: string): string {
  return kind === 'MODEL_UNAVAILABLE' ? '模型暂时不可用' : '这个问题超出本报告材料范围'
}

function degradedGuide(kind?: string): string {
  return kind === 'MODEL_UNAVAILABLE'
    ? '模型侧没有返回可用结果（可能未配置、上游失败或当日预算已用尽），稍后重试即可，不需要重做报告。'
    : '追问只能引用原报告已检索到的片段。这个方向本报告没有材料，请生成一份新报告，让检索重新取片段。'
}

watch(chartId, () => {
  report.value = null
  followups.value = []
  void loadChart()
})

/**
 * 从反查页跳过来时带上 `interpret=1`：进入即自动生成一次解读。
 * 用后立刻清掉 query 与 sessionStorage，刷新不会重复生成也不会重复扣额度。
 */
const autoInterpreted = ref(false)

async function maybeAutoInterpret(): Promise<void> {
  if (autoInterpreted.value) return
  if (route.query.interpret !== '1') return
  autoInterpreted.value = true
  const wanted = typeof route.query.depth === 'string' ? (route.query.depth as Depth) : 'brief'
  if (wanted === 'brief' || wanted === 'detailed') depth.value = wanted
  const rest = { ...route.query }
  delete rest.interpret
  await router.replace({ path: route.path, query: rest })
  sessionStorage.removeItem('xs:pending-chart')
  await generate()
}

onMounted(async () => {
  await loadChart()
  await usage.load()
  await maybeAutoInterpret()
})
</script>

<template>
  <div class="chart-page">
    <el-skeleton v-if="loading" :rows="6" animated />

    <el-result
      v-else-if="notFound"
      icon="warning"
      title="命盘不存在"
      sub-title="可能已被删除，或不属于当前账号。"
    >
      <template #extra>
        <el-button type="primary" @click="router.push('/bazi')">去排盘</el-button>
      </template>
    </el-result>

    <template v-else-if="chart">
      <div class="head">
        <div class="title-row">
          <el-input v-model="titleDraft" class="title-input" placeholder="未命名命盘" />
          <el-button size="small" @click="renameChart">重命名</el-button>
        </div>
        <div class="tools">
          <el-button size="small" @click="exportAs('md')">导出 Markdown</el-button>
          <el-button size="small" @click="exportAs('txt')">导出纯文本</el-button>
          <el-button size="small" @click="share">生成分享链接</el-button>
          <el-button size="small" type="danger" plain @click="removeChart">删除命盘</el-button>
        </div>
      </div>

      <div v-if="shareLink" class="share-box">
        <span class="share-label">分享链接（7 天有效，可随时撤销）</span>
        <code class="share-link">{{ shareLink }}</code>
        <span class="share-expire">到期：{{ shareExpires }}</span>
        <el-button size="small" text type="danger" @click="revoke">撤销</el-button>
      </div>

      <ChartBoard :result="chart" />

      <section class="report-area">
        <div class="section-head">
          <h3>AI 解读</h3>
          <div class="depth-row">
            <el-radio-group v-model="depth">
              <el-radio-button value="brief">简版</el-radio-button>
              <el-radio-button value="detailed">详版</el-radio-button>
            </el-radio-group>
            <el-button type="primary" :loading="reportLoading" @click="generate">生成解读</el-button>
          </div>
        </div>

        <QuotaBadge :depth="depth" show-upload />

        <div v-if="reports.length" class="history">
          <span class="history-label">历史报告</span>
          <el-button
            v-for="item in reports"
            :key="item.id"
            size="small"
            :type="report?.id === item.id ? 'primary' : 'default'"
            @click="openReport(item.id)"
          >
            #{{ item.id }} · {{ item.depth === 'detailed' ? '详版' : '简版' }} ·
            {{ item.status === 'degraded' ? '降级' : '正常' }} · {{ item.created_at.slice(0, 16) }}
          </el-button>
        </div>

        <el-skeleton v-if="reportLoading && !report" :rows="5" animated />

        <template v-else-if="report">
          <div class="report-meta">
            <el-tag size="small" effect="plain">报告 #{{ report.id }}</el-tag>
            <ModelBadge
              :provider="report.model_provider"
              :model="report.model_name"
              :degraded="report.status === 'degraded'"
            />
            <el-tag size="small" effect="plain">技能 {{ report.skill_version }}</el-tag>
            <el-tag size="small" effect="plain">提示词 {{ report.prompt_version }}</el-tag>
            <el-tag size="small" effect="plain">算法 {{ report.algorithm_version }}</el-tag>
            <el-tag v-if="report.status === 'degraded'" size="small" type="warning" effect="plain">已降级</el-tag>
          </div>
          <el-alert
            v-if="report.status === 'degraded'"
            type="warning"
            :closable="false"
            show-icon
            title="本次未生成 AI 解释，仅展示盘面事实"
          >
            <p class="degraded-reason">{{ degradedReason }}</p>
            <p class="degraded-reason">本次预扣额度已全额退还，不会计入消耗。</p>
          </el-alert>
          <ReportSections :report="report.report" :citations="report.citations" :status="report.status" />

          <section class="followup">
            <div class="followup-head">
              <h4>继续追问</h4>
              <span class="followup-hint">
                追问仅基于本报告已有内容回答，不重新检索；如需全新问题，请生成新报告。
                同一报告最多 20 轮，不扣额度。
              </span>
            </div>

            <p v-if="!followups.length" class="followup-empty">
              可以问「为什么这么判」「另一个宫位怎么看」「这条引用的原文是什么」。
            </p>

            <ul v-else class="chat">
              <li v-for="turn in followups" :key="turn.id" class="turn">
                <div class="q">
                  <span class="q-idx">问 {{ turn.seq }}</span>
                  <span>{{ turn.question }}</span>
                </div>
                <div class="a">
                  <p class="answer">{{ turn.answer.answer }}</p>
                  <ul v-if="turn.answer.points.length" class="points">
                    <li v-for="(point, index) in turn.answer.points" :key="index">{{ point }}</li>
                  </ul>
                  <ul v-if="turn.answer.uncertainties.length" class="uncertain">
                    <li v-for="(item, index) in turn.answer.uncertainties" :key="index">{{ item }}</li>
                  </ul>
                  <el-alert
                    v-if="turn.status === 'degraded'"
                    class="degraded-guide"
                    type="warning"
                    :closable="false"
                    show-icon
                    :title="degradedTitle(turn.answer.reason_kind)"
                  >
                    <template #default>
                      <p class="guide-text">{{ degradedGuide(turn.answer.reason_kind) }}</p>
                      <el-button
                        v-if="turn.answer.reason_kind !== 'MODEL_UNAVAILABLE'"
                        size="small"
                        type="warning"
                        plain
                        @click="generate"
                      >
                        重新生成报告
                      </el-button>
                      <span v-else class="guide-hint">稍后点上方「生成解读」重试即可。</span>
                    </template>
                  </el-alert>
                  <div class="turn-foot">
                    <el-tag v-if="turn.status === 'degraded'" size="small" type="warning" effect="plain">
                      降级
                    </el-tag>
                    <span v-for="cite in turn.citations" :key="cite.chunk_id" class="cite">
                      《{{ cite.title }}》{{ cite.location || '' }}
                    </span>
                    <span class="safety">{{ turn.answer.safety_note }}</span>
                  </div>
                </div>
              </li>
            </ul>

            <div class="ask-row">
              <el-input
                v-model="followupDraft"
                type="textarea"
                :rows="2"
                maxlength="500"
                show-word-limit
                placeholder="针对这份报告继续问…（Ctrl + Enter 发送）"
                @keydown.ctrl.enter="ask"
              />
              <el-button type="primary" :loading="followupLoading" @click="ask">提问</el-button>
            </div>
          </section>
        </template>

        <el-empty v-else description="还没有报告，选择深度后点「生成解读」" :image-size="70" />
      </section>

      <section class="notes">
        <div class="section-head">
          <h3>我的笔记</h3>
          <span class="hint">笔记只有你自己可见，不会上传给模型。</span>
        </div>
        <div class="note-input">
          <el-input v-model="noteDraft" type="textarea" :rows="2" maxlength="1000" show-word-limit placeholder="记下你的疑问或核对结果" />
          <el-button type="primary" @click="addNote">添加</el-button>
        </div>
        <el-empty v-if="!notes.length" description="还没有笔记" :image-size="50" />
        <ul v-else class="note-list">
          <li v-for="item in notes" :key="item.id">
            <div class="note-body">{{ item.content }}</div>
            <div class="note-foot">
              <span>{{ item.created_at.slice(0, 16) }}</span>
              <el-button size="small" text type="danger" @click="removeNote(item.id)">删除</el-button>
            </div>
          </li>
        </ul>
      </section>

      <div class="page-foot">
        本页盘面由确定性引擎计算（算法版本 {{ chart.algorithm_version }}），文字解释由 AI 生成并经服务端校验；
        内容属于传统文化研习，不构成专业建议。
      </div>
    </template>
  </div>
</template>

<style scoped>
.chart-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-input {
  width: 240px;
}

.tools {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.share-box {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  border: 1px dashed var(--xs-border);
  border-radius: 10px;
  background: var(--xs-surface-muted);
  padding: 10px 12px;
  font-size: 12px;
}

.share-label {
  color: var(--xs-text-muted);
}

.share-link {
  font-size: 12px;
  word-break: break-all;
}

.share-expire {
  color: var(--xs-text-muted);
}

.report-area,
.notes {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.section-head h3 {
  margin: 0;
}

.depth-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.history {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.history-label {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.report-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.degraded-reason {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.8;
}

.note-input {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.note-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.note-list li {
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  padding: 10px 12px;
}

.note-body {
  font-size: 13px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.note-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.hint {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.page-foot {
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.8;
  border-top: 1px dashed var(--xs-border);
  padding-top: 10px;
}

/* ---- 追问 ---- */
.followup {
  border-top: 1px dashed var(--xs-border);
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.followup-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}

.followup-head h4 {
  margin: 0;
  font-size: 14px;
}

.followup-hint {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.followup-empty {
  margin: 0;
  font-size: 12.5px;
  color: var(--xs-text-muted);
  line-height: 1.8;
}

.chat {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.turn {
  border: 1px solid var(--xs-border);
  border-radius: 10px;
  overflow: hidden;
}

.q {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 8px 12px;
  background: var(--xs-surface-muted);
  font-size: 13px;
}

.q-idx {
  flex: none;
  font-size: 11px;
  color: var(--xs-accent);
  font-weight: 600;
}

.a {
  padding: 10px 12px 12px;
  font-size: 13px;
  line-height: 1.85;
}

.answer {
  margin: 0 0 6px;
  white-space: pre-wrap;
}

.points {
  margin: 0;
  padding-left: 18px;
}

.uncertain {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #8a5a1c;
}

.degraded-guide {
  margin: 8px 0;
}

.degraded-guide .guide-text {
  margin: 0 0 8px;
  line-height: 1.7;
}

.guide-hint {
  font-size: 12px;
  color: var(--xs-text-muted);
}
.turn-foot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11px;
  color: var(--xs-text-muted);
}

.cite {
  border-bottom: 1px dotted var(--xs-border);
}

.safety {
  flex: 1 0 100%;
  line-height: 1.7;
}

.ask-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
</style>
