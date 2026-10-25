<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import ConventionPanel from '@/components/common/ConventionPanel.vue'
import { useChartStore } from '@/stores/chart'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const store = useChartStore()
const auth = useAuthStore()

const formRef = ref()
const saveTitle = ref('')
const saving = ref(false)

const form = reactive({
  birth_datetime: store.form.birth_datetime,
  timezone: store.form.timezone,
  time_known: store.form.time_known,
  gender: store.form.gender,
  longitude: store.form.longitude as number | null,
  convention: { ...store.form.convention },
  liunian_start_year: store.form.liunian_start_year ?? new Date().getFullYear(),
  liunian_years: store.form.liunian_years ?? 10,
})

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

const needsLongitude = computed(() => form.convention.solar_time === 'true_solar_time')

const rules = {
  birth_datetime: [{ required: true, message: '请填写出生时间', trigger: 'change' }],
  timezone: [{ required: true, message: '请选择或填写时区', trigger: 'change' }],
}

onMounted(() => {
  void auth.bootstrap()
})

async function onSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (needsLongitude.value && (form.longitude === null || Number.isNaN(form.longitude))) {
    ElMessage.warning('选择真太阳时后必须填写出生地经度')
    return
  }
  store.form = {
    birth_datetime: form.birth_datetime,
    timezone: form.timezone,
    time_known: form.time_known,
    gender: form.gender,
    longitude: form.longitude,
    convention: { ...form.convention },
    liunian_start_year: form.liunian_start_year,
    liunian_years: form.liunian_years,
  }
  try {
    await store.calculate()
    ElMessage.success('排盘完成')
  } catch {
    // 统一错误提示已在 axios 拦截器里给出
  }
}

async function onSave(): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存命盘需要先登录')
    router.push({ path: '/login', query: { redirect: '/bazi' } })
    return
  }
  if (!store.result) return
  saving.value = true
  try {
    const chart = await store.save(saveTitle.value || '未命名命盘')
    ElMessage.success('已保存到「我的命盘」')
    router.push(`/charts/${chart.id}`)
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

function onReset(): void {
  store.reset()
  form.birth_datetime = store.form.birth_datetime
  form.timezone = store.form.timezone
  form.time_known = store.form.time_known
  form.gender = store.form.gender
  form.longitude = null
  form.convention = {}
  form.liunian_start_year = new Date().getFullYear()
  form.liunian_years = 10
  saveTitle.value = ''
}

const result = computed(() => store.result)
</script>

<template>
  <div class="bazi-page">
    <div class="intro">
      <h2>四柱排盘</h2>
      <p>
        输入公历出生时间即可排盘，<strong>无需登录</strong>。结果只保留在当前页面内存中，刷新即消失；
        想要长期保存请点「保存命盘」。
      </p>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" class="form-card">
      <el-form-item label="出生时间" prop="birth_datetime">
        <el-date-picker
          v-model="form.birth_datetime"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm"
          placeholder="选择公历日期与时间"
          :clearable="false"
          style="width: 260px"
        />
        <span class="inline-note">按当地钟表时间填写，1990-01-01 00:30 这类子时边界请确认换日口径</span>
      </el-form-item>

      <el-form-item label="时区" prop="timezone">
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
        <span class="inline-note">仅用于大运顺逆判断</span>
      </el-form-item>

      <el-form-item label="时辰">
        <el-switch v-model="form.time_known" active-text="时间确定" inactive-text="时辰不详" />
        <span class="inline-note">时辰不详时时柱相关结论会被标注为不确定</span>
      </el-form-item>

      <el-form-item label="出生经度">
        <el-input-number
          v-model="form.longitude"
          :disabled="!needsLongitude"
          :min="-180"
          :max="180"
          :precision="2"
          :step="0.5"
          style="width: 180px"
        />
        <span class="inline-note">
          {{ needsLongitude ? '东经为正、西经为负，用于真太阳时修正' : '仅在「真太阳时」口径下需要' }}
        </span>
      </el-form-item>

      <el-form-item label="流年窗口">
        <el-input-number
          v-model="form.liunian_start_year"
          :min="1800"
          :max="2200"
          :controls="false"
          style="width: 120px"
        />
        <span class="range-dash">起，共</span>
        <el-input-number v-model="form.liunian_years" :min="1" :max="30" :controls="false" style="width: 90px" />
        <span class="range-dash">年</span>
        <span class="inline-note">流年只作展示窗口，不参与四柱；不填起始年则不计算流年</span>
      </el-form-item>

      <el-form-item label="口径" class="form-item-full">
        <ConventionPanel v-model="form.convention" collapsible />
      </el-form-item>

      <el-form-item class="form-item-full">
        <el-button type="primary" :loading="store.loading" @click="onSubmit">开始排盘</el-button>
        <el-button @click="onReset">清空</el-button>
      </el-form-item>
    </el-form>

    <div v-if="result" class="result">
      <div class="result-head">
        <h3>排盘结果</h3>
        <div class="save-row">
          <el-input v-model="saveTitle" placeholder="给这份命盘起个名字（可选）" style="width: 220px" />
          <el-button type="primary" plain :loading="saving" @click="onSave">保存命盘</el-button>
        </div>
      </div>

      <ChartBoard :result="result" />

      <div class="next-step-card">
        <div class="step-icon">解</div>
        <div class="step-body">
          <div class="step-title">下一步：生成带引用的 AI 解读</div>
          <div class="step-desc">
            保存命盘后可在详情页生成报告；报告会先校验引用与干支一致性，不合格会退回额度并标为降级。
          </div>
        </div>
        <el-button class="step-btn" type="primary" plain @click="onSave">保存命盘</el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bazi-page {
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
}

.range-dash {
  margin: 0 6px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.next-step-card {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  border: 1px solid rgba(138, 106, 59, 0.25);
  border-radius: 16px;
  padding: 16px 18px;
  background:
    radial-gradient(600px 160px at 0% 0%, #fffdf6 0%, rgba(255, 253, 246, 0) 70%),
    linear-gradient(135deg, #fdfbf6 0%, #f4f0e6 100%);
}

.step-icon {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #8a6a3b, #c29a5e);
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 20px;
  box-shadow: 0 8px 18px rgba(138, 106, 59, 0.25);
}

.step-body {
  flex: 1;
  min-width: 220px;
}

.step-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 12.5px;
  line-height: 1.8;
  color: var(--xs-text-muted);
}

.step-btn {
  flex: none;
}

@media (max-width: 720px) {
  .inline-note {
    margin-left: 0;
    display: block;
  }
}
</style>
