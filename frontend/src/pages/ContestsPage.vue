<script setup>
// Список конкурсов (D-061): вертикальный список строк с этапом, сроком и участием.
// Организатору — все конкурсы, участнику — только те, где он в списке (решает сервер).
// Участнику сверху — «Ждут вашего действия»; поиск, фильтр по этапу и сортировка — здесь же.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import ContestRow from '../components/ContestRow.vue'
import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { syncServerTime } from '../lib/clock.js'
import { useSignals } from '../lib/connection.js'
import { SORTS, arrange, needsAction } from '../lib/contestList.js'
import { isOrganizer } from '../lib/session.js'

const now = useServerNow()
const organizer = computed(isOrganizer)
const contests = ref(null)
const error = ref(null)
const filter = ref('all')
const query = ref('')
const sort = ref('deadline')
const showAllFinished = ref(false)
const FINISHED_PREVIEW = 5

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

// Счётчики в строках меняются от действий всех участников. Чтобы не перечитывать список
// на каждый голос, сигналы объединяются: не чаще раза в секунду.
let pending = null
function loadSoon() {
  if (!pending) pending = setTimeout(() => ((pending = null), load()), 1000)
}
onBeforeUnmount(() => clearTimeout(pending))

useSignals((message) => {
  if (['contests_changed', 'phase_changed', 'resync'].includes(message.type)) load()
  else if (message.type === 'contest_changed') loadSoon()
})
onMounted(load)

const counts = computed(() => {
  const result = { all: 0, submission: 0, voting: 0, finished: 0 }
  for (const item of arrange(contests.value ?? [], now.value)) {
    result.all += 1
    result[item.phase] += 1
  }
  return result
})

const visible = computed(() =>
  arrange(contests.value ?? [], now.value, { query: query.value, phase: filter.value, sort: sort.value }),
)

// Группы — только в общем виде; при выбранном этапе — один плоский список.
const groups = computed(() => {
  if (filter.value !== 'all') return [{ key: 'flat', title: null, items: visible.value }]
  const action = []
  const running = []
  const finished = []
  for (const item of visible.value) {
    if (needsAction(item.contest, item.phase, organizer.value)) action.push(item)
    else if (item.phase === 'finished') finished.push(item)
    else running.push(item)
  }
  return [
    { key: 'action', title: 'Ждут вашего действия', items: action, accent: true },
    { key: 'running', title: 'Идут', items: running },
    { key: 'finished', title: 'Завершены', items: finished, limit: true },
  ].filter((group) => group.items.length)
})

const shown = (group) =>
  group.limit && !showAllFinished.value && !query.value ? group.items.slice(0, FINISHED_PREVIEW) : group.items
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>Конкурсы</h1>
        <p class="subtitle">
          {{ organizer ? 'Все конкурсы компании — создавайте новые и следите за ходом.' : 'Конкурсы, в которых вы участвуете.' }}
        </p>
      </div>
      <RouterLink v-if="organizer" class="btn btn-primary" :to="{ name: 'contest-new' }">
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

    <div v-else-if="!contests" class="card list">
      <div v-for="n in 4" :key="n" class="skeleton loading-row" />
    </div>

    <template v-else-if="contests.length">
      <div class="toolbar">
        <label class="search">
          <span class="sr-only">Поиск по теме</span>
          <Icon name="search" :size="16" class="icon" />
          <input v-model="query" class="input" type="search" placeholder="Поиск по теме" />
        </label>
        <div class="segmented" role="tablist" aria-label="Фильтр по этапу">
          <button
            v-for="item in FILTERS"
            :key="item.key"
            :class="{ active: filter === item.key }"
            type="button"
            role="tab"
            :aria-selected="filter === item.key"
            @click="filter = item.key"
          >
            {{ item.label }} <span class="count">{{ counts[item.key] }}</span>
          </button>
        </div>
        <label class="sort">
          <span class="sr-only">Сортировка</span>
          <select v-model="sort" class="select">
            <option v-for="item in SORTS" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
        </label>
      </div>

      <div v-if="visible.length" class="stack">
        <section
          v-for="(group, index) in groups"
          :key="group.key"
          class="card list"
          :class="{ accent: group.accent }"
        >
          <header v-if="group.title" class="group-head">
            <h2 class="overline">{{ group.title }}</h2>
            <span class="faint">{{ group.items.length }}</span>
          </header>
          <div v-if="index === 0" class="columns" aria-hidden="true">
            <span>Конкурс</span><span>Этап</span><span>Срок</span><span>{{ organizer ? 'Активность' : 'Ваше участие' }}</span><span />
          </div>
          <ContestRow
            v-for="item in shown(group)"
            :key="item.contest.id"
            :contest="item.contest"
            :phase="item.phase"
            :now="now"
            :organizer="organizer"
          />
          <button
            v-if="group.limit && !query && !showAllFinished && group.items.length > FINISHED_PREVIEW"
            class="btn btn-ghost btn-sm more"
            type="button"
            @click="showAllFinished = true"
          >
            Показать все завершённые ({{ group.items.length }}) <Icon name="chevron-down" :size="16" />
          </button>
        </section>
      </div>
      <EmptyState
        v-else-if="query"
        icon="search"
        title="Ничего не найдено"
        :text="`Нет конкурсов, в теме которых есть «${query.trim()}».`"
      >
        <button class="btn" type="button" @click="query = ''">Сбросить поиск</button>
      </EmptyState>
      <EmptyState v-else icon="list" title="Нет конкурсов на этом этапе" text="Выберите другой фильтр." />
    </template>

    <EmptyState
      v-else-if="organizer"
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
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.toolbar .search {
  flex: 1 1 240px;
  max-width: 360px;
}

.sort {
  margin-left: auto;
}

.sort .select {
  width: auto;
}

/* Колонки строк задаются здесь один раз — заголовок и строки совпадают. */
.list {
  --contest-columns: minmax(0, 2.2fr) minmax(0, 1fr) minmax(0, 1.2fr) minmax(0, 1.3fr) 18px;
  padding: 0;
  overflow: hidden;
}

.list.accent {
  border-color: color-mix(in srgb, var(--warning) 45%, var(--border));
}

.group-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px 20px 10px;
}

.list.accent .overline {
  color: var(--warning);
}

.columns {
  display: grid;
  grid-template-columns: var(--contest-columns);
  gap: 20px;
  padding: 8px 16px 8px 20px;
  border-top: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-3);
  font-size: var(--text-xs);
  font-weight: 500;
}

.more {
  width: 100%;
  border-top: 1px solid var(--border);
  border-radius: 0;
  min-height: 40px;
}

.loading-row {
  height: 64px;
  margin: 12px 16px;
}

@media (max-width: 760px) {
  .columns {
    display: none;
  }

  .toolbar .search {
    max-width: none;
    flex-basis: 100%;
  }

  .sort {
    margin-left: 0;
  }
}
</style>
