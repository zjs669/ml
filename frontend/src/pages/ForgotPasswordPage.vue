<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import * as authApi from '@/api/auth'

/**
 * 忘记密码第一步：填邮箱申请重置。
 *
 * 后端对「邮箱存在 / 不存在」返回完全相同的文案，所以这里不做任何「该邮箱未注册」提示——
 * 既防账号枚举，也避免用户反复试不同邮箱。
 */
const formRef = ref()
const submitting = ref(false)
const sent = ref(false)
const sentMessage = ref('')
const expiresIn = ref(30)
const debugUrl = ref<string | null>(null)

const form = reactive({ email: '' })

const rules = {
  email: [
    { required: true, message: '请填写邮箱', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/, message: '邮箱格式不正确', trigger: 'blur' },
  ],
}

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const result = await authApi.forgotPassword(form.email.trim())
    sent.value = true
    sentMessage.value = result.message
    expiresIn.value = result.expires_in_minutes
    debugUrl.value = result.debug_reset_url
    ElMessage.success('如果该邮箱已注册，重置邮件已发出')
  } catch {
    // 统一错误提示由 axios 拦截器给出（限流时会显示「稍后再试」）
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
          <h2>找回密码</h2>
          <p class="sub">填注册邮箱，我们会发送一条 30 分钟内有效的重置链接。</p>
        </div>
      </div>

      <template v-if="!sent">
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
          <el-form-item label="注册邮箱" prop="email">
            <el-input
              v-model="form.email"
              placeholder="you@example.com"
              autocomplete="username"
              size="large"
              @keyup.enter="submit"
            />
          </el-form-item>
          <el-button type="primary" class="submit" size="large" :loading="submitting" @click="submit">
            发送重置邮件
          </el-button>
        </el-form>
      </template>

      <template v-else>
        <el-result icon="success" title="请检查邮箱" :sub-title="sentMessage" />
        <div class="hints">
          <p>· 链接 {{ expiresIn }} 分钟内有效，只能用一次；</p>
          <p>· 重置成功后，所有已登录设备都会被强制下线；</p>
          <p>· 没收到？先看垃圾箱，或 10 分钟后再申请。</p>
        </div>
        <el-alert
          v-if="debugUrl"
          class="debug"
          type="warning"
          :closable="false"
          show-icon
          title="开发环境提示"
          :description="`MAIL_MODE=console 时不会真的发信，重置链接：${debugUrl}`"
        />
      </template>

      <div class="foot">
        <router-link to="/login">返回登录</router-link>
        <span class="dot">·</span>
        <router-link to="/">回首页</router-link>
      </div>
    </div>

    <div class="side-note">
      <h3>为什么响应总是一样？</h3>
      <p>
        无论邮箱是否注册，接口都返回同一句话。这是刻意的：如果「未注册」和「已注册」的提示不同，
        任何人都能拿一批邮箱来试探哪些账号存在。
      </p>
      <p>如果你的账号是第三方登录或没有绑定邮箱，请联系支持人工核验。</p>
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

.submit {
  width: 100%;
  margin-top: 6px;
}

.hints {
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.9;
  margin: 0 0 12px;
}

.hints p {
  margin: 0;
}

.debug {
  margin-bottom: 12px;
}

.foot {
  margin-top: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.dot {
  margin: 0 6px;
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
