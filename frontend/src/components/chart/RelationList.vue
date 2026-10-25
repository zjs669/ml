<script setup lang="ts">
import { computed } from 'vue'

import type { ConflictItem, IncompleteRelation, Position, TriggeredRule } from '@/api/types'

const props = defineProps<{
  rules: TriggeredRule[]
  incomplete?: IncompleteRelation[]
  conflicts?: ConflictItem[]
}>()

const POSITION_LABEL: Record<Position, string> = {
  year: '年',
  month: '月',
  day: '日',
  hour: '时',
}

const grouped = computed(() => {
  const buckets = new Map<string, TriggeredRule[]>()
  for (const rule of props.rules) {
    const list = buckets.get(rule.relation) ?? []
    list.push(rule)
    buckets.set(rule.relation, list)
  }
  return [...buckets.entries()].map(([relation, items]) => ({ relation, items }))
})

function positionsText(positions: Position[]): string {
  return positions.map((item) => `${POSITION_LABEL[item]}柱`).join('、')
}
</script>

<template>
  <div class="relation-list">
    <div class="head">
      <span class="title">刑冲合害</span>
      <el-tag size="small" effect="plain">{{ rules.length }} 条已触发</el-tag>
    </div>
    <p class="hint">
      以下只列出「哪些规则被触发、由哪些位置触发」，不含吉凶判断；点击可展开规则来源与版本。
    </p>

    <el-empty v-if="!rules.length" description="本盘未触发任何已登记的关系规则" :image-size="60" />

    <div v-for="group in grouped" :key="group.relation" class="group">
      <div class="group-title">{{ group.relation }}</div>
      <el-collapse>
        <el-collapse-item
          v-for="rule in group.items"
          :key="rule.rule_id + rule.positions.join('-')"
          :name="rule.rule_id + rule.positions.join('-')"
        >
          <template #title>
            <div class="rule-line">
              <span class="label">{{ rule.label }}</span>
              <span class="positions">{{ positionsText(rule.positions) }}</span>
            </div>
          </template>
          <div class="rule-detail">
            <div><span class="k">rule_id</span><code>{{ rule.rule_id }}</code></div>
            <div><span class="k">规则版本</span><span>{{ rule.version }}</span></div>
            <div><span class="k">来源</span><code>{{ rule.source_ref }}</code></div>
            <div><span class="k">说明</span><span>{{ rule.note }}</span></div>
            <div v-if="rule.duplicated_branches && Object.keys(rule.duplicated_branches).length">
              <span class="k">同支并见</span>
              <span>
                <span v-for="(pos, branch) in rule.duplicated_branches" :key="branch" class="dup">
                  {{ branch }}：{{ pos.map((p) => POSITION_LABEL[p]).join('、') }}
                </span>
              </span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div v-if="conflicts?.length" class="extra">
      <div class="extra-title">并列提示</div>
      <ul>
        <li v-for="(item, index) in conflicts" :key="index">
          {{ item.type }}（{{ item.relations.join('、') }}）：{{ item.note }}
        </li>
      </ul>
    </div>

    <div v-if="incomplete?.length" class="extra">
      <div class="extra-title">缺一提示（不构成完整关系）</div>
      <ul>
        <li v-for="(item, index) in incomplete" :key="index">
          {{ item.relation }}：缺 {{ item.rule_id }} 的完整组合，已现 {{ item.members_present.join('') }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.relation-list {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 14px 16px;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  font-weight: 600;
}

.hint {
  margin: 8px 0 12px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.group + .group {
  margin-top: 12px;
}

.group-title {
  font-size: 13px;
  color: var(--xs-accent);
  margin-bottom: 4px;
}

.rule-line {
  display: flex;
  gap: 10px;
  align-items: baseline;
}

.label {
  font-weight: 500;
}

.positions {
  font-size: 12px;
  color: var(--xs-text-muted);
}

.rule-detail {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: var(--xs-text);
}

.rule-detail .k {
  display: inline-block;
  width: 72px;
  color: var(--xs-text-muted);
}

.dup {
  margin-right: 10px;
}

.extra {
  margin-top: 14px;
  font-size: 13px;
}

.extra-title {
  color: var(--xs-text-muted);
  margin-bottom: 6px;
}

.extra ul {
  margin: 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
