<script setup>
// Список конкурсов: организатору — все, участнику — только те, где он в списке (сервер).
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import ContestCard from '../components/ContestCard.vue'
import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { phaseAt, syncServerTime } from '../lib/clock.js'
import { useSignals } from '../lib/connection.js'
import { isOrganizer } from '../lib/session.js'

const now = useServerNow()
const contests = ref(null)
const error = ref(null)
const filter = ref('all')

const FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'submission', label: 'Приём идей' },
  { key: 'voting', label: 'Голосование' },
  { key: 'finished', label: 'Завершены' },
]

async function load() {
  try {
    const [list, health] = await Promise.all([api.contests(), api.health().catch(() => null)])
    if (health) syncServerTime(health.server_time)
    contests.value = list
    error.value = null
  } catch (failure) {
    if (!contests.value) error.value = failure
  }
}

// Новый конкурс, наступивший срок, восстановление связи — перечитать список.
useSignals((message) => {
  if (['contests_changed', 'phase_changed', 'resync'].includes(message.type)) load()
})
onMounted(load)

const withPhase = computed(() =>
  (contests.value ?? []).map((contest) => ({ contest, phase: phaseAt(contest, now.value) })),
)
const counts = computed(() => {
  const result = { all: withPhase.value.length, submission: 0, voting: 0, finished: 0 }
  for (const item of withPhase.value) result[item.phase] += 1
  return result
})
// Сначала идущие конкурсы, затем завершённые; внутри — как вернул сервер (новые сверху).
const visible = computed(() => {
  const order = { voting: 0, submission: 1, finished: 2 }
  return withPhase.value
    .filter((item) => filter.value === 'all' || item.phase === filter.value)
    .sort((a, b) => order[a.phase] - order[b.phase])
    .map((item) => item.contest)
})
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>Конкурсы</h1>
        <p class="subtitle">
          {{ isOrganizer() ? 'Все конкурсы компании — создавайте новые и следите за ходом.' : 'Конкурсы, в которых вы участвуете.' }}
        </p>
      </div>
      <RouterLink v-if="isOrganizer()" class="btn btn-primary" :to="{ name: 'contest-new' }">
        <Icon name="plus" /> Новый конкурс
      </RouterLink>
    </header>

    <EmptyState
      v-if="error"
      tone="error"
      icon="alert"
      title="Не удалось загрузить конкурсы"
      :text="error.message"
    >
      <button class="btn" type="button" @click="load"><Icon name="refresh" /> Повторить</button>
    </EmptyState>

    <div v-else-if="!contests" class="grid">
      <div v-for="n in 3" :key="n" class="skeleton" style="height: 150px; border-radius: 18px" />
    </div>

    <template v-else-if="contests.length">
      <div class="filters" role="tablist" aria-label="Фильтр по этапу">
        <button
          v-for="item in FILTERS"
          :key="item.key"
          class="filter"
          :class="{ active: filter === item.key }"
          type="button"
          role="tab"
          :aria-selected="filter === item.key"
          @click="filter = item.key"
        >
          {{ item.label }} <span class="count">{{ counts[item.key] }}</span>
        </button>
      </div>

      <div v-if="visible.length" class="grid">
        <ContestCard v-for="contest in visible" :key="contest.id" :contest="contest" :now="now" />
      </div>
      <EmptyState v-else icon="list" title="Нет конкурсов на этом этапе" text="Выберите другой фильтр." />
    </template>

    <EmptyState
      v-else-if="isOrganizer()"
      icon="bulb"
      title="Конкурсов пока нет"
      text="Создайте первый конкурс: тема, срок приёма идей, срок голосования и участники."
    >
      <RouterLink class="btn btn-primary" :to="{ name: 'contest-new' }"><Icon name="plus" /> Новый конкурс</RouterLink>
    </EmptyState>
    <EmptyState
      v-else
      icon="inbox"
      title="Вас пока не пригласили в конкурс"
      text="Когда организатор включит вас в список участников, конкурс появится здесь сразу — обновлять страницу не нужно."
    />
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.filters {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 18px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.filter {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 12px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-2);
  font: inherit;
  font-weight: 600;
  font-size: 0.88rem;
  cursor: pointer;
}

.filter:hover {
  background: var(--surface-hover);
}

.filter.active {
  background: var(--primary-soft);
  color: var(--primary-text);
}

.count {
  min-width: 20px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--surface-2);
  font-size: 0.75rem;
  text-align: center;
}

.filter.active .count {
  background: var(--surface);
}

@media (max-width: 400px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
