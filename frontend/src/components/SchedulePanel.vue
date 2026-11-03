<script setup>
// Расписание конкурса для организатора (D-051): напоминания и подведение итогов.
import { RouterLink } from 'vue-router'

import { formatCountdown, formatDateTime } from '../lib/format.js'
import Icon from './Icon.vue'

defineProps({
  schedule: { type: Array, required: true },
  contestId: { type: Number, required: true },
  now: { type: Number, required: true },
})

const KIND = {
  remind_submission: { title: 'Напоминание о подаче идей', icon: 'bell' },
  remind_voting: { title: 'Напоминание о голосовании', icon: 'bell' },
  finalize: { title: 'Итоги и письма участникам', icon: 'flag' },
}
const STATUS = {
  pending: { text: 'Запланировано', tone: '' },
  done: { text: 'Выполнено', tone: 'badge-success' },
  skipped: { text: 'Пропущено', tone: 'badge-warning' },
  failed: { text: 'Ошибка', tone: 'badge-danger' },
}
</script>

<template>
  <section class="card">
    <div class="card-title">
      <Icon name="calendar" />
      <h2>Расписание</h2>
    </div>
    <ul class="jobs">
      <li v-for="job in schedule" :key="job.kind" class="job" :data-kind="job.kind">
        <span class="mark" :class="job.status"><Icon :name="KIND[job.kind].icon" :size="16" /></span>
        <div class="body">
          <strong>{{ KIND[job.kind].title }}</strong>
          <div class="when">
            <span class="badge" :class="STATUS[job.status].tone">{{ STATUS[job.status].text }}</span>
            <span class="faint">{{ formatDateTime(job.finished_at ?? job.run_at) }}</span>
            <span v-if="job.status === 'pending' && Date.parse(job.run_at) > now" class="faint">
              · через {{ formatCountdown(Date.parse(job.run_at) - now) }}
            </span>
          </div>
          <div v-if="job.note" class="note">{{ job.note }}</div>
        </div>
      </li>
    </ul>
    <RouterLink class="btn btn-soft btn-sm mail-link" :to="{ name: 'mail', query: { contest: contestId } }">
      <Icon name="mail" /> Письма этого конкурса
    </RouterLink>
  </section>
</template>

<style scoped>
.jobs {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}

.job {
  display: flex;
  gap: 12px;
}

.mark {
  display: grid;
  place-items: center;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-3);
}

.mark.done {
  background: var(--success-soft);
  color: var(--success);
}

.mark.skipped {
  background: var(--warning-soft);
  color: var(--warning);
}

.mark.failed {
  background: var(--danger-soft);
  color: var(--danger);
}

.body {
  flex: 1;
  min-width: 0;
}

.when {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.note {
  margin-top: 2px;
  color: var(--text-2);
  font-size: 0.85rem;
}

.badge-danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.mail-link {
  width: 100%;
}
</style>
