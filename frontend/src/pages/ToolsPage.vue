<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { DOMAIN_ENTRIES, entriesByGroup, type DomainGroup } from '@/config/domains'

/**
 * 工具页：完整清单 + 说明 + 边界。
 *
 * 数据全部来自 `config/domains.ts`，本文件不再维护第二份清单 ——
 * 之前这里硬编码 19 个对象（约 250 行），与首页、路由表各写一份，
 * 新增域漏改就会出现「工具页有、顶部导航没有」。
 *
 * 导航下拉只给「快速跳转」，这一页负责「说清楚每个域能做什么、边界在哪」。
 */
const router = useRouter()

const buckets = entriesByGroup()

const keyword = ref('')

const filtered = computed(() => {
  const q = keyword.value.trim()
  if (!q) return buckets
  return buckets
    .map((bucket) => ({
      group: bucket.group,
      items: bucket.items.filter(
        (item) => item.label.includes(q) || item.desc.includes(q) || item.note.includes(q),
      ),
    }))
    .filter((bucket) => bucket.items.length > 0)
})

const total = DOMAIN_ENTRIES.length

function enter(path: string): void {
  router.push(path)
}

/** 反查与排局是不同动作，按钮文案分开写，避免「进入排盘」误导。 */
const ACTION_LABEL: Record<string, string> = {
  reverse: '进入反查',
  qimen: '进入排局',
  almanac: '查看黄历',
  tarot: '开始抽牌',
  mbti: '开始作答',
  dream: '开始解梦',
  face: '上传照片',
  palm: '上传照片',
}

function actionLabel(key: string): string {
  return ACTION_LABEL[key] ?? '进入排盘'
}

const groupHint: Record<DomainGroup, string> = {
  命理排盘: '以出生时间（或干支）为输入，输出确定的盘面结构。',
  起局占断: '以起局时刻或起卦方式为输入，输出卦象、局数与盘面。',
  西式与问卷: '非中式的占断体系与倾向问卷，边界与中式域不同，页面内单独说明。',
  视觉分析: '上传图片后由视觉模型做形态描述，不走确定性算法，按次计费。',
}
</script>

<template>
  <div class="tools">
    <div class="page-head">
      <h2>工具</h2>
      <p>
        共 {{ total }} 个入口，全部已跑通验收。每个域只实现一种口径，差异在结果页回显；
        未实现的部分写在页内「已知边界」里，不静默省略。
      </p>
      <el-input v-model="keyword" class="search" placeholder="搜索术数名称或说明" clearable />
    </div>

    <section v-for="bucket in filtered" :key="bucket.group" class="group">
      <div class="group-head">
        <h3>{{ bucket.group }}</h3>
        <span>{{ groupHint[bucket.group] }}</span>
      </div>

      <div class="cards">
        <div v-for="tool in bucket.items" :key="tool.key" class="card">
          <div class="card-head">
            <span class="mark">{{ tool.mark }}</span>
            <span class="name">{{ tool.label }}</span>
            <el-tag v-if="tool.requiresAuth" size="small" type="warning" effect="plain">需登录</el-tag>
            <el-tag v-else size="small" type="success" effect="plain">免登录</el-tag>
          </div>
          <p class="desc">{{ tool.desc }}</p>
          <p class="note">{{ tool.note }}</p>
          <div class="card-foot">
            <el-button size="small" plain @click="enter(tool.path)">
              {{ actionLabel(tool.key) }}
              <span class="arrow">→</span>
            </el-button>
          </div>
        </div>
      </div>
    </section>

    <el-empty v-if="filtered.length === 0" description="没有匹配的术数，换个关键词试试" />
  </div>
</template>

<style scoped>
.tools {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.page-head h2 {
  margin: 0 0 6px;
}

.page-head p {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
  max-width: 760px;
}

.search {
  max-width: 320px;
}

.group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--xs-border);
}

.group-head h3 {
  margin: 0;
  font-size: 15px;
  letter-spacing: 0.5px;
}

.group-head span {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.card {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: #fff;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.card:hover {
  box-shadow: var(--xs-shadow);
  transform: translateY(-1px);
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mark {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 9px;
  background: #f6f1e6;
  color: var(--xs-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-family: 'Songti SC', 'STSong', serif;
  font-size: 16px;
}

.name {
  font-weight: 600;
  font-size: 15px;
  flex: 1;
}

.desc {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.note {
  margin: 0;
  font-size: 12px;
  line-height: 1.75;
  color: var(--xs-text-muted);
  padding-top: 8px;
  border-top: 1px dashed var(--xs-border);
}

.card-foot {
  margin-top: auto;
  padding-top: 10px;
}

.arrow {
  margin-left: 4px;
}

@media (max-width: 1100px) {
  .cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
