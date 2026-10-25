<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')

/** 右侧说明用：登录后典型的三步，避免那列只剩一段安全声明 */
const FLOW = [
  { title: '排盘', desc: '免登录，四术数都能直接出盘，结果带算法版本与口径。' },
  { title: '保存', desc: '登录后把盘面与所用口径一起存档，方便复盘对比。' },
  { title: '解读', desc: 'AI 只解释盘面事实，每条解释都能点回知识库原文。' },
]
const formRef = ref()
const submitting = ref(false)

const form = reactive({
  email: '',
  password: '',
  displayName: '',
  accepted: false,
})

const rules = {
  email: [
    { required: true, message: '请填写邮箱', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/, message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请填写密码', trigger: 'blur' },
    { min: 8, message: '至少 8 位', trigger: 'blur' },
  ],
}

/** 注册时的即时强度提示：只讲规则，不给「安全性百分比」这种假指标 */
const passwordHint = computed(() => {
  if (mode.value === 'login') return '登录后不区分「邮箱不存在」与「密码错误」'
  const value = form.password
  if (!value) return '至少 8 位，需同时包含字母与数字'
  if (value.length < 8) return '还差一些：至少 8 位'
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return '还需要同时包含字母与数字'
  if (/^password|^123456|^admin/i.test(value)) return '这个组合太常见，建议换一个'
  return '符合规则'
})

async function submit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  if (mode.value === 'register' && !form.accepted) {
    ElMessage.warning('注册需要先同意隐私政策与用户协议')
    return
  }
  submitting.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(form.email, form.password)
      ElMessage.success('登录成功')
    } else {
      await auth.register(form.email, form.password, form.displayName)
      ElMessage.success('注册成功，已自动登录')
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/account'
    router.push(redirect)
  } catch {
    // 拦截器已提示；被锁定的账号会看到明确的重试时间
  } finally {
    submitting.value = false
  }
}

function switchMode(next: 'login' | 'register'): void {
  mode.value = next
  formRef.value?.clearValidate()
}

onMounted(() => {
  if (route.query.reset === '1') {
    ElMessage.success('密码已重置，请用新密码登录')
  }
})
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="brand-row">
        <div class="mark">玄</div>
        <div>
          <h1>玄枢国学研习台</h1>
          <p class="sub">排盘免登录；保存命盘与生成解读需要账号。</p>
        </div>
      </div>

      <div class="tabs">
        <button class="tab" :class="{ active: mode === 'login' }" @click="switchMode('login')">登录</button>
        <button class="tab" :class="{ active: mode === 'register' }" @click="switchMode('register')">注册</button>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" size="large" placeholder="you@example.com" autocomplete="username" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            size="large"
            :placeholder="mode === 'register' ? '至少 8 位，需同时包含字母与数字' : '请输入密码'"
            :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
            @keyup.enter="submit"
          />
          <div class="hint">{{ passwordHint }}</div>
        </el-form-item>

        <el-form-item v-if="mode === 'register'" label="昵称（可选）">
          <el-input v-model="form.displayName" size="large" maxlength="80" placeholder="仅用于页面称呼" />
        </el-form-item>

        <el-form-item v-if="mode === 'register'">
          <el-checkbox v-model="form.accepted">
            我已阅读并同意
            <router-link to="/legal/privacy">隐私政策</router-link>、
            <router-link to="/legal/terms">用户协议</router-link> 与
            <router-link to="/legal/ai">AI 使用说明</router-link>
          </el-checkbox>
        </el-form-item>

        <el-button type="primary" class="submit" size="large" :loading="submitting" @click="submit">
          {{ mode === 'login' ? '登录' : '注册并登录' }}
        </el-button>
      </el-form>

      <div class="foot">
        <template v-if="mode === 'login'">
          <router-link to="/forgot-password" class="forgot">忘记密码？</router-link>
          <p class="foot-note">连续输错 5 次会临时锁定账号，这是为了防止撞库。</p>
        </template>
        <template v-else>
          <p class="foot-note">密码只保存 Argon2id 哈希，管理员也看不到明文。</p>
        </template>
      </div>
    </div>

    <aside class="side">
      <h2>账号能做什么</h2>
      <ul>
        <li><strong>保存命盘</strong>：四柱、紫微、六爻、奇门各存一份，带口径与算法版本。</li>
        <li><strong>生成解读</strong>：简版每天 1 次免费；详版用付费额度，失败自动退还。</li>
        <li><strong>追溯来源</strong>：报告里的每条解释都带知识库出处，可点开对照原文。</li>
        <li><strong>随时删除</strong>：命盘、笔记、账号都可自助删除，注销 30 天后物理清理。</li>
      </ul>
      <div class="flow">
        <div v-for="(step, index) in FLOW" :key="step.title" class="flow-item">
          <span class="flow-idx">{{ index + 1 }}</span>
          <div class="flow-body">
            <div class="flow-title">{{ step.title }}</div>
            <div class="flow-desc">{{ step.desc }}</div>
          </div>
        </div>
      </div>
      <div class="safe-note">
        安全说明：登录令牌 15 分钟过期，刷新令牌一次性使用；改密或登出会让所有设备立即下线。
      </div>
    </aside>
  </div>
</template>

<style scoped>
.auth-page {
  display: grid;
  grid-template-columns: minmax(0, 420px) minmax(0, 1fr);
  gap: 26px;
  align-items: stretch;
  /* 宽屏时整体居中、不要把两列硬贴到页面左侧 */
  max-width: 980px;
  margin: 0 auto;
  padding: 32px 0 48px;
}

.auth-card {
  background: #fff;
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  padding: 28px 28px 22px;
  box-shadow: 0 12px 30px rgba(120, 98, 60, 0.08);
}

.brand-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.mark {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: 11px;
  background: linear-gradient(135deg, #8a6a3b, #b8975f);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 21px;
  font-family: 'Songti SC', 'STSong', serif;
}

h1 {
  margin: 0 0 4px;
  font-size: 22px;
  letter-spacing: 1px;
}

.sub {
  margin: 0;
  font-size: 12px;
  color: var(--xs-text-muted);
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

.tab {
  flex: 1;
  border: 1px solid var(--xs-border);
  background: #fff;
  border-radius: 9px;
  padding: 9px 0;
  font-size: 14px;
  cursor: pointer;
  color: var(--xs-text-muted);
  transition: all 0.15s ease;
}

.tab.active {
  border-color: var(--xs-accent);
  color: var(--xs-accent);
  font-weight: 600;
  background: #fdfaf3;
}

.submit {
  width: 100%;
  margin-top: 4px;
}

.hint {
  font-size: 12px;
  color: var(--xs-text-muted);
  margin-top: 4px;
}

.foot {
  margin-top: 14px;
  font-size: 12px;
  color: var(--xs-text-muted);
  text-align: left;
  line-height: 1.8;
}

.forgot {
  font-size: 12.5px;
}

.foot-note {
  margin: 4px 0 0;
  font-size: 11.5px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}

.side {
  border: 1px solid var(--xs-border);
  border-radius: 16px;
  background: linear-gradient(160deg, #fff 0%, #faf7ef 100%);
  padding: 22px 24px;
  max-width: 520px;
  /* 与左侧表单同高，安全说明贴底，避免右侧下半段空一大块 */
  display: flex;
  flex-direction: column;
}

.side h2 {
  margin: 0 0 10px;
  font-size: 15px;
}

.side ul {
  margin: 0 0 12px;
  padding-left: 18px;
  font-size: 13px;
  line-height: 2;
  color: var(--xs-text-muted);
}

.safe-note {
  margin-top: auto;
  font-size: 12px;
  line-height: 1.9;
  color: #8a5a1c;
  background: #fdf6ec;
  border: 1px solid #f2e5cf;
  border-radius: 10px;
  padding: 10px 12px;
}

.flow {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 4px 0 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--xs-border);
}

.flow-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.flow-idx {
  width: 20px;
  height: 20px;
  flex: none;
  margin-top: 1px;
  border-radius: 50%;
  background: #f6f1e6;
  color: var(--xs-accent);
  font-size: 11px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.flow-title {
  font-size: 13px;
  font-weight: 600;
}

.flow-desc {
  font-size: 12px;
  line-height: 1.7;
  color: var(--xs-text-muted);
}

@media (max-width: 900px) {
  .auth-page {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
    justify-items: center;
  }

  /* 单列时不要把表单拉成整屏宽：限宽居中，输入框与按钮才好看 */
  .auth-card,
  .side {
    width: 100%;
    max-width: 460px;
  }
}
</style>
