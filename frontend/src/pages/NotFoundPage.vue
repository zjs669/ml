<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <el-result icon="info" title="页面不存在" sub-title="链接可能已失效，或该内容不属于当前账号。">
      <template #extra>
        <el-button type="primary" @click="router.push('/')">回到首页</el-button>
        <el-button @click="router.push('/bazi')">去排盘</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.not-found {
  padding: 40px 0;
}
</style>
