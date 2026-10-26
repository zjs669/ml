<script setup lang="ts">
import GenericChartPage from './GenericChartPage.vue'
import { DOMAIN_FORMS } from '@/config/domainForms'

/** 大六壬：表单与结果渲染全部由 `GenericChartPage` + 配置驱动。 */
const config = DOMAIN_FORMS['daliuren']
</script>

<template>
  <GenericChartPage :config="config" />
</template>
