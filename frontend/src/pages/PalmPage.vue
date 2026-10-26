<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import { analyze, getTypes, type VisionResult, type VisionTypes } from '@/api/vision'
import { useAuthStore } from '@/stores/auth'

/**
 * 手相观察页。
 *
 * 图片上传后由服务端剥 EXIF、按内容寻址落盘，再送视觉模型。
 * 前端不缓存图片 base64，也不做本地预览留存 —— 敏感图片不该留在浏览器里。
 */
const kind = 'palm' as 'face' | 'palm'
const router = useRouter()
const auth = useAuthStore()

const types = ref<VisionTypes | null>(null)
const analysisType = ref('full')
const handType = ref('left')
const question = ref('')
const storeQuestion = ref(true)
const file = ref<File | null>(null)
const fileName = ref('')
const loading = ref(false)
const result = ref<VisionResult | null>(null)

onMounted(async () => {
  try {
    types.value = await getTypes()
    if (kind === 'palm' && types.value) handType.value = Object.keys(types.value.palm.hand_types)[0] || 'left'
  } catch {
    // 拦截器已提示
  }
})

const typeList = computed(() => (kind === 'face' ? types.value?.face.types : types.value?.palm.types) ?? [])
const disclaimer = computed(() =>
  kind === 'face' ? types.value?.face.disclaimer ?? '' : types.value?.palm.disclaimer ?? '',
)
const handTypes = computed(() => types.value?.palm.hand_types ?? {})
const maxMb = computed(() => ((types.value?.max_bytes ?? 5242880) / (1024 * 1024)).toFixed(1))

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const picked = input.files?.[0]
  if (!picked) return
  if (!['image/jpeg', 'image/jpg', 'image/png', 'image/webp'].includes(picked.type)) {
    ElMessage.error('只支持 jpeg / png / webp')
    input.value = ''
    return
  }
  file.value = picked
  fileName.value = picked.name
}

async function onSubmit(): Promise<void> {
  if (!auth.isLoggedIn) {
    ElMessage.info('需要先登录')
    router.push({ path: '/login', query: { redirect: '/palm' } })
    return
  }
  if (!file.value) {
    ElMessage.warning('请先选择图片')
    return
  }
  loading.value = true
  try {
    result.value = await analyze(kind, file.value, {
      analysisType: analysisType.value,
      handType: kind === 'palm' ? handType.value : undefined,
      question: question.value.trim() || undefined,
      storeQuestion: storeQuestion.value,
      idempotencyKey: `${kind}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    })
    if (result.value.degraded) {
      ElMessage.warning('视觉模型不可用，已退回并退还额度')
    } else {
      ElMessage.success('分析完成')
    }
  } catch {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

const observations = computed(() => {
  const payload = result.value?.result as { observations?: Array<Record<string, unknown>> } | undefined
  return payload?.observations ?? []
})

const interpretations = computed(() => {
  const payload = result.value?.result as
    | { traditional_interpretations?: Array<Record<string, unknown>> }
    | undefined
  return payload?.traditional_interpretations ?? []
})

const uncertainties = computed(() => {
  const payload = result.value?.result as { uncertainties?: string[] } | undefined
  return payload?.uncertainties ?? []
})
</script>

<template>
  <div class="vision">
    <div class="page-head">
      <h2>手相观察</h2>
      <p>只依据照片上可见的掌纹与掌型做描述性整理。不推断性格、命运、健康。</p>
    </div>

    <el-alert v-if="disclaimer" type="info" :closable="false" :title="disclaimer" show-icon />

    <el-form label-width="140px" class="form">
      <el-form-item label="分析类型">
        <el-radio-group v-model="analysisType">
          <el-radio-button v-for="item in typeList" :key="item.id" :value="item.id">
            {{ item.name }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item v-if="kind === 'palm'" label="手别">
        <el-radio-group v-model="handType">
          <el-radio-button v-for="(label, value) in handTypes" :key="value" :value="value">
            {{ label }}
          </el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="图片">
        <input type="file" accept="image/jpeg,image/png,image/webp" @change="onFileChange" />
        <div class="hint">
          上限 {{ maxMb }} MiB。上传后服务端会剥除 EXIF（含 GPS、设备型号、拍摄时间），
          只保留像素，按留存策略定期删除。
        </div>
      </el-form-item>

      <el-form-item label="补充问题（可选）">
        <el-input v-model="question" type="textarea" :rows="3" maxlength="200" show-word-limit />
      </el-form-item>

      <el-form-item label="保存问题原文">
        <el-switch v-model="storeQuestion" />
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" @click="onSubmit">开始分析</el-button>
      </el-form-item>
    </el-form>

    <template v-if="result">
      <el-divider content-position="left">观察</el-divider>
      <div class="meta">
        <span>模型：{{ result.usage?.model ?? '—' }}</span>
        <span>耗时：{{ result.usage?.latency_ms ?? 0 }} ms</span>
        <span>图片：{{ result.media.width }}×{{ result.media.height }}</span>
        <span>留存至：{{ result.media.delete_after ?? '—' }}</span>
      </div>

      <ul v-if="observations.length" class="list">
        <li v-for="(item, index) in observations" :key="index">{{ item.fact }}</li>
      </ul>
      <p v-else class="empty">没有返回可展示的观察条目。</p>

      <template v-if="interpretations.length">
        <el-divider content-position="left">传统说法（文化背景，非结论）</el-divider>
        <ul class="list">
          <li v-for="(item, index) in interpretations" :key="index">
            {{ item.claim }}
            <span v-if="item.school_note" class="note">{{ item.school_note }}</span>
          </li>
        </ul>
      </template>

      <template v-if="uncertainties.length">
        <el-divider content-position="left">不确定项</el-divider>
        <ul class="list muted">
          <li v-for="(item, index) in uncertainties" :key="index">{{ item }}</li>
        </ul>
      </template>

      <div class="save-row">
        <el-button @click="router.push(`/charts/${result.chart_id}`)">查看已保存的命盘</el-button>
      </div>

      <el-collapse v-if="result.warnings.length">
        <el-collapse-item :title="`提示（${result.warnings.length} 条）`">
          <ul>
            <li v-for="(item, index) in result.warnings" :key="index">{{ item }}</li>
          </ul>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<style scoped>
.vision {
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

.hint {
  width: 100%;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.meta {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
}

.list.muted {
  color: var(--xs-text-muted);
}

.note {
  margin-left: 8px;
  font-size: 11px;
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
}

ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}
</style>
