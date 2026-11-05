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
import { t } from '../lib/i18n.js'
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

// Подписи — computed: пересчитываются при смене языка (D-065).
const FILTERS = computed(() =>
  ['all', 'submission', 'voting', 'finished'].map((key) => ({ key, label: t(`contests.filter.${key}`) })),
)

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
    { key: 'action', title: t('contests.group.action'), items: action, accent: true },
    { key: 'running', title: t('contests.group.running'), items: running },
    { key: 'finished', title: t('contests.group.finished'), items: finished, limit: true },
  ].filter((group) => group.items.length)
})

const shown = (group) =>
  group.limit && !showAllFinished.value && !query.value ? group.items.slice(0, FINISHED_PREVIEW) : group.items
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>{{ t('contests.title') }}</h1>
        <p class="subtitle">
          {{ organizer ? t('contests.subtitleOrganizer') : t('contests.subtitleParticipant') }}
        </p>
      </div>
      <RouterLink v-if="organizer" class="btn btn-primary" :to="{ name: 'contest-new' }">
        <Icon name="plus" /> {{ t('contests.newContest') }}
      </RouterLink>
    </header>

    <EmptyState
      v-if="error"
      tone="error"
      icon="alert"
      :title="t('contests.loadError')"
      :text="error.message"
    >
      <button class="btn" type="button" @click="load"><Icon name="refresh" /> {{ t('common.retry') }}</button>
    </EmptyState>

    <div v-else-if="!contests" class="card list">
      <div v-for="n in 4" :key="n" class="skeleton loading-row" />
    </div>

    <template v-else-if="contests.length">
      <div class="toolbar">
        <label class="search">
          <span class="sr-only">{{ t('contests.searchByTopic') }}</span>
          <Icon name="search" :size="16" class="icon" />
          <input v-model="query" class="input" type="search" :placeholder="t('contests.searchByTopic')" />
        </label>
        <div class="segmented" role="tablist" :aria-label="t('contests.phaseFilter')">
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
          <span class="sr-only">{{ t('contests.sortLabel') }}</span>
          <select v-model="sort" class="select">
            <option v-for="key in SORTS" :key="key" :value="key">{{ t(`contests.sort.${key}`) }}</option>
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
            <span>{{ t('contests.column.contest') }}</span><span>{{ t('contests.column.phase') }}</span><span>{{ t('contests.column.deadline') }}</span><span>{{ organizer ? t('contests.column.activity') : t('contests.column.participation') }}</span><span />
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
            {{ t('contests.showAllFinished', { count: group.items.length }) }} <Icon name="chevron-down" :size="16" />
          </button>
        </section>
      </div>
      <EmptyState
        v-else-if="query"
        icon="search"
        :title="t('contests.nothingFound')"
        :text="t('contests.nothingFoundText', { query: query.trim() })"
      >
        <button class="btn" type="button" @click="query = ''">{{ t('contests.resetSearch') }}</button>
      </EmptyState>
      <EmptyState v-else icon="list" :title="t('contests.emptyPhase')" :text="t('contests.emptyPhaseText')" />
    </template>

    <EmptyState
      v-else-if="organizer"
      icon="bulb"
      :title="t('contests.emptyOrganizer')"
      :text="t('contests.emptyOrganizerText')"
    >
      <RouterLink class="btn btn-primary" :to="{ name: 'contest-new' }"><Icon name="plus" /> {{ t('contests.newContest') }}</RouterLink>
    </EmptyState>
    <EmptyState
      v-else
      icon="inbox"
      :title="t('contests.emptyParticipant')"
      :text="t('contests.emptyParticipantText')"
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
