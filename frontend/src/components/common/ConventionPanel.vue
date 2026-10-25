<script setup lang="ts">
import { computed } from 'vue'

import type { Convention } from '@/api/types'

/**
 * 口径面板：四项可选 + 一项锁定。每一项都不是"隐式默认"，
 * 用户选了就随命盘存档、并出现在报告与导出文本里。
 */
const props = defineProps<{
  modelValue: Partial<Convention>
  /** 折叠态（表单里默认收起，避免干扰主流程） */
  collapsible?: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [Partial<Convention>] }>()

interface Option {
  value: string
  label: string
  note: string
}

const YEAR_BOUNDARY: Option[] = [
  { value: 'lichun', label: '立春交节时刻', note: '年柱在立春交节那一分钟切换，主流口径' },
  { value: 'lichun_day', label: '立春当日 00:00', note: '立春当天整日归入新年，需注意交节时刻前的时段' },
]

const DAY_BOUNDARY: Option[] = [
  { value: 'zi_hour_policy_a', label: '23:00 换日', note: '23:00 起算次日，子时整体归属次日' },
  { value: 'zi_hour_policy_b', label: '00:00 换日', note: '23:00-23:59 为夜子时，日柱仍取当天' },
]

const SOLAR_TIME: Option[] = [
  { value: 'none', label: '不修正（钟表时间）', note: '直接使用当地标准时间' },
  { value: 'true_solar_time', label: '真太阳时', note: '按经度差 + 均时差修正，必须填写经度' },
]

const SCHOOL: Option[] = [
  { value: 'default_v1', label: '通用流派（default_v1）', note: '首版唯一开放的流派标识' },
]

const current = computed(() => ({
  year_boundary: props.modelValue.year_boundary ?? 'lichun',
  day_boundary: props.modelValue.day_boundary ?? 'zi_hour_policy_a',
  solar_time: props.modelValue.solar_time ?? 'none',
  school: props.modelValue.school ?? 'default_v1',
}))

function patch(key: keyof Convention, value: string): void {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

/** 用工厂函数生成事件处理器，避免模板里的内联回调触发隐式 any。 */
function pick(key: keyof Convention): (value: unknown) => void {
  return (value) => patch(key, String(value))
}

const isDefault = computed(
  () =>
    current.value.year_boundary === 'lichun' &&
    current.value.day_boundary === 'zi_hour_policy_a' &&
    current.value.solar_time === 'none',
)
</script>

<template>
  <el-collapse v-if="collapsible" class="convention-panel">
    <el-collapse-item name="convention">
      <template #title>
        <span class="collapse-title">
          高级口径
          <el-tag v-if="!isDefault" size="small" type="warning" effect="plain">已改动非默认口径</el-tag>
        </span>
      </template>
      <div class="fields">
        <div class="field">
          <div class="field-label">年柱边界</div>
          <el-radio-group
            :model-value="current.year_boundary"
            @update:model-value="pick('year_boundary')"
          >
            <el-radio v-for="opt in YEAR_BOUNDARY" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
          <div class="field-note">{{ YEAR_BOUNDARY.find((o) => o.value === current.year_boundary)?.note }}</div>
        </div>

        <div class="field">
          <div class="field-label">换日规则</div>
          <el-radio-group
            :model-value="current.day_boundary"
            @update:model-value="pick('day_boundary')"
          >
            <el-radio v-for="opt in DAY_BOUNDARY" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
          <div class="field-note">{{ DAY_BOUNDARY.find((o) => o.value === current.day_boundary)?.note }}</div>
        </div>

        <div class="field">
          <div class="field-label">时间修正</div>
          <el-radio-group
            :model-value="current.solar_time"
            @update:model-value="pick('solar_time')"
          >
            <el-radio v-for="opt in SOLAR_TIME" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
          <div class="field-note">{{ SOLAR_TIME.find((o) => o.value === current.solar_time)?.note }}</div>
        </div>

        <div class="field">
          <div class="field-label">流派</div>
          <el-radio-group :model-value="current.school" @update:model-value="pick('school')">
            <el-radio v-for="opt in SCHOOL" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
          </el-radio-group>
          <div class="field-note">五行权重固定为 weight-v1（本气 1.0 / 中气 0.5 / 余气 0.3），不可选。</div>
        </div>
      </div>
    </el-collapse-item>
  </el-collapse>

  <div v-else class="convention-panel inline">
    <div class="fields">
      <div class="field">
        <div class="field-label">年柱边界</div>
        <el-select
          :model-value="current.year_boundary"
          @update:model-value="pick('year_boundary')"
        >
          <el-option v-for="opt in YEAR_BOUNDARY" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
      <div class="field">
        <div class="field-label">换日规则</div>
        <el-select
          :model-value="current.day_boundary"
          @update:model-value="pick('day_boundary')"
        >
          <el-option v-for="opt in DAY_BOUNDARY" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
      <div class="field">
        <div class="field-label">时间修正</div>
        <el-select :model-value="current.solar_time" @update:model-value="pick('solar_time')">
          <el-option v-for="opt in SOLAR_TIME" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
      <div class="field">
        <div class="field-label">流派</div>
        <el-select :model-value="current.school" @update:model-value="pick('school')">
          <el-option v-for="opt in SCHOOL" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </div>
    </div>
  </div>
</template>

<style scoped>
.convention-panel {
  margin-top: 8px;
}

.collapse-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px 20px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  color: var(--xs-text-muted);
}

.field-note {
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.6;
}

.inline .field-note {
  display: none;
}

:deep(.el-radio) {
  margin-right: 12px;
}
</style>
