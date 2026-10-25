<script setup lang="ts">
import { computed } from 'vue'

import CitationList from './CitationList.vue'
import UncertaintyBox from './UncertaintyBox.vue'
import type { Citation, ReportPayload } from '@/api/types'

/**
 * 报告渲染强制分三块视觉区隔：【盘面事实】【传统解释】【现实建议】。
 * 再叠加引用列表与不确定项，使「哪部分是事实、哪部分是解释、哪部分是建议」在 UI 层可验证。
 */
const props = defineProps<{
  report: ReportPayload
  citations: Citation[]
  status?: string
}>()

const citationMap = computed(() => {
  const map = new Map<number, Citation>()
  for (const item of props.citations) map.set(item.chunk_id, item)
  return map
})

function citationLabel(ids: number[]): string[] {
  return ids
    .map((id) => {
      const hit = citationMap.value.get(id)
      return hit ? `[${id}] ${hit.citation_label}` : `[${id}]（引用缺失）`
    })
    .filter(Boolean)
}

const missingCitations = computed(() =>
  props.report.citations.filter((id) => !citationMap.value.has(id)),
)
</script>

<template>
  <div class="report-sections">
    <el-alert
      v-if="status === 'degraded'"
      class="degraded"
      type="warning"
      :closable="false"
      show-icon
      title="本报告为降级模板"
      description="模型输出未通过服务端校验，以下内容由规则模板生成，未经过模型改写。知识库依据可能不足。"
    />

    <section class="block block-summary">
      <div class="block-tag">摘要</div>
      <p class="summary">{{ report.summary }}</p>
    </section>

    <section class="block block-fact">
      <div class="block-tag">盘面事实</div>
      <p class="block-hint">以下内容直接来自确定性排盘引擎，模型无权修改。</p>
      <el-empty v-if="!report.observations.length" description="本盘未产出可陈述的观测项" :image-size="50" />
      <ul v-else class="facts">
        <li v-for="(item, index) in report.observations" :key="index">
          <span class="fact-text">{{ item.fact }}</span>
          <span class="fact-meta">
            <template v-if="item.rule_ids.length">
              <code v-for="rid in item.rule_ids" :key="rid" class="rule-id">{{ rid }}</code>
            </template>
            <template v-if="item.citation_ids.length">
              <span v-for="label in citationLabel(item.citation_ids)" :key="label" class="cite">{{ label }}</span>
            </template>
          </span>
        </li>
      </ul>
    </section>

    <section class="block block-interp">
      <div class="block-tag">传统解释</div>
      <p class="block-hint">传统术数体系内的既有说法，属于文化解释，不是对现实的预测。</p>
      <el-empty
        v-if="!report.traditional_interpretations.length"
        description="知识库依据不足，本次不提供传统解释"
        :image-size="50"
      />
      <ul v-else class="interps">
        <li v-for="(item, index) in report.traditional_interpretations" :key="index">
          <div class="claim">{{ item.claim }}</div>
          <div v-if="item.school_note" class="school-note">流派差异：{{ item.school_note }}</div>
          <div class="fact-meta">
            <span v-for="label in citationLabel(item.citation_ids)" :key="label" class="cite">{{ label }}</span>
          </div>
        </li>
      </ul>
    </section>

    <section class="block block-advice">
      <div class="block-tag">现实建议</div>
      <p class="block-hint">以下是可以自行取舍的反思方向，不构成任何决策指令。</p>
      <el-empty v-if="!report.practical_reflections.length" description="本次未给出建议" :image-size="50" />
      <ul v-else class="advice">
        <li v-for="(item, index) in report.practical_reflections" :key="index">{{ item }}</li>
      </ul>
    </section>

    <UncertaintyBox :items="report.uncertainties" />

    <CitationList :citations="citations" :missing="missingCitations" />

    <div class="safety">
      <span class="safety-label">安全声明</span>
      <span>{{ report.safety_note }}</span>
    </div>
  </div>
</template>

<style scoped>
.report-sections {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.degraded {
  margin-bottom: 4px;
}

.block {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
}

.block-summary {
  background: var(--xs-surface-muted);
}

.block-fact {
  border-left: 4px solid #4c7fbf;
}

.block-interp {
  border-left: 4px solid #a8763f;
}

.block-advice {
  border-left: 4px solid #4c9a6d;
}

.block-tag {
  display: inline-block;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 2px;
  color: var(--xs-text-muted);
  margin-bottom: 8px;
}

.block-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.summary {
  margin: 0;
  line-height: 1.9;
}

.facts,
.interps,
.advice {
  margin: 0;
  padding-left: 18px;
  line-height: 1.9;
  font-size: 14px;
}

.interps,
.advice {
  list-style: none;
  padding-left: 0;
}

.interps li + li,
.advice li + li {
  margin-top: 10px;
}

.claim {
  font-size: 14px;
}

.school-note {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-top: 4px;
}

.fact-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.rule-id,
.cite {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--xs-surface-muted);
  color: var(--xs-text-muted);
}

.safety {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.safety-label {
  flex: 0 0 auto;
  font-weight: 600;
}
</style>
