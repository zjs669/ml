<script setup lang="ts">
import GenericChartPage from './GenericChartPage.vue'
import { DOMAIN_FORMS } from '@/config/domainForms'

/** 紫微飞星：表单与结果渲染全部由 `GenericChartPage` + 配置驱动。 */
const config = DOMAIN_FORMS['ziwei_flying']
</script>

<template>
  <GenericChartPage :config="config" />
</template>
