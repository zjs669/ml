<script setup lang="ts">
/**
 * 单柱选择器：先选天干、再选地支，只列出六十甲子中真实存在的组合。
 * 「不限」是空串而不是 null，避免 el-select 把 null 当成未受控值。
 */
import { computed } from 'vue'

import { BRANCHES, JIAZI, STEMS } from '@/api/reverse'

const props = defineProps<{
  label: string
  /** 当前值，如「庚午」；空串表示不限 */
  modelValue: string
  /** 同盘其他柱已选的干支，用于提示重复（仅提示，不阻断） */
  others?: string[]
}>()

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const stem = computed(() => (props.modelValue ? props.modelValue[0] : ''))
const branch = computed(() => (props.modelValue ? props.modelValue[1] : ''))

/** 当前天干下合法的地支（阴干只配阴支） */
const availableBranches = computed(() => {
  if (!stem.value) return [...BRANCHES]
  const stemIndex = STEMS.indexOf(stem.value as (typeof STEMS)[number])
  return BRANCHES.filter((_, index) => index % 2 === stemIndex % 2)
})

const duplicate = computed(
  () => Boolean(props.modelValue) && (props.others ?? []).includes(props.modelValue),
)

function setStem(value: string): void {
  if (!value) {
    emit('update:modelValue', '')
    return
  }
  // 换了天干要保证地支仍合法，否则自动取第一个合法地支
  const branchIndex = branch.value ? BRANCHES.indexOf(branch.value as (typeof BRANCHES)[number]) : -1
  if (branchIndex >= 0 && branchIndex % 2 === STEMS.indexOf(value as (typeof STEMS)[number]) % 2) {
    emit('update:modelValue', `${value}${branch.value}`)
    return
  }
  const fallback = BRANCHES.find((_, index) => index % 2 === STEMS.indexOf(value as (typeof STEMS)[number]) % 2)
  emit('update:modelValue', fallback ? `${value}${fallback}` : value)
}

function setBranch(value: string): void {
  if (!value) {
    emit('update:modelValue', '')
    return
  }
  if (!stem.value) {
    // 只选地支时，取六十甲子里第一个该地支的组合
    const combo = JIAZI.find((text) => text[1] === value)
    emit('update:modelValue', combo ?? '')
    return
  }
  emit('update:modelValue', `${stem.value}${value}`)
}
</script>

<template>
  <div class="pillar-picker" :class="{ duplicate }">
    <div class="picker-label">
      {{ label }}
      <el-tag v-if="duplicate" size="small" type="warning" effect="plain">与其他柱重复</el-tag>
    </div>
    <div class="picker-row">
      <el-select :model-value="stem" placeholder="天干" clearable style="width: 88px" @update:model-value="setStem">
        <el-option label="不限" value="" />
        <el-option v-for="item in STEMS" :key="item" :label="item" :value="item" />
      </el-select>
      <el-select
        :model-value="branch"
        placeholder="地支"
        clearable
        style="width: 88px"
        @update:model-value="setBranch"
      >
        <el-option label="不限" value="" />
        <el-option v-for="item in availableBranches" :key="item" :label="item" :value="item" />
      </el-select>
      <code class="picker-value">{{ modelValue || '不限' }}</code>
    </div>
  </div>
</template>

<style scoped>
.pillar-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.picker-label {
  font-size: 13px;
  color: var(--xs-text-muted);
  display: flex;
  align-items: center;
  gap: 6px;
}

.picker-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.picker-value {
  font-size: 13px;
  min-width: 36px;
  color: var(--xs-accent);
}

.duplicate .picker-value {
  color: #b88230;
}
</style>
