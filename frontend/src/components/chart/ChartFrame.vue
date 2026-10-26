<script setup lang="ts">
import ChartBoard from './ChartBoard.vue'
import type { ChartResult } from '@/api/types'

/**
 * 盘面外壳：标题栏 + 盘面 + 保存行 + 计算提示。
 *
 * 原先这段结构在 6 个页面里各写一遍（BaziPage / ZiweiPage / LiuyaoPage /
 * QimenPage / GenericChartPage 的结果区，以及 ReversePage 的对照区），
 * 差异只在「保存按钮文案」和「下一步提示」。
 *
 * 注意：本组件只统一**外壳**，不碰各域表单 —— 5 个旧页面的表单各有特殊交互
 * （反查、手填六爻、流派面板），强行统一会把简单页面变复杂。
 */
const props = withDefaults(
  defineProps<{
    result: ChartResult
    title?: string
    /** 是否显示保存行；反查页这类只出结果的场景可关掉 */
    showSave?: boolean
    saving?: boolean
    /** 保存按钮文案，各域不同（「保存命盘」/「保存并生成解读」） */
    saveText?: string
    /** 有解读按钮时，主按钮文案 */
    interpretText?: string
    /** 关闭时折叠计算提示 */
    showWarnings?: boolean
    /** 标题输入框占位，各域可带上自己的默认标题 */
    titlePlaceholder?: string
  }>(),
  {
    title: '盘面',
    showSave: true,
    saving: false,
    saveText: '保存命盘',
    interpretText: '',
    showWarnings: true,
    titlePlaceholder: '给这份命盘起个名字（可选）',
  },
)

const emit = defineEmits<{
  save: []
  interpret: []
}>()

const saveTitle = defineModel<string>('saveTitle', { default: '' })
</script>

<template>
  <section class="chart-frame">
    <div class="frame-head">
      <h3>{{ title }}</h3>
      <div v-if="showSave" class="save-row">
        <el-input v-model="saveTitle" :placeholder="titlePlaceholder" style="width: 220px" />
        <el-button :loading="saving" @click="emit('save')">{{ saveText }}</el-button>
        <el-button v-if="interpretText" type="primary" :loading="saving" @click="emit('interpret')">
          {{ interpretText }}
        </el-button>
      </div>
    </div>

    <ChartBoard :result="props.result" />

    <el-collapse v-if="showWarnings && props.result.warnings.length" class="warnings">
      <el-collapse-item :title="`计算提示（${props.result.warnings.length} 条）`">
        <ul>
          <li v-for="(item, index) in props.result.warnings" :key="index">{{ item }}</li>
        </ul>
      </el-collapse-item>
    </el-collapse>

    <slot />
  </section>
</template>

<style scoped>
.chart-frame {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.frame-head {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--xs-border);
}

.frame-head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.5px;
}

.save-row {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.warnings ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}
</style>
