<script setup lang="ts">
/**
 * 四柱反查：已知干支 → 反推公历日期。
 *
 * 与排盘严格互逆：反查窗口由后端按时辰 + 换日口径 + 真太阳时算出，
 * 页面只负责展示与「一键带入既有报告管线」，不复刻任何历法逻辑。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import ChartBoard from '@/components/chart/ChartBoard.vue'
import PillarPicker from '@/components/chart/PillarPicker.vue'
import ConventionPanel from '@/components/common/ConventionPanel.vue'
import * as chartsApi from '@/api/charts'
import * as reverseApi from '@/api/reverse'
import { useAuthStore } from '@/stores/auth'
import type { BaziFormInput, ChartResult, ReverseCandidate, ReverseSearchOut } from '@/api/types'

const router = useRouter()
const auth = useAuthStore()

const TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Taipei',
  'Asia/Tokyo',
  'Europe/London',
  'America/New_York',
  'America/Los_Angeles',
  'UTC',
]

const form = reactive({
  year: '',
  month: '',
  day: '',
  hour: '',
  range: ['1980-01-01', '2010-12-31'] as [string, string],
  timezone: 'Asia/Shanghai',
  longitude: null as number | null,
  convention: {
    year_boundary: 'lichun',
    day_boundary: 'zi_hour_policy_a',
    solar_time: 'none',
    school: 'default_v1',
  } as BaziFormInput['convention'],
  limit: 50,
})

const loading = ref(false)
const result = ref<ReverseSearchOut | null>(null)
const offset = ref(0)

const needsLongitude = computed(() => form.convention.solar_time === 'true_solar_time')

const filledCount = computed(
  () => [form.year, form.month, form.day, form.hour].filter((item) => item).length,
)

const others = (key: 'year' | 'month' | 'day' | 'hour'): string[] =>
  (['year', 'month', 'day', 'hour'] as const).filter((item) => item !== key).map((item) => form[item]).filter(Boolean)

const pageFrom = computed(() => (result.value ? offset.value + 1 : 0))
const pageTo = computed(() =>
  result.value ? offset.value + result.value.candidates.length : 0,
)

onMounted(() => {
  void auth.bootstrap()
})

function buildPayload(extraOffset: number) {
  return {
    pillars: {
      year: form.year || null,
      month: form.month || null,
      day: form.day || null,
      hour: form.hour || null,
    },
    range_start: form.range[0],
    range_end: form.range[1],
    timezone: form.timezone,
    longitude: needsLongitude.value ? form.longitude : null,
    convention: { ...form.convention },
    limit: form.limit,
    offset: extraOffset,
  }
}

async function search(nextOffset = 0): Promise<void> {
  if (!filledCount.value) {
    ElMessage.warning('至少填写一个柱位')
    return
  }
  if (needsLongitude.value && form.longitude === null) {
    ElMessage.warning('选择真太阳时后必须填写出生地经度')
    return
  }
  if (form.hour && !form.day && !form.year && !form.month) {
    ElMessage.warning('只填时柱会匹配两百年的每一天，请至少补一个日柱或年柱')
    return
  }
  loading.value = true
  try {
    result.value = await reverseApi.reverseSearch(buildPayload(nextOffset))
    offset.value = nextOffset
  } catch {
    result.value = null
  } finally {
    loading.value = false
  }
}

function reset(): void {
  form.year = ''
  form.month = ''
  form.day = ''
  form.hour = ''
  form.longitude = null
  result.value = null
  offset.value = 0
}

/** 把「11:00-13:00」这类窗口标签换算成代表时刻（中点，跨日则顺延）。 */
function representative(candidate: ReverseCandidate): { datetime: string; hour: number } {
  const label = candidate.hour_windows[0] || '12:00-14:00'
  const match = label.match(/(\d{2}):(\d{2})-(\d{2}):(\d{2})/)
  if (!match) return { datetime: `${candidate.date}T12:00:00`, hour: 12 }
  const [sh, sm, eh, em] = match.slice(1).map(Number)
  const start = sh * 60 + sm
  let end = eh * 60 + em
  if (end <= start) end += 24 * 60
  const mid = Math.floor((start + end) / 2) % (24 * 60)
  const hour = Math.floor(mid / 60)
  const minute = mid % 60
  return {
    datetime: `${candidate.date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`,
    hour,
  }
}

function toFormInput(candidate: ReverseCandidate): BaziFormInput {
  return {
    birth_datetime: representative(candidate).datetime,
    timezone: form.timezone,
    longitude: needsLongitude.value ? form.longitude : null,
    time_known: true,
    gender: 'unknown',
    convention: { ...form.convention },
  }
}

const boardLoading = ref(false)
const boardResult = ref<ChartResult | null>(null)
const boardDate = ref('')

async function expand(candidate: ReverseCandidate): Promise<void> {
  boardLoading.value = true
  boardDate.value = candidate.date
  try {
    boardResult.value = await chartsApi.calculate(toFormInput(candidate))
  } catch {
    boardResult.value = null
  } finally {
    boardLoading.value = false
  }
}

const saving = ref('')

/** 反查 → 选中候选 → 保存命盘 → 跳报告页自动生成（复用既有校验与额度）。 */
async function interpret(candidate: ReverseCandidate): Promise<void> {
  const input = toFormInput(candidate)
  sessionStorage.setItem('xs:pending-chart', JSON.stringify({ form: input, date: candidate.date }))
  if (!auth.isLoggedIn) {
    ElMessage.info('生成 AI 解读需要先登录，登录后会回到本页')
    router.push({ path: '/login', query: { redirect: '/reverse' } })
    return
  }
  saving.value = candidate.date
  try {
    const chart = await chartsApi.saveChart(input, `反查 · ${candidate.date}`)
    sessionStorage.removeItem('xs:pending-chart')
    router.push(`/charts/${chart.id}?interpret=1&depth=brief`)
  } catch {
    // 拦截器已提示
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <div class="reverse-page">
    <div class="intro">
      <h2>四柱反查</h2>
      <p>
        已知某人的四柱干支，反推可能的公历出生日期。<strong>免登录</strong>，不保存任何查询记录；
        柱位填得越少命中越多，只给日柱大约每 60 天命中一天。
      </p>
    </div>

    <div class="form-card">
      <div class="pickers">
        <PillarPicker v-model="form.year" label="年柱" :others="others('year')" />
        <PillarPicker v-model="form.month" label="月柱" :others="others('month')" />
        <PillarPicker v-model="form.day" label="日柱" :others="others('day')" />
        <PillarPicker v-model="form.hour" label="时柱" :others="others('hour')" />
      </div>

      <div class="row">
        <div class="field">
          <div class="field-label">检索范围</div>
          <el-date-picker
            v-model="form.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            :clearable="false"
            style="width: 260px"
          />
          <div class="field-note">上限 200 年；范围越大越慢</div>
        </div>

        <div class="field">
          <div class="field-label">时区</div>
          <el-select v-model="form.timezone" filterable allow-create default-first-option style="width: 180px">
            <el-option v-for="tz in TIMEZONES" :key="tz" :label="tz" :value="tz" />
          </el-select>
        </div>

        <div class="field">
          <div class="field-label">经度</div>
          <el-input-number
            v-model="form.longitude"
            :disabled="!needsLongitude"
            :min="-180"
            :max="180"
            :precision="2"
            :step="0.5"
            style="width: 150px"
          />
          <div class="field-note">{{ needsLongitude ? '东经为正、西经为负' : '仅在真太阳时口径下需要' }}</div>
        </div>

        <div class="field">
          <div class="field-label">每页条数</div>
          <el-select v-model="form.limit" style="width: 100px">
            <el-option v-for="size in [20, 50, 100, 200]" :key="size" :label="`${size} 条`" :value="size" />
          </el-select>
        </div>
      </div>

      <ConventionPanel v-model="form.convention" />

      <div class="actions">
        <el-button type="primary" :loading="loading" @click="search(0)">开始反查</el-button>
        <el-button @click="reset">清空</el-button>
        <span class="hint">已填 {{ filledCount }} 柱</span>
      </div>
    </div>

    <template v-if="result">
      <div class="stats">
        检索 {{ result.searched_days }} 天 · 命中 {{ result.total_matches }} 天
        <span v-if="result.candidates.length">· 当前显示第 {{ pageFrom }}–{{ pageTo }} 条</span>
        <span class="algo">算法 {{ result.algorithm_version }}</span>
      </div>

      <el-alert
        v-if="result.truncated"
        type="info"
        :closable="false"
        show-icon
        title="结果已截断"
        description="命中数超过本次返回上限，请缩小检索范围或补全更多柱位后再查。"
      />

      <el-alert
        v-for="(warning, index) in result.warnings"
        :key="`w-${index}`"
        type="warning"
        :closable="false"
        :title="warning"
      />

      <div v-if="result.candidates.length" class="table-wrap">
        <el-table :data="result.candidates" size="small" border>
          <el-table-column prop="date" label="公历日期" width="120" />
          <el-table-column label="时辰窗口" min-width="150">
            <template #default="{ row }">
              <span v-if="row.hour_windows.length">{{ row.hour_windows.join('、') }}</span>
              <span v-else class="muted">未限定时柱</span>
            </template>
          </el-table-column>
          <el-table-column label="实际四柱" min-width="180">
            <template #default="{ row }">
              <code>
                {{ row.pillars.year }} {{ row.pillars.month }} {{ row.pillars.day }} {{ row.pillars.hour }}
              </code>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="160">
            <template #default="{ row }">
              <span class="muted">{{ row.notes.join('；') || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="190" fixed="right">
            <template #default="{ row }">
              <el-button size="small" :loading="boardLoading && boardDate === row.date" @click="expand(row)">
                展开盘面
              </el-button>
              <el-button
                size="small"
                type="primary"
                plain
                :loading="saving === row.date"
                @click="interpret(row)"
              >
                生成解读
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pager">
          <el-button size="small" :disabled="offset === 0" @click="search(Math.max(offset - form.limit, 0))">
            上一页
          </el-button>
          <el-button
            size="small"
            :disabled="offset + result.candidates.length >= result.total_matches"
            @click="search(offset + form.limit)"
          >
            下一页
          </el-button>
        </div>
      </div>

      <div v-else class="diagnosis">
        <h3>没有命中，逐柱排查如下</h3>
        <ul>
          <li v-for="(item, index) in result.diagnosis" :key="`d-${index}`">{{ item }}</li>
        </ul>
        <p class="muted">
          最常见的原因是记错了一柱、或与出生时间不在同一时区。可以先只填日柱确认干支本身是否存在于该范围。
        </p>
      </div>

      <section v-if="boardResult" class="board-area">
        <div class="board-head">
          <h3>盘面预览 · {{ boardDate }}</h3>
          <el-button size="small" text @click="boardResult = null">收起</el-button>
        </div>
        <ChartBoard :result="boardResult" />
        <p class="muted">
          预览按该时辰窗口的代表时刻计算；窗口内不同时刻的年月柱可能因交节而不同，最终以保存后的盘面为准。
        </p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.reverse-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.intro h2 {
  margin: 0 0 6px;
}

.intro p {
  margin: 0;
  font-size: 13px;
  line-height: 1.85;
  color: var(--xs-text-muted);
}

.form-card,
.board-area,
.diagnosis {
  border: 1px solid var(--xs-border);
  border-radius: 12px;
  background: #fff;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pickers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px 20px;
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 24px;
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
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.stats {
  font-size: 13px;
  color: var(--xs-text-muted);
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.algo {
  color: var(--xs-text-muted);
  opacity: 0.7;
}

.table-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.diagnosis h3 {
  margin: 0;
  font-size: 15px;
}

.diagnosis ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 2;
}

.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.board-head h3 {
  margin: 0;
}

.muted {
  color: var(--xs-text-muted);
  font-size: 12px;
}

.hint {
  font-size: 12px;
  color: var(--xs-text-muted);
}
</style>
