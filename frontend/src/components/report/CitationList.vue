<script setup lang="ts">
import type { Citation } from '@/api/types'

/** 引用列表：每条都可核对到书名 / 版本 / 章节 / 许可状态，这是"可验证"的落点。 */
defineProps<{
  citations: Citation[]
  /** 模型引用了但服务端未找到的 chunk_id（正常链路上应为空） */
  missing?: number[]
}>()
</script>

<template>
  <div class="citation-list">
    <div class="head">
      <span class="title">引用来源</span>
      <el-tag size="small" effect="plain">{{ citations.length }} 条</el-tag>
    </div>

    <el-empty v-if="!citations.length" description="本次报告未引用知识库片段" :image-size="50" />

    <ol v-else class="items">
      <li
        v-for="item in citations"
        :id="`citation-${item.chunk_id}`"
        :key="item.chunk_id"
        class="citation-item"
      >
        <div class="line">
          <span class="idx">[{{ item.chunk_id }}]</span>
          <span class="label">{{ item.citation_label }}</span>
          <el-tag v-if="item.license_status === 'public_domain'" size="small" type="success" effect="plain">
            公版
          </el-tag>
          <el-tag v-else size="small" type="warning" effect="plain">{{ item.license_status }}</el-tag>
        </div>
        <div v-if="item.location" class="location">{{ item.location }}</div>
        <div class="snippet">{{ item.snippet }}</div>
      </li>
    </ol>

    <div v-if="missing?.length" class="missing">
      以下引用未在知识库中找到，报告可能被降级：{{ missing.map((id) => `[${id}]`).join('、') }}
    </div>
  </div>
</template>

<style scoped>
.citation-list {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.title {
  font-weight: 600;
}

.citation-item {
  border-radius: 10px;
  padding: 6px 8px;
  margin: -6px -8px;
  transition: background 0.4s;
}

/* 由 ReportSections 的 jumpToCitation 临时加上，滚动到位后闪一下再淡出 */
.citation-item.cite-flash {
  background: #fff8e6;
  box-shadow: 0 0 0 2px #f0d9a8 inset;
}

.items {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.idx {
  font-variant-numeric: tabular-nums;
  color: var(--xs-text-muted);
  font-size: 12px;
}

.label {
  font-size: 14px;
}

.location {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-top: 4px;
}

.snippet {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--xs-text);
  background: var(--xs-surface-muted);
  border-radius: 8px;
  padding: 8px 10px;
}

.missing {
  margin-top: 10px;
  font-size: 12px;
  color: #a45f22;
}
</style>
