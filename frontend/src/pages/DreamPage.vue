<script setup lang="ts">
import GenericChartPage from './GenericChartPage.vue'
import { DOMAIN_FORMS } from '@/config/domainForms'

/** 解梦：表单与结果渲染全部由 `GenericChartPage` + 配置驱动。 */
const config = DOMAIN_FORMS['dream']
</script>

<template>
  <GenericChartPage :config="config" />
</template>
