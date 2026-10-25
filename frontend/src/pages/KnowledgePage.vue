<script setup lang="ts">
import { onMounted, ref } from 'vue'

import * as knowledgeApi from '@/api/knowledge'
import type { KnowledgeChunkDetail, KnowledgeHit } from '@/api/types'

const query = ref('')
const items = ref<KnowledgeHit[]>([])
const loading = ref(false)
const searched = ref(false)
const approvedCount = ref<number | null>(null)

const drawer = ref(false)
const detail = ref<KnowledgeChunkDetail | null>(null)
const detailLoading = ref(false)

/** 首屏术语入口：点一下就检索，降低"不知道搜什么"的门槛。 */
const SUGGESTIONS = ['六合', '三合', '相冲', '藏干', '十神', '相刑', '相害', '大运', '立春', '真太阳时']

async function search(keyword?: string): Promise<void> {
  const q = (keyword ?? query.value).trim()
  if (!q) return
  query.value = q
  loading.value = true
  searched.value = true
  try {
    const data = await knowledgeApi.searchKnowledge(q)
    items.value = data.items
  } finally {
    loading.value = false
  }
}

async function openChunk(id: number): Promise<void> {
  drawer.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await knowledgeApi.getChunk(id)
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  try {
    const stats = await knowledgeApi.knowledgeStats()
    approvedCount.value = typeof stats.approved_chunks === 'number' ? stats.approved_chunks : null
  } catch {
    approvedCount.value = null
  }
})
</script>

<template>
  <div class="knowledge">
    <div class="page-head">
      <h2>知识库</h2>
      <p>
        只检索<strong>已审核</strong>的条目，每条都登记书名、版本、章节与许可状态。
        <span v-if="approvedCount !== null">当前可用片段 {{ approvedCount }} 条。</span>
        检索无命中时，报告会明确写「知识库依据不足」，不允许模型自行补全。
      </p>
    </div>

    <div class="search-bar">
      <el-input
        v-model="query"
        placeholder="搜索术语，如：六合、藏干、相冲"
        clearable
        @keyup.enter="search()"
      >
        <template #append>
          <el-button :loading="loading" @click="search()">搜索</el-button>
        </template>
      </el-input>
    </div>

    <div class="suggestions">
      <span class="sug-label">试试：</span>
      <el-button v-for="word in SUGGESTIONS" :key="word" size="small" text @click="search(word)">{{ word }}</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="4" animated />

    <template v-else>
      <el-empty
        v-if="searched && !items.length"
        description="没有匹配的已审核条目。可以换个说法，或等待知识库补充。"
        :image-size="70"
      />

      <div v-else class="results">
        <div v-for="item in items" :key="item.chunk_id" class="hit" @click="openChunk(item.chunk_id)">
          <div class="hit-head">
            <span class="hit-title">{{ item.title }}</span>
            <el-tag size="small" effect="plain">{{ item.topic }}</el-tag>
            <el-tag v-if="item.license_status === 'public_domain'" size="small" type="success" effect="plain">
              公版
            </el-tag>
            <el-tag v-else size="small" type="warning" effect="plain">{{ item.license_status }}</el-tag>
            <span class="score">相关度 {{ item.score.toFixed(2) }}</span>
          </div>
          <div v-if="item.location" class="hit-location">{{ item.citation_label }} · {{ item.location }}</div>
          <div v-else class="hit-location">{{ item.citation_label }}</div>
          <div class="hit-snippet">{{ item.snippet }}</div>
        </div>
      </div>
    </template>

    <el-drawer v-model="drawer" title="出处详情" size="480px">
      <el-skeleton v-if="detailLoading" :rows="5" animated />
      <template v-else-if="detail">
        <div class="drawer-title">{{ detail.title }}</div>
        <div class="drawer-meta">
          <div><span class="k">出处</span><span>{{ detail.citation_label }}</span></div>
          <div><span class="k">章节</span><span>{{ detail.location || '—' }}</span></div>
          <div><span class="k">书名</span><span>{{ detail.source.title || '—' }}</span></div>
          <div><span class="k">作者</span><span>{{ detail.source.author || '—' }}</span></div>
          <div><span class="k">版本</span><span>{{ detail.source.edition || '—' }}</span></div>
          <div><span class="k">许可</span><span>{{ detail.license_status }}</span></div>
          <div><span class="k">审核</span><span>{{ detail.approval_status }}</span></div>
          <div><span class="k">内容指纹</span><code>{{ detail.content_hash }}</code></div>
        </div>
        <div class="drawer-content">{{ detail.content }}</div>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.knowledge {
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
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.search-bar {
  max-width: 620px;
}

.suggestions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hit {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.2s ease;
}

.hit:hover {
  border-color: var(--xs-accent);
}

.hit-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hit-title {
  font-weight: 600;
}

.score {
  margin-left: auto;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.hit-location {
  margin-top: 6px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.hit-snippet {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text);
}

.drawer-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 10px;
}

.drawer-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  border-bottom: 1px dashed var(--xs-border);
  padding-bottom: 12px;
  margin-bottom: 12px;
}

.drawer-meta .k {
  display: inline-block;
  width: 72px;
  color: var(--xs-text-muted);
}

.drawer-meta code {
  font-size: 11px;
  word-break: break-all;
}

.drawer-content {
  font-size: 14px;
  line-height: 2;
  white-space: pre-wrap;
}
</style>
