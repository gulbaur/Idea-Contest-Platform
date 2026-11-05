<script setup>
// Список участников конкурса — только организатору (D-051). Список после создания
// конкурса не меняется, поэтому загружается один раз.
import { onMounted, ref } from 'vue'

import { api } from '../lib/api.js'
import Icon from './Icon.vue'

const props = defineProps({ contestId: { type: Number, required: true } })

const participants = ref(null)
const failed = ref(false)

async function load() {
  failed.value = false
  try {
    participants.value = await api.participants(props.contestId)
  } catch {
    failed.value = true
  }
}

onMounted(load)
</script>

<template>
  <section class="card">
    <div class="card-title">
      <Icon name="users" />
      <h2>Участники</h2>
      <span v-if="participants" class="faint">{{ participants.length }}</span>
    </div>
    <div v-if="failed" class="row">
      <span class="muted">Не удалось загрузить список.</span>
      <button class="btn btn-sm" type="button" @click="load">Повторить</button>
    </div>
    <div v-else-if="!participants" class="stack-sm">
      <div v-for="n in 3" :key="n" class="skeleton" style="height: 22px" />
    </div>
    <ul v-else class="people">
      <li v-for="person in participants" :key="person.id">{{ person.display_name }}</li>
    </ul>
    <p class="faint hint">Только они подают идеи, голосуют и получают письма. Авторство идей откроется после финала.</p>
  </section>
</template>

<style scoped>
.people {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.people li {
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--surface-2);
  font-size: var(--text-sm);
}

.hint {
  margin-top: 12px;
}
</style>
