<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import * as chartsApi from '@/api/charts'
import type { ChartResult } from '@/api/types'
import { useAuthStore } from '@/stores/auth'

/**
 * 关系合盘页。
 *
 * 两种输入来源：出生时间（由后端排盘）或已保存的四柱盘 id。
 * 「直接填四柱」这一路刻意不做前端表单 —— 手工干支最容易因年界/日界口径不同而出错，
 * 后端会为它打上「未经验证」的提示，前端不该鼓励这种用法。
 */
const router = useRouter()
const auth = useAuthStore()

const formRef = ref()
const result = ref<ChartResult | null>(null)
const loading = ref(false)
const saving = ref(false)
const saveTitle = ref('')

type SideForm = {
  label: string
  source: 'birth' | 'chart'
  birth_datetime: string
  timezone: string
  gender: 'male' | 'female' | 'unknown'
  chart_id: number | null
}

const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Tokyo',
  'Europe/London',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
].map((value) => ({ value, label: value }))

const left = reactive<SideForm>({
  label: '甲方',
  source: 'birth',
  birth_datetime: '1990-05-20T12:00:00',
  timezone: 'Asia/Shanghai',
  gender: 'unknown',
  chart_id: null,
})

const right = reactive<SideForm>({
  label: '乙方',
  source: 'birth',
  birth_datetime: '1992-08-15T12:00:00',
  timezone: 'Asia/Shanghai',
  gender: 'unknown',
  chart_id: null,
})

const relationType = ref<'couple' | 'business' | 'parent_child'>('couple')
const scope = ref<'all' | 'day_only'>('all')

const rules = {
  'left.birth_datetime': [{ required: true, message: '请填写甲方出生时间', trigger: 'change' }],
  'right.birth_datetime': [{ required: true, message: '请填写乙方出生时间', trigger: 'change' }],
}

function buildSide(side: SideForm): Record<string, unknown> {
  if (side.source === 'chart') {
    return { label: side.label, chart_id: Number(side.chart_id) }
  }
  return {
    label: side.label,
    birth_datetime: side.birth_datetime,
    timezone: side.timezone,
    gender: side.gender,
  }
}

function payload(): Record<string, unknown> {
  return {
    left: buildSide(left),
    right: buildSide(right),
    relation_type: relationType.value,
    convention: { scope: scope.value },
  }
}

async function onSubmit(): Promise<void> {
  if (left.source === 'chart' && !left.chart_id) {
    ElMessage.warning('请填写甲方的命盘 id')
    return
  }
  if (right.source === 'chart' && !right.chart_id) {
    ElMessage.warning('请填写乙方的命盘 id')
    return
  }
  loading.value = true
  try {
    result.value = await chartsApi.calculateFor('hepan', payload())
    ElMessage.success('合盘完成')
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('保存合盘需要先登录')
    router.push({ path: '/login', query: { redirect: '/hepan' } })
    return
  }
  saving.value = true
  try {
    const chart = await chartsApi.saveChartFor('hepan', payload(), saveTitle.value || '关系合盘')
    ElMessage.success('已保存到「我的命盘」')
    router.push(`/charts/${chart.id}`)
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

const facts = () => (result.value?.chart_facts ?? {}) as Record<string, unknown>
const crossRelations = () => (facts().cross_chart_relations ?? []) as Array<Record<string, unknown>>
const internalRelations = () => (facts().internal_relations ?? []) as Array<Record<string, unknown>>
const summary = () => (facts().summary ?? {}) as Record<string, number>
</script>

<template>
  <div class="hepan">
    <div class="page-head">
      <h2>关系合盘</h2>
      <p>
        把两张四柱盘拼到一起，复用单盘的 66 条关系规则判定干支交互。
        只列触发的规则，不判断关系好坏、不预测走向。
      </p>
    </div>

    <el-form ref="formRef" :model="{ left, right }" :rules="rules" label-width="130px" class="form">
      <div class="sides">
        <div v-for="side in [left, right]" :key="side.label" class="side">
          <el-form-item label="标签">
            <el-input v-model="side.label" maxlength="20" />
          </el-form-item>
          <el-form-item label="输入来源">
            <el-radio-group v-model="side.source">
              <el-radio-button value="birth">出生时间</el-radio-button>
              <el-radio-button value="chart">已保存命盘 id</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <template v-if="side.source === 'birth'">
            <el-form-item :prop="`${side === left ? 'left' : 'right'}.birth_datetime`" label="出生时间">
              <el-date-picker
                v-model="side.birth_datetime"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="时区">
              <el-select v-model="side.timezone" style="width: 100%">
                <el-option v-for="item in TIMEZONES" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="性别">
              <el-select v-model="side.gender" style="width: 100%">
                <el-option label="男" value="male" />
                <el-option label="女" value="female" />
                <el-option label="未知" value="unknown" />
              </el-select>
            </el-form-item>
          </template>
          <el-form-item v-else label="命盘 id">
            <el-input-number v-model="side.chart_id" :min="1" style="width: 200px" />
            <div class="hint">只能填自己的四柱盘 id；口径与算法版本随盘存档。</div>
          </el-form-item>
        </div>
      </div>

      <el-form-item label="关系类型">
        <el-radio-group v-model="relationType">
          <el-radio-button value="couple">情侣</el-radio-button>
          <el-radio-button value="business">商业</el-radio-button>
          <el-radio-button value="parent_child">亲子</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="比较范围">
        <el-radio-group v-model="scope">
          <el-radio-button value="all">全部四柱两两比较</el-radio-button>
          <el-radio-button value="day_only">只比日柱</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">计算合盘</el-button>
      </el-form-item>
    </el-form>

    <template v-if="result">
      <el-divider content-position="left">合盘结果</el-divider>

      <div class="counts">
        <span>跨盘关系：{{ summary().cross_count ?? 0 }}</span>
        <span>盘内关系：{{ summary().internal_count ?? 0 }}</span>
        <span>甲方盘内：{{ summary().left_count ?? 0 }}</span>
        <span>乙方盘内：{{ summary().right_count ?? 0 }}</span>
      </div>

      <ChartBoard :result="result" :show-relations="false" />

      <el-divider content-position="left">跨盘关系</el-divider>
      <ul v-if="crossRelations().length" class="relations">
        <li v-for="(item, index) in crossRelations()" :key="index">
          <strong>{{ item.relation }}</strong>
          <span class="rule-id">{{ item.rule_id }}</span>
          <span class="positions">
            <span v-for="(detail, i) in (item.positions_detail as Array<Record<string, unknown>>)" :key="i">
              {{ detail.side === 'left' ? left.label : right.label }}·{{ detail.pillar_label }}
            </span>
          </span>
        </li>
      </ul>
      <p v-else class="empty">双方干支之间没有触发跨盘关系规则。</p>

      <el-divider content-position="left">盘内关系</el-divider>
      <ul v-if="internalRelations().length" class="relations">
        <li v-for="(item, index) in internalRelations()" :key="index">
          <strong>{{ item.relation }}</strong>
          <span class="rule-id">{{ item.rule_id }}</span>
          <span class="positions">
            <span v-for="(detail, i) in (item.positions_detail as Array<Record<string, unknown>>)" :key="i">
              {{ detail.side === 'left' ? left.label : right.label }}·{{ detail.pillar_label }}
            </span>
          </span>
        </li>
      </ul>
      <p v-else class="empty">双方盘内都没有触发关系规则。</p>

      <div class="save-row">
        <el-input v-model="saveTitle" placeholder="标题（默认：关系合盘）" style="max-width: 320px" />
        <el-button :loading="saving" @click="onSave">保存合盘</el-button>
      </div>

      <el-collapse v-if="result.warnings.length">
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
.hepan {
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

.sides {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.side {
  border: 1px dashed var(--xs-border);
  border-radius: 12px;
  padding: 12px 14px 0;
}

.hint {
  width: 100%;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.counts {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.relations {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
}

.rule-id {
  margin-left: 8px;
  font-size: 11px;
  color: var(--xs-text-muted);
  font-family: 'SFMono-Regular', Consolas, monospace;
}

.positions {
  margin-left: 10px;
  display: inline-flex;
  gap: 8px;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.empty {
  margin: 0;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.save-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}
</style>
