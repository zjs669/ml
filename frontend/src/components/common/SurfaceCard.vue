<script setup lang="ts">
/**
 * 内容卡片：统一 border / 圆角 / 底色 / 阴影。
 *
 * 这套外观（`1px solid var(--xs-border)` + `--xs-radius` + 白底 + `--xs-shadow`）
 * 原先在 34 个文件里重复定义 64 次，改一次圆角要改 64 处。
 *
 * `padded=false` 给需要自己控制内边距的场景（如表格铺满）。
 */
withDefaults(
  defineProps<{
    padded?: boolean
    /** 悬停时是否抬起。列表类卡片建议开，表单卡片建议关。 */
    hoverable?: boolean
    /** 次要卡片：浅底，用于「说明」「提示」这类非主体内容 */
    muted?: boolean
  }>(),
  { padded: true, hoverable: false, muted: false },
)
</script>

<template>
  <div class="surface-card" :class="{ padded, hoverable, muted }">
    <slot />
  </div>
</template>

<style scoped>
.surface-card {
  border: 1px solid var(--xs-border);
  border-radius: var(--xs-radius);
  background: #fff;
  box-shadow: 0 4px 14px rgba(120, 98, 60, 0.05);
  transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}

.surface-card.padded {
  padding: 18px 20px;
}

.surface-card.muted {
  background: var(--xs-surface-muted);
  box-shadow: none;
}

.surface-card.hoverable:hover {
  border-color: rgba(138, 106, 59, 0.4);
  box-shadow: var(--xs-shadow-hover);
  transform: translateY(-2px);
}
</style>
