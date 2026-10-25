<script setup lang="ts">
/** 不确定项：口径差异、节气临界、时辰不详等必须显式列出，而不是被藏进正文。 */
defineProps<{
  items: string[]
}>()
</script>

<template>
  <div class="uncertainty-box">
    <div class="head">
      <span class="title">不确定项与口径说明</span>
    </div>
    <p v-if="!items.length" class="none">本次未发现需要额外提示的不确定项。</p>
    <ul v-else>
      <li v-for="(item, index) in items" :key="index">{{ item }}</li>
    </ul>
    <div class="foot">
      相同学术体系内存在不同口径时，本站不做"唯一正确"的判断，只给出所用口径并允许切换比对。
    </div>
  </div>
</template>

<style scoped>
.uncertainty-box {
  border: 1px dashed var(--xs-border);
  border-radius: 12px;
  background: #fbfaf6;
  padding: 14px 16px;
}

.head {
  margin-bottom: 8px;
}

.title {
  font-weight: 600;
  font-size: 14px;
}

ul {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
  color: var(--xs-text);
}

.none {
  margin: 0;
  font-size: 13px;
  color: var(--xs-text-muted);
}

.foot {
  margin-top: 10px;
  font-size: 12px;
  color: var(--xs-text-muted);
  line-height: 1.7;
}
</style>
