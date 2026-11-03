<script setup>
import { RouterLink } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
</script>

<template>
  <div class="container page">
    <EmptyState icon="eye-off" title="Страница не найдена" text="Проверьте адрес или вернитесь к списку конкурсов.">
      <RouterLink class="btn btn-primary" :to="{ name: 'contests' }">К конкурсам</RouterLink>
    </EmptyState>
  </div>
</template>
