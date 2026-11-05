<script setup>
// Демопочта (D-016, D-045): участник видит только свои письма, организатор — журнал всех.
// Права проверяет сервер: страница просто показывает то, что он вернул.
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { useSignals } from '../lib/connection.js'
import { formatDateTime } from '../lib/format.js'
import { notify } from '../lib/notify.js'
import { isOrganizer } from '../lib/session.js'

const KINDS = {
  reminder_submission: { label: 'Напоминание о подаче', icon: 'bell', tone: 'badge-primary' },
  reminder_voting: { label: 'Напоминание о голосовании', icon: 'bell', tone: 'badge-primary' },
  final: { label: 'Итоги', icon: 'trophy', tone: 'badge-gold' },
}
const KIND_FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'reminders', label: 'Напоминания' },
  { key: 'final', label: 'Итоги' },
]

const route = useRoute()
const router = useRouter()
const now = useServerNow()
const organizer = computed(isOrganizer)

const letters = ref(null)
const contests = ref([])
const error = ref(null)
const kind = ref('all')
const selectedId = ref(null)

const contestFilter = computed({
  get: () => (route.query.contest ? Number(route.query.contest) : ''),
  set: (value) => router.replace({ query: value ? { contest: value } : {} }),
})

// Письма приходят порциями от новых к старым (D-059); «Показать ещё» догружает следующую.
const PAGE = 50
const hasMore = ref(false)
const loadingMore = ref(false)

async function load() {
  // Перечитываем столько писем, сколько уже показано: догруженные старые не пропадают.
  const limit = Math.max(PAGE, letters.value?.length ?? 0)
  try {
    const [list, contestList] = await Promise.all([
      api.emails({ contest_id: contestFilter.value || undefined, limit }),
      contests.value.length ? Promise.resolve(contests.value) : api.contests(),
    ])
    letters.value = list
    hasMore.value = list.length === limit
    contests.value = contestList
    error.value = null
    if (selectedId.value && !list.some((letter) => letter.id === selectedId.value)) selectedId.value = null
  } catch (failure) {
    if (!letters.value) error.value = failure
  }
}

async function loadMore() {
  const last = letters.value?.at(-1)
  if (!last || loadingMore.value) return
  loadingMore.value = true
  try {
    const page = await api.emails({
      contest_id: contestFilter.value || undefined,
      limit: PAGE,
      before_time: last.created_at,
      before_id: last.id,
    })
    const known = new Set(letters.value.map((letter) => letter.id))
    letters.value = [...letters.value, ...page.filter((letter) => !known.has(letter.id))]
    hasMore.value = page.length === PAGE
  } catch (failure) {
    notify.error(failure.message)
  } finally {
    loadingMore.value = false
  }
}

useSignals((message) => {
  if (message.type === 'mail_changed' || message.type === 'resync') load()
})
onMounted(load)
watch(contestFilter, () => {
  selectedId.value = null
  letters.value = null // новый фильтр — снова с первой порции
  load()
})

const visible = computed(() =>
  (letters.value ?? []).filter((letter) => {
    if (kind.value === 'reminders') return letter.kind !== 'final'
    if (kind.value === 'final') return letter.kind === 'final'
    return true
  }),
)
const selected = computed(() => visible.value.find((letter) => letter.id === selectedId.value) ?? null)
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>Почта</h1>
        <p class="subtitle">
          {{ organizer ? 'Журнал всех писем сервиса — видно, кому и что отправлено.' : 'Письма, отправленные вам.' }}
        </p>
      </div>
      <div class="filters row">
        <select v-model="contestFilter" class="select contest-select" aria-label="Конкурс">
          <option value="">Все конкурсы</option>
          <option v-for="item in contests" :key="item.id" :value="item.id">{{ item.topic }}</option>
        </select>
        <div class="segmented" role="tablist" aria-label="Вид писем">
          <button
            v-for="item in KIND_FILTERS"
            :key="item.key"
            type="button"
            role="tab"
            :aria-selected="kind === item.key"
            :class="{ active: kind === item.key }"
            @click="kind = item.key"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
    </header>

    <div class="notice stub">
      <Icon name="info" class="icon" />
      <span>
        Это демонстрационная почта: письма сохраняются в базе данных и показываются здесь, наружу они не отправляются.
      </span>
    </div>

    <EmptyState v-if="error" tone="error" icon="alert" title="Не удалось загрузить письма" :text="error.message">
      <button class="btn" type="button" @click="load"><Icon name="refresh" /> Повторить</button>
    </EmptyState>

    <div v-else-if="!letters" class="stack">
      <div v-for="n in 4" :key="n" class="skeleton" style="height: 64px" />
    </div>

    <EmptyState
      v-else-if="!visible.length"
      icon="mail"
      title="Писем пока нет"
      text="Напоминания приходят тем, кто ещё не участвовал, незадолго до конца раунда; итоговое письмо — каждому участнику после финала."
    />

    <div v-else class="mailbox" :class="{ reading: selected }">
      <ul class="list" aria-label="Письма">
        <li v-for="letter in visible" :key="letter.id">
          <button
            class="item"
            :class="{ active: letter.id === selectedId }"
            type="button"
            :data-letter-id="letter.id"
            @click="selectedId = letter.id"
          >
            <span class="kind-mark" :class="letter.kind"><Icon :name="KINDS[letter.kind].icon" :size="16" /></span>
            <span class="summary">
              <span class="subject">{{ letter.subject }}</span>
              <span class="meta">
                <template v-if="organizer">{{ letter.recipient.display_name }} · </template>{{ letter.contest_topic }}
              </span>
            </span>
            <span class="time faint">{{ formatDateTime(letter.created_at, now) }}</span>
          </button>
        </li>
        <li v-if="hasMore" class="more">
          <button class="btn btn-sm" type="button" :disabled="loadingMore" @click="loadMore">
            <span v-if="loadingMore" class="spinner" aria-hidden="true" /> Показать ещё
          </button>
        </li>
      </ul>

      <article v-if="selected" class="letter card" aria-live="polite">
        <button class="btn btn-ghost btn-sm close" type="button" @click="selectedId = null">
          <Icon name="arrow-left" /> К списку
        </button>
        <span class="badge" :class="KINDS[selected.kind].tone">{{ KINDS[selected.kind].label }}</span>
        <h2 class="subject-big">{{ selected.subject }}</h2>
        <dl class="headers">
          <div>
            <dt>Кому</dt>
            <dd>{{ selected.recipient.display_name }} &lt;{{ selected.to_address }}&gt;</dd>
          </div>
          <div>
            <dt>Когда</dt>
            <dd>{{ formatDateTime(selected.created_at, now) }}</dd>
          </div>
          <div>
            <dt>Конкурс</dt>
            <dd>
              <RouterLink :to="{ name: 'contest', params: { id: selected.contest_id } }">
                {{ selected.contest_topic }}
              </RouterLink>
            </dd>
          </div>
        </dl>
        <pre class="body">{{ selected.body }}</pre>
      </article>
      <div v-else class="letter placeholder">
        <Icon name="mail" :size="28" />
        <p class="muted">Выберите письмо, чтобы прочитать его.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.more {
  display: flex;
  justify-content: center;
  padding-top: 6px;
}

.filters {
  gap: 10px;
}

.contest-select {
  width: auto;
  max-width: 280px;
}

.segmented {
  display: inline-flex;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.segmented button {
  padding: 6px 12px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-2);
  font: inherit;
  font-weight: 600;
  font-size: 0.86rem;
  cursor: pointer;
}

.segmented button.active {
  background: var(--primary-soft);
  color: var(--primary-text);
}

.stub {
  margin-bottom: 18px;
}

.mailbox {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 18px;
  align-items: start;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.item:hover {
  background: var(--surface-hover);
}

.item.active {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.kind-mark {
  display: grid;
  place-items: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-text);
}

.kind-mark.final {
  background: var(--gold-soft);
  color: var(--warning);
}

.summary {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

/* Тема — до двух строк: в одной строке почти все темы обрезались. */
.subject {
  display: -webkit-box;
  overflow: hidden;
  font-weight: 650;
  overflow-wrap: anywhere;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.meta {
  overflow: hidden;
  color: var(--text-2);
  font-size: 0.84rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  flex: none;
  font-size: 0.8rem;
}

.letter {
  position: sticky;
  top: calc(var(--header-h) + 16px);
}

.letter .close {
  display: none;
  margin: -6px 0 10px -8px;
}

.subject-big {
  margin: 10px 0 14px;
  overflow-wrap: anywhere;
}

.headers {
  display: grid;
  gap: 6px;
  margin: 0 0 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.headers div {
  display: flex;
  gap: 10px;
  font-size: 0.9rem;
}

.headers dt {
  width: 70px;
  flex: none;
  color: var(--text-3);
}

.headers dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.body {
  margin: 0;
  font-family: var(--font);
  font-size: 0.95rem;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 20px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  color: var(--text-3);
}

@media (max-width: 860px) {
  .mailbox {
    /* minmax(0, …): иначе длинная тема письма в одну строку растягивает колонку шире экрана. */
    grid-template-columns: minmax(0, 1fr);
  }

  .placeholder {
    display: none;
  }

  .mailbox.reading .list {
    display: none;
  }

  .letter {
    position: static;
  }

  .letter .close {
    display: inline-flex;
  }

  .contest-select {
    max-width: none;
    flex: 1;
  }
}
</style>
