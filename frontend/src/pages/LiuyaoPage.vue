<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartFrame from '@/components/chart/ChartFrame.vue'
import * as chartsApi from '@/api/charts'
import { useAuthStore } from '@/stores/auth'
import type { ChartResult, LiuyaoFormInput } from '@/api/types'

const router = useRouter()
const auth = useAuthStore()

const formRef = ref()
const result = ref<ChartResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveTitle = ref('')

const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Tokyo',
  'Europe/London',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
]

/** 6/7/8/9 依次为老阴、少阳、少阴、老阳；6 与 9 为动爻 */
const LINE_OPTIONS = [
  { value: 6, label: '老阴 ✕', hint: '动，变阳' },
  { value: 7, label: '少阳', hint: '静，阳爻' },
  { value: 8, label: '少阴', hint: '静，阴爻' },
  { value: 9, label: '老阳 ○', hint: '动，变阴' },
]

const POSITION_LABELS = ['初爻', '二爻', '三爻', '四爻', '五爻', '上爻']

const form = reactive<LiuyaoFormInput>({
  method: 'coins',
  cast_datetime: '2026-01-01T12:00:00',
  timezone: 'Asia/Shanghai',
  seed: null,
  question: '',
  store_question: true,
})

/** 手填六爻（初爻在前、上爻在后），单独存放便于逐爻 v-model */
const manualLines = ref<number[]>([7, 7, 7, 7, 7, 7])

const isManual = computed(() => form.method === 'manual')
const isCoins = computed(() => form.method === 'coins')

/** 手填时自上而下展示：上爻在第 1 行，初爻在最后一行 */
const manualRows = computed(() =>
  POSITION_LABELS.map((label, index) => ({ label, index })).reverse(),
)

const rules = {
  cast_datetime: [{ required: true, message: '请填写起卦时间', trigger: 'change' }],
  timezone: [{ required: true, message: '请选择或填写时区', trigger: 'change' }],
}

function payload(): Record<string, unknown> {
  const body: Record<string, unknown> = {
    method: form.method,
    cast_datetime: form.cast_datetime,
    timezone: form.timezone,
    question: form.question?.trim() ? form.question.trim() : null,
    store_question: form.store_question,
  }
  if (isCoins.value && form.seed !== null && form.seed !== undefined) {
    body.seed = Number(form.seed)
  }
  if (isManual.value) {
    body.lines = [...manualLines.value]
  }
  return body
}

async function onSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor('liuyao', payload())
    ElMessage.success('起卦完成')
  } catch {
    // 统一错误提示已在 axios 拦截器里给出
  } finally {
    loading.value = false
  }
}

async function onSave(interpret: boolean): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存卦盘需要先登录')
    router.push({ path: '/login', query: { redirect: '/liuyao' } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor(
      'liuyao',
      payload(),
      saveTitle.value || '六爻卦盘',
    )
    ElMessage.success('已保存到「我的命盘」')
    if (interpret) {
      router.push(`/charts/${chart.id}?interpret=1&depth=brief`)
    } else {
      router.push(`/charts/${chart.id}`)
    }
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

function onReset(): void {
  form.method = 'coins'
  form.cast_datetime = '2026-01-01T12:00:00'
  form.timezone = 'Asia/Shanghai'
  form.seed = null
  manualLines.value = [7, 7, 7, 7, 7, 7]
  form.question = ''
  form.store_question = true
  saveTitle.value = ''
  result.value = null
}
</script>

<template>
  <div class="liuyao-page">
    <div class="intro">
      <h2>六爻</h2>
      <p>
        三种起卦方式均可<strong>免登录</strong>排盘。本版本只实现<strong>京房纳甲单一口径</strong>：
        月建以节气为界、日辰按所选换日口径、六亲以本卦卦宫五行推算（变爻六亲同样对照本卦卦宫），
        六神按日干起于初爻顺排。只出装卦层，不取用神、不判旺衰、不给应期。
      </p>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" class="form-card">
      <el-form-item label="起卦方式">
        <el-radio-group v-model="form.method">
          <el-radio value="coins">三枚铜钱</el-radio>
          <el-radio value="time">时间起卦</el-radio>
          <el-radio value="manual">手动输入</el-radio>
        </el-radio-group>
        <span class="inline-note">
          {{
            isCoins
              ? '由服务端按种子模拟掷钱，可复现；正式占问请掷实体铜钱后手填'
              : isManual
                ? '按自下而上的实际掷出结果逐爻填写，6/9 为动爻'
                : '梅花易数取数法：年支+月+日取上卦，再加时支取下卦与动爻，只有单个动爻'
          }}
        </span>
      </el-form-item>

      <el-form-item label="起卦时间" prop="cast_datetime">
        <el-date-picker
          v-model="form.cast_datetime"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm"
          placeholder="选择起卦的当地钟表时间"
          :clearable="false"
          style="width: 260px"
        />
        <span class="inline-note">决定日辰、月建与旬空；23:00 之后按所选换日口径处理</span>
      </el-form-item>

      <el-form-item label="时区">
        <el-select v-model="form.timezone" filterable allow-create default-first-option style="width: 200px">
          <el-option v-for="tz in TIMEZONES" :key="tz" :label="tz" :value="tz" />
        </el-select>
      </el-form-item>

      <el-form-item v-if="isCoins" label="随机种子">
        <el-input-number v-model="form.seed" :min="0" :max="4294967295" :controls="false" placeholder="留空则按起卦时刻派生" style="width: 200px" />
        <span class="inline-note">同一时间 + 同一种子必得同一卦，便于复核与回归</span>
      </el-form-item>

      <el-form-item v-if="isManual" label="六爻">
        <div class="manual-grid">
          <div v-for="row in manualRows" :key="row.index" class="manual-row">
            <span class="pos-label">{{ row.label }}</span>
            <el-radio-group v-model="manualLines[row.index]" size="small">
              <el-radio-button v-for="option in LINE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </el-radio-button>
            </el-radio-group>
          </div>
        </div>
      </el-form-item>

      <el-form-item label="占问">
        <el-input
          v-model="form.question"
          type="textarea"
          :rows="2"
          maxlength="200"
          show-word-limit
          placeholder="可选。只用于本次解读的上下文，不会写入任何调用日志"
        />
      </el-form-item>

      <el-form-item label="原文保存">
        <el-switch v-model="form.store_question" active-text="保存占问原文" inactive-text="只存盘面" />
        <span class="inline-note">选择「只存盘面」时，服务端会直接丢弃占问原文，命盘里查不到</span>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">开始起卦</el-button>
        <el-button @click="onReset">清空</el-button>
      </el-form-item>
    </el-form>

        <ChartFrame
      v-if="result"
      v-model:save-title="saveTitle"
      title="卦盘"
      title-placeholder="给这张卦盘起个名字（可选）"
      :result="result"
      :saving="saving"
      save-text="保存卦盘"
      interpret-text="保存并生成解读"
      @save="onSave(false)"
      @interpret="onSave(true)"
    >
      <el-alert
        class="next-step"
        type="info"
        :closable="false"
        show-icon
        title="关于解读"
        description="解读只复述卦名、卦宫、世应、纳甲六亲六神与动变关系，不含吉凶断语、用神取舍与应期推算。"
      />
        </ChartFrame>
  </div>
</template>

<style scoped>
.liuyao-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.intro h2 {
  margin: 0 0 6px;
}

.intro p {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.form-card {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 20px 22px 8px;
}

.inline-note {
  margin-left: 12px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.6;
}

.manual-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.manual-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pos-label {
  width: 40px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.next-step {
  margin-top: 4px;
}

@media (max-width: 720px) {
  .inline-note {
    margin-left: 0;
    display: block;
  }

  .manual-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>
