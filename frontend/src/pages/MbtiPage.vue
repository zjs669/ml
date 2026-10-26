<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import * as chartsApi from '@/api/charts'
import { getBank, type MbtiBank } from '@/api/mbti'
import type { ChartResult } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

/**
 * 性格问卷页。
 *
 * 题库由后端 `/mbti/questions` 提供，不在前端硬编码 —— 题库版本会随审校更新，
 * 硬编码会让「前端问的」和「后端算的」不是同一套题。
 */
const router = useRouter()
const auth = useAuthStore()

const bank = ref<MbtiBank | null>(null)
const answers = reactive<Record<string, 'A' | 'B' | ''>>({})
const result = ref<ChartResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveTitle = ref('')
const error = ref('')

onMounted(async () => {
  try {
    bank.value = await getBank()
    for (const question of bank.value.questions) answers[question.id] = ''
  } catch {
    error.value = '题库加载失败，请稍后重试'
  }
})

const total = computed(() => bank.value?.questions.length ?? 0)
const answered = computed(
  () => Object.values(answers).filter((value) => value === 'A' || value === 'B').length,
)
const progress = computed(() => (total.value ? Math.round((answered.value / total.value) * 100) : 0))
const complete = computed(() => total.value > 0 && answered.value === total.value)

const grouped = computed(() => {
  if (!bank.value) return []
  return bank.value.dimensions.map((dim) => ({
    ...dim,
    questions: bank.value!.questions.filter((item) => item.dimension === dim.dimension),
  }))
})

function pick(id: string, choice: 'A' | 'B'): void {
  answers[id] = choice
}

function payload(): Record<string, unknown> {
  const body: Record<string, string> = {}
  for (const [key, value] of Object.entries(answers)) {
    if (value === 'A' || value === 'B') body[key] = value
  }
  return { answers: body, store_answers: true }
}

async function onSubmit(): Promise<void> {
  if (!complete.value) {
    ElMessage.warning(`还有 ${total.value - answered.value} 题未作答`)
    return
  }
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor('mbti', payload())
    ElMessage.success('已生成结果')
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存结果需要先登录')
    router.push({ path: '/login', query: { redirect: '/mbti' } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor('mbti', payload(), saveTitle.value || '性格问卷')
    ElMessage.success('已保存到「我的命盘」')
    router.push(`/charts/${chart.id}`)
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

const code = computed(() => {
  const facts = result.value?.chart_facts as { code?: string } | undefined
  return facts?.code ?? ''
})

const dimensions = computed(() => {
  const facts = result.value?.chart_facts as
    | { dimensions?: Array<Record<string, unknown>> }
    | undefined
  return facts?.dimensions ?? []
})
</script>

<template>
  <div class="mbti">
    <div class="page-head">
      <h2>性格问卷</h2>
      <p>
        自编 {{ total }} 题四维倾向问卷，不是官方 MBTI 量表。结果只表示本次作答在四个维度上的选择倾向，
        不构成人格诊断或职业建议。
      </p>
    </div>

    <el-alert v-if="error" type="error" :closable="false" :title="error" show-icon />

    <el-progress v-if="total" :percentage="progress" :stroke-width="8" />

    <div v-for="group in grouped" :key="group.dimension" class="group">
      <h3>
        {{ group.name }}
        <span class="poles">{{ group.poles[group.dimension[0]] }} / {{ group.poles[group.dimension[1]] }}</span>
      </h3>
      <div v-for="(question, index) in group.questions" :key="question.id" class="question">
        <div class="q-text">{{ index + 1 }}. {{ question.text }}</div>
        <div class="q-options">
          <el-button
            size="small"
            :type="answers[question.id] === 'A' ? 'primary' : 'default'"
            @click="pick(question.id, 'A')"
          >
            {{ question.option_a }}
          </el-button>
          <el-button
            size="small"
            :type="answers[question.id] === 'B' ? 'primary' : 'default'"
            @click="pick(question.id, 'B')"
          >
            {{ question.option_b }}
          </el-button>
        </div>
      </div>
    </div>

    <div class="actions">
      <el-button type="primary" :loading="loading" :disabled="!complete" @click="onSubmit">
        生成结果（已答 {{ answered }} / {{ total }}）
      </el-button>
    </div>

    <template v-if="result">
      <el-divider content-position="left">结果</el-divider>
      <div class="code">{{ code }}</div>
      <div class="dims">
        <div v-for="dim in dimensions" :key="String(dim.dimension)" class="dim">
          <div class="dim-name">{{ dim.name }}（{{ dim.dimension }}）</div>
          <div class="dim-body">
            <span>{{ (dim.poles as Record<string, Record<string, unknown>>)[(dim.dimension as string)[0]].label }}：
              {{ (dim.poles as Record<string, Record<string, unknown>>)[(dim.dimension as string)[0]].count }}</span>
            <span>{{ (dim.poles as Record<string, Record<string, unknown>>)[(dim.dimension as string)[1]].label }}：
              {{ (dim.poles as Record<string, Record<string, unknown>>)[(dim.dimension as string)[1]].count }}</span>
            <el-tag size="small" effect="plain">{{ dim.tendency_label }}</el-tag>
          </div>
        </div>
      </div>

      <div class="save-row">
        <el-input v-model="saveTitle" placeholder="标题（默认：性格问卷）" style="max-width: 320px" />
        <el-button :loading="saving" @click="onSave">保存结果</el-button>
      </div>

      <el-collapse v-if="result.warnings.length">
        <el-collapse-item :title="`说明（${result.warnings.length} 条）`">
          <ul>
            <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
.mbti {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.page-head h2 {
  margin: 0 0 6px;
}

.page-head p {
  margin: 0;
  font-size: 13px;
  color: var(--xs-text-muted);
  line-height: 1.8;
}

.group {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: var(--xs-surface);
  padding: 16px 20px;
  box-shadow: var(--xs-shadow);
}

.group h3 {
  margin: 0 0 12px;
  font-size: 15px;
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.poles {
  font-size: 12px;
  font-weight: 400;
  color: var(--xs-text-muted);
}

.question {
  padding: 10px 0;
  border-top: 1px dashed var(--xs-border);
}

.question:first-of-type {
  border-top: none;
}

.q-text {
  font-size: 13px;
  margin-bottom: 8px;
}

.q-options {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.actions {
  display: flex;
  gap: 10px;
}

.code {
  font-family: 'Songti SC', serif;
  font-size: 30px;
  letter-spacing: 0.16em;
  color: var(--xs-accent);
}

.dims {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.dim {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--xs-surface);
}

.dim-name {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.dim-body {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 12px;
  color: var(--xs-text-muted);
  flex-wrap: wrap;
}

.save-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}
</style>
