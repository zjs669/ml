<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import * as authApi from '@/api/auth'

/**
 * 忘记密码第二步：用邮件里的令牌设置新密码。
 *
 * 令牌从 URL 读取；提交成功后所有旧会话立刻失效，因此这里直接引导去登录页，
 * 而不是顺手登录——避免「改密后旧标签页还挂着」的错觉。
 */
const route = useRoute()
const router = useRouter()

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const formRef = ref()
const submitting = ref(false)
const done = ref(false)

const form = reactive({ password: '', confirm: '' })

const rules = {
  password: [
    { required: true, message: '请填写新密码', trigger: 'blur' },
    { min: 8, message: '至少 8 位，且需同时包含字母与数字', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再输入一次', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
        if (value !== form.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}

/** 粗略强度提示：只讲规则，不给虚假的「安全性百分比」 */
const strengthHint = computed(() => {
  const value = form.password
  if (!value) return '至少 8 位，需同时包含字母与数字'
  if (value.length < 8) return '还差一些：至少 8 位'
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return '还需要同时包含字母与数字'
  if (value.length >= 12) return '长度充足'
  return '符合规则（再长一些更稳）'
})

async function submit(): Promise<void> {
  if (!token.value) return
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const result = await authApi.resetPassword(token.value, form.password)
    done.value = true
    ElMessage.success(result.message)
    setTimeout(() => router.push({ path: '/login', query: { reset: '1' } }), 1200)
  } catch {
    // 令牌无效/过期时拦截器会提示「重置链接无效或已过期」
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="card-head">
        <div class="mark">玄</div>
        <div>
          <h2>设置新密码</h2>
          <p class="sub">重置成功后，所有已登录设备都会被强制下线。</p>
        </div>
      </div>

      <el-alert
        v-if="!token"
        type="error"
        :closable="false"
        show-icon
        title="链接不完整"
        description="地址里没有找到重置令牌。请从邮件里的链接重新打开，或返回「找回密码」重新申请。"
      />

      <template v-else-if="!done">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="新密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              size="large"
              autocomplete="new-password"
              placeholder="至少 8 位，包含字母与数字"
            />
            <div class="hint">{{ strengthHint }}</div>
          </el-form-item>
          <el-form-item label="确认新密码" prop="confirm">
            <el-input
              v-model="form.confirm"
              type="password"
              show-password
              size="large"
              autocomplete="new-password"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-button type="primary" class="submit" size="large" :loading="submitting" @click="submit">
            确认修改
          </el-button>
        </el-form>
      </template>

      <el-result v-else icon="success" title="密码已更新" sub-title="即将跳转到登录页，请用新密码登录。" />

      <div class="foot">
        <router-link to="/login">返回登录</router-link>
      </div>
    </div>

    <div class="side-note">
      <h3>这个链接只能用一次</h3>
      <p>重置令牌 30 分钟内有效，用过即废；同一账号新申请会让旧链接失效。</p>
      <p>密码不会以任何形式回传：服务端只保存 Argon2id 哈希，管理员也看不到明文。</p>
      <p>如果你没有申请重置，说明有人知道你的邮箱；建议改密后开启独立邮箱专用密码。</p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: grid;
  grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
  max-width: 980px;
  margin: 0 auto;
  padding: 32px 0 48px;
}

.auth-card {
  background: #fff;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  padding: 26px 26px 20px;
  box-shadow: 0 12px 30px rgba(120, 98, 60, 0.08);
}

.card-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.mark {
  width: 38px;
  height: 38px;
  flex: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #8a6a3b, #b3906010);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-family: 'Songti SC', 'STSong', serif;
}

h2 {
  margin: 0 0 4px;
  font-size: 20px;
}

.sub {
  margin: 0;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.hint {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-top: 4px;
}

.submit {
  width: 100%;
  margin-top: 6px;
}

.foot {
  margin-top: 16px;
  text-align: center;
  font-size: 12px;
}

.side-note {
  border: 1px dashed var(--xs-border);
  border-radius: 16px;
  padding: 20px 22px;
  background: #fbfaf6;
  max-width: 520px;
}

.side-note h3 {
  margin: 0 0 8px;
  font-size: 14px;
}

.side-note p {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.9;
  color: var(--xs-text-muted);
}

@media (max-width: 900px) {
  .auth-page {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    justify-items: center;
  }

  .auth-card,
  .side-note {
    width: 100%;
    max-width: 460px;
  }
}
</style>
