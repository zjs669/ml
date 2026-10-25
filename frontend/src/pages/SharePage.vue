<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import { previewShare } from '@/api/charts'
import type { ChartResult, SharePreview } from '@/api/types'

const route = useRoute()
const router = useRouter()

const token = computed(() => String(route.params.token ?? ''))
const preview = ref<SharePreview | null>(null)
const loading = ref(true)
const error = ref('')

/** 分享页只拿到脱敏后的盘面，拼成 ChartBoard 需要的统一外壳。 */
const asResult = computed<ChartResult | null>(() => {
  if (!preview.value) return null
  return {
    domain: preview.value.domain,
    algorithm_version: preview.value.algorithm_version,
    input_summary: {},
    convention: preview.value.convention,
    chart_facts: preview.value.chart_facts,
    triggered_rules: preview.value.triggered_rules,
    warnings: preview.value.warnings,
    source_refs: [],
  }
})

onMounted(async () => {
  try {
    preview.value = await previewShare(token.value)
  } catch {
    error.value = '链接已过期、已被撤销，或不存在。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="share-page">
    <el-skeleton v-if="loading" :rows="6" animated />

    <el-result v-else-if="error" icon="warning" title="无法打开该分享" :sub-title="error">
      <template #extra>
        <el-button type="primary" @click="router.push('/bazi')">自己排一盘</el-button>
      </template>
    </el-result>

    <template v-else-if="preview && asResult">
      <div class="head">
        <h2>{{ preview.title || '分享的命盘' }}</h2>
        <div class="meta">
          <el-tag size="small" effect="plain">{{ preview.domain }}</el-tag>
          <el-tag size="small" effect="plain">四柱 {{ preview.pillars_text }}</el-tag>
          <span class="expire">链接有效期至 {{ preview.expires_at.slice(0, 19) }}</span>
        </div>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="这是脱敏分享"
        description="分享页不包含账号信息、笔记与已生成的报告正文；盘面由确定性引擎计算，属于传统文化研习内容。"
      />

      <ChartBoard :result="asResult" />

      <div class="foot">
        想看带引用的 AI 解读，可以自己排一盘：
        <el-button type="primary" link @click="router.push('/bazi')">进入排盘</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.share-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.head h2 {
  margin: 0 0 8px;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.foot {
  border-top: 1px dashed var(--xs-border);
  padding-top: 12px;
  font-size: 13px;
  color: var(--xs-text-muted);
}
</style>
