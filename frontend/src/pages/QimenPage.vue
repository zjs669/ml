<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import * as chartsApi from '@/api/charts'
import { useAuthStore } from '@/stores/auth'
import type { ChartResult } from '@/api/types'

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

const DAY_BOUNDARY_OPTIONS = [
  { value: 'zi_hour_policy_a', label: '23:00 起算次日（默认）', hint: '日柱与符头随之变化，进而影响局数' },
  { value: 'zi_hour_policy_b', label: '00:00 换日（夜子时）', hint: '时柱取次日日干，日柱不换' },
]

const form = reactive({
  cast_datetime: '2026-01-01T12:00:00',
  timezone: 'Asia/Shanghai',
  day_boundary: 'zi_hour_policy_a',
})

const rules = {
  cast_datetime: [{ required: true, message: '请填写起局时间', trigger: 'change' }],
  timezone: [{ required: true, message: '请选择或填写时区', trigger: 'change' }],
}

function payload(): Record<string, unknown> {
  return {
    cast_datetime: form.cast_datetime,
    timezone: form.timezone,
    convention: { day_boundary: form.day_boundary },
  }
}

async function onSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor('qimen', payload())
    ElMessage.success('排局完成')
  } catch {
    // 统一错误提示已在 axios 拦截器里给出
  } finally {
    loading.value = false
  }
}

async function onSave(interpret: boolean): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存盘面需要先登录')
    router.push({ path: '/login', query: { redirect: '/qimen' } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor('qimen', payload(), saveTitle.value || '奇门局')
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
  form.cast_datetime = '2026-01-01T12:00:00'
  form.timezone = 'Asia/Shanghai'
  form.day_boundary = 'zi_hour_policy_a'
  saveTitle.value = ''
  result.value = null
}
</script>

<template>
  <div class="qimen-page">
    <div class="intro">
      <h2>奇门遁甲</h2>
      <p>
        只需起局时刻，<strong>免登录</strong>即可排盘。本版本只实现<strong>时家转盘拆补法</strong>：
        阴阳遁以二十四节气为界（冬至→芒种阳遁、夏至→大雪阴遁），上中下元按符头（甲日、己日）地支拆补，
        中五宫寄坤二宫、天禽随天芮。置闰法、飞盘奇门与法术奇门不在本版本范围内。
        只出盘面结构与事实，<strong>不取用神、不判旺衰、不择日、不给应期</strong>。
      </p>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="96px" class="form-card">
      <el-form-item label="起局时间" prop="cast_datetime">
        <el-date-picker
          v-model="form.cast_datetime"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          format="YYYY-MM-DD HH:mm"
          placeholder="选择起局的当地钟表时间"
          :clearable="false"
          style="width: 260px"
        />
        <span class="inline-note">决定四柱、节气与符头；局数由这三者共同推出，不可手工指定</span>
      </el-form-item>

      <el-form-item label="时区">
        <el-select v-model="form.timezone" filterable allow-create default-first-option style="width: 200px">
          <el-option v-for="tz in TIMEZONES" :key="tz" :label="tz" :value="tz" />
        </el-select>
      </el-form-item>

      <el-form-item label="换日口径">
        <el-radio-group v-model="form.day_boundary">
          <el-radio v-for="item in DAY_BOUNDARY_OPTIONS" :key="item.value" :value="item.value">
            {{ item.label }}
          </el-radio>
        </el-radio-group>
        <span class="inline-note">
          23:00 前后起局时，两套口径得到的日柱、符头与局数可能不同，结果页会回显本次所用口径
        </span>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">开始排局</el-button>
        <el-button @click="onReset">清空</el-button>
      </el-form-item>
    </el-form>

    <div v-if="result" class="result">
      <div class="result-head">
        <h3>局盘</h3>
        <div class="save-row">
          <el-input v-model="saveTitle" placeholder="给这局起个名字（可选）" style="width: 220px" />
          <el-button plain :loading="saving" @click="onSave(false)">保存盘面</el-button>
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
        description="解读只复述局数、九宫星门神、旬空与马星等盘面事实，不取用神、不作吉凶推断、不择日、不给应期。"
      />
    </div>
  </div>
</template>

<style scoped>
.qimen-page {
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
