<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import * as chartsApi from '@/api/charts'
import { useAuthStore } from '@/stores/auth'
import type { ChartResult, ZiweiFormInput } from '@/api/types'

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

const form = reactive<ZiweiFormInput>({
  calendar: 'gregorian',
  birth_datetime: '1990-05-20T12:00:00',
  is_leap_month: false,
  timezone: 'Asia/Shanghai',
  time_known: true,
  gender: 'male',
})

const isLunar = computed(() => form.calendar === 'lunar')

/** 大限/流年四化是可选层：用文本输入再转数字，避免 el-input-number 的 null 类型问题 */
const reviewAge = ref('')
const reviewYear = ref('')
const flyingDepth = ref<1 | 2 | 3>(2)

function optionalNumber(text: string): number | null {
  const value = text.trim()
  if (!value) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

const rules = {
  birth_datetime: [{ required: true, message: '请填写出生时间', trigger: 'change' }],
  timezone: [{ required: true, message: '请选择或填写时区', trigger: 'change' }],
}

function payload(): Record<string, unknown> {
  const body: Record<string, unknown> = {
    calendar: form.calendar,
    birth_datetime: form.birth_datetime,
    is_leap_month: isLunar.value ? form.is_leap_month : false,
    timezone: form.timezone,
    time_known: form.time_known,
    gender: form.gender,
  }
  // 不填就不传：后端未收到这两个字段时不会输出对应四化层，也不会猜年龄
  const age = optionalNumber(reviewAge.value)
  const year = optionalNumber(reviewYear.value)
  if (age !== null) body.review_age = age
  if (year !== null) body.review_year = year
  body.flying_depth = flyingDepth.value
  return body
}

async function onSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor('ziwei', payload())
    ElMessage.success('排盘完成')
  } catch {
    // 统一错误提示已在 axios 拦截器里给出
  } finally {
    loading.value = false
  }
}

async function onSave(interpret: boolean): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存命盘需要先登录')
    router.push({ path: '/login', query: { redirect: '/ziwei' } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor(
      'ziwei',
      payload(),
      saveTitle.value || '紫微命盘',
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
  form.calendar = 'gregorian'
  form.birth_datetime = '1990-05-20T12:00:00'
  form.is_leap_month = false
  form.timezone = 'Asia/Shanghai'
  form.time_known = true
  form.gender = 'male'
  reviewAge.value = ''
  reviewYear.value = ''
  flyingDepth.value = 2
  saveTitle.value = ''
  result.value = null
}
</script>

<template>
  <div class="ziwei-page">
    <div class="intro">
      <h2>紫微斗数</h2>
      <p>
        输入出生时间即可安星，<strong>无需登录</strong>。本版本只实现
        <strong>三合派单一口径</strong>：安星按《紫微斗数全书》通行法，庚干四化采「太阳、武曲、太阴、天同」，
        闰月按本月计，23:00–24:00 按当日之子时计。其他流派不支持，也不静默套用。
      </p>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" class="form-card">
      <el-form-item label="历法">
        <el-radio-group v-model="form.calendar">
          <el-radio value="gregorian">公历</el-radio>
          <el-radio value="lunar">农历</el-radio>
        </el-radio-group>
        <span class="inline-note">
          {{ isLunar ? '下方按农历年-月-日填写，闰月请勾选' : '下方按公历填写，由服务端换算农历' }}
        </span>
      </el-form-item>

      <el-form-item label="出生时间" prop="birth_datetime">
        <el-date-picker
          v-model="form.birth_datetime"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm"
          :placeholder="isLunar ? '选择农历日期与时间' : '选择公历日期与时间'"
          :clearable="false"
          style="width: 260px"
        />
        <span class="inline-note">
          {{ isLunar ? '按农历年月日填写，系统据此换算为公历时刻' : '按当地钟表时间填写' }}
        </span>
      </el-form-item>

      <el-form-item v-if="isLunar" label="闰月">
        <el-switch v-model="form.is_leap_month" active-text="是闰月" inactive-text="非闰月" />
        <span class="inline-note">仅农历输入有效；闰月按本月安星，不并入下月</span>
      </el-form-item>

      <el-form-item label="时区">
        <el-select v-model="form.timezone" filterable allow-create default-first-option style="width: 200px">
          <el-option v-for="tz in TIMEZONES" :key="tz" :label="tz" :value="tz" />
        </el-select>
      </el-form-item>

      <el-form-item label="性别">
        <el-radio-group v-model="form.gender">
          <el-radio value="male">男</el-radio>
          <el-radio value="female">女</el-radio>
          <el-radio value="unknown">不填</el-radio>
        </el-radio-group>
        <span class="inline-note">用于大限顺逆（阳男阴女顺行）；不填时按阳年顺行占位</span>
      </el-form-item>

      <el-form-item label="时辰">
        <el-switch v-model="form.time_known" active-text="时间确定" inactive-text="时辰不详" />
        <span class="inline-note">时辰不详时按午时占位安星，命宫与全盘星曜都可能偏移</span>
      </el-form-item>

      <el-form-item label="推演层次">
        <el-input v-model="reviewAge" placeholder="虚岁，如 30" style="width: 140px" />
        <span class="inline-note">可选：填了才算「大限四化」，不填不猜年龄</span>
      </el-form-item>

      <el-form-item label="流年">
        <el-input v-model="reviewYear" placeholder="农历年，如 2026" style="width: 140px" />
        <span class="inline-note">可选：填了才算「流年四化」与流年命宫</span>
      </el-form-item>

      <el-form-item label="飞星深度">
        <el-radio-group v-model="flyingDepth">
          <el-radio :value="1">一跳</el-radio>
          <el-radio :value="2">两跳</el-radio>
          <el-radio :value="3">三跳</el-radio>
        </el-radio-group>
        <span class="inline-note">只列链路（A→B→C），不推事件；深度越高条目越多</span>
      </el-form-item>

      <el-form-item class="form-item-full">
        <el-button type="primary" :loading="loading" @click="onSubmit">开始排盘</el-button>
        <el-button @click="onReset">清空</el-button>
      </el-form-item>
    </el-form>

    <div v-if="result" class="result">
      <div class="result-head">
        <h3>命盘</h3>
        <div class="save-row">
          <el-input v-model="saveTitle" placeholder="给这张命盘起个名字（可选）" style="width: 220px" />
          <el-button plain :loading="saving" @click="onSave(false)">保存命盘</el-button>
          <el-button type="primary" :loading="saving" @click="onSave(true)">保存并生成解读</el-button>
        </div>
      </div>

      <ChartBoard :result="result" />

      <el-alert
        class="next-step"
        type="info"
        :closable="false"
        show-icon
        title="关于解读"
        description="解读只复述盘面事实与可查证的典籍条目，不含吉凶断语、流年推演与格局评价。保存后可随时在命盘详情页重新生成。"
      />
    </div>
  </div>
</template>

<style scoped>
.ziwei-page {
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
  border-radius: 16px;
  background: #fff;
  padding: 22px 24px 8px;
  box-shadow: var(--xs-shadow);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 28px;
  align-items: start;
}

.form-card :deep(.el-form-item) {
  margin-bottom: 18px;
}

.form-card :deep(.form-item-full) {
  grid-column: 1 / -1;
}

@media (max-width: 980px) {
  .form-card {
    grid-template-columns: minmax(0, 1fr);
  }
}

.inline-note {
  margin-left: 12px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.6;
}

.result {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.result-head h3 {
  margin: 0;
}

.save-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.next-step {
  margin-top: 4px;
}

@media (max-width: 720px) {
  .inline-note {
    margin-left: 0;
    display: block;
  }
}
</style>
