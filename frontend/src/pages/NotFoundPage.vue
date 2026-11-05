<script setup>
import { RouterLink } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import { t } from '../lib/i18n.js'
</script>

<template>
  <div class="container page">
    <EmptyState icon="eye-off" :title="t('contests.notFound.title')" :text="t('contests.notFound.text')">
      <RouterLink class="btn btn-primary" :to="{ name: 'contests' }">{{ t('contests.notFound.back') }}</RouterLink>
    </EmptyState>
  </div>
</template>
