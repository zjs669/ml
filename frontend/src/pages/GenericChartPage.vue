<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import * as chartsApi from '@/api/charts'
import type { ChartResult } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import type { DomainFormConfig, FieldDef } from '@/config/domainForms'

/**
 * 通用排盘页：按配置渲染表单，提交到 `/charts/{domain}/calculate`。
 *
 * 为什么需要它：新增的 8 个域表单结构同构（时间/日期/数字/选择/开关 + 文本），
 * 各写一个页面会得到 8 份 90% 相同的代码。既有 4 个域（八字/紫微/六爻/奇门）
 * 有各自的特殊交互，仍保留原页面，不迁到这里。
 */
const props = defineProps<{ config: DomainFormConfig }>()

const router = useRouter()
const auth = useAuthStore()

const formRef = ref()
const result = ref<ChartResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveTitle = ref('')

const values = reactive<Record<string, unknown>>({})

/** 用配置里的默认值初始化；切换域时重置，避免残留上一个域的字段 */
function reset(): void {
  for (const key of Object.keys(values)) delete values[key]
  for (const field of props.config.fields) {
    if (field.default !== undefined) {
      values[field.key] = field.default
    } else if (field.kind === 'switch') {
      values[field.key] = false
    } else {
      values[field.key] = ''
    }
  }
}

reset()
watch(() => props.config.domain, reset)

/** 条件显示：`visibleWhen` 不满足的字段不渲染，也不参与必填校验 */
function visible(field: FieldDef): boolean {
  if (!field.visibleWhen) return true
  return values[field.visibleWhen.key] === field.visibleWhen.equals
}

const visibleFields = computed(() => props.config.fields.filter(visible))

const rules = computed(() => {
  const map: Record<string, Array<Record<string, unknown>>> = {}
  for (const field of visibleFields.value) {
    if (!field.required) continue
    map[field.key] = [
      {
        required: true,
        message: `请填写${field.label}`,
        trigger: field.kind === 'select' || field.kind === 'switch' ? 'change' : 'blur',
      },
    ]
  }
  return map
})

const title = computed(() => props.config.title)
const intro = computed(() => props.config.intro)

async function onSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor(props.config.domain, props.config.build({ ...values }))
    ElMessage.success('计算完成')
  } catch {
    // 统一错误提示已在 axios 拦截器里给出
  } finally {
    loading.value = false
  }
}

async function onSave(interpret: boolean): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存命盘需要先登录')
    router.push({ path: '/login', query: { redirect: `/${props.config.domain}` } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor(
      props.config.domain,
      props.config.build({ ...values }),
      saveTitle.value || props.config.defaultTitle,
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
</script>

<template>
  <div class="generic-page">
    <div class="page-head">
      <h2>{{ title }}</h2>
      <p>{{ intro }}</p>
    </div>

    <el-form ref="formRef" :model="values" :rules="rules" label-width="150px" class="form">
      <template v-for="field in visibleFields" :key="field.key + String(field.visibleWhen?.equals)">
        <el-form-item :label="field.label" :prop="field.key">
          <el-date-picker
            v-if="field.kind === 'datetime'"
            v-model="values[field.key]"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="选择日期与时间"
            style="width: 100%"
          />
          <el-date-picker
            v-else-if="field.kind === 'date'"
            v-model="values[field.key]"
            type="date"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
          />
          <el-input-number
            v-else-if="field.kind === 'number'"
            v-model="values[field.key] as number"
            :min="field.min"
            :max="field.max"
            :step="field.key === 'reversed_probability' ? 0.05 : 1"
            :precision="field.key === 'reversed_probability' ? 2 : 0"
            style="width: 220px"
          />
          <el-select
            v-else-if="field.kind === 'select'"
            v-model="values[field.key]"
            placeholder="请选择"
            style="width: 100%"
          >
            <el-option
              v-for="option in field.options || []"
              :key="String(option.value)"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-switch v-else-if="field.kind === 'switch'" v-model="values[field.key] as boolean" />
          <el-input
            v-else-if="field.kind === 'textarea'"
            v-model="values[field.key] as string"
            type="textarea"
            :rows="4"
            :placeholder="field.placeholder"
          />
          <el-input
            v-else
            v-model="values[field.key] as string"
            :placeholder="field.placeholder"
          />
          <div v-if="field.hint" class="hint">{{ field.hint }}</div>
        </el-form-item>
      </template>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">计算</el-button>
      </el-form-item>
    </el-form>

    <template v-if="result">
      <el-divider content-position="left">盘面</el-divider>
      <ChartBoard :result="result" />

      <el-divider content-position="left">保存与解读</el-divider>
      <div class="save-row">
        <el-input v-model="saveTitle" :placeholder="`标题（默认：${config.defaultTitle}）`" style="max-width: 320px" />
        <el-button :loading="saving" @click="onSave(false)">保存命盘</el-button>
        <el-button type="primary" :loading="saving" @click="onSave(true)">保存并生成解读</el-button>
      </div>

      <el-collapse v-if="result.warnings.length" class="warnings">
        <el-collapse-item :title="`计算提示（${result.warnings.length} 条）`">
          <ul>
            <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
.generic-page {
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

.form {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: var(--xs-surface);
  padding: 20px 22px 4px;
  box-shadow: var(--xs-shadow);
}

.hint {
  width: 100%;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.save-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

.warnings {
  border: none;
}

.warnings ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}
</style>
