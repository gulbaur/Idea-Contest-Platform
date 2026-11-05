<script setup>
// Журнал рассылки (D-063) — технический список всех отправленных писем: кому, что и когда.
// Организатору и администратору; не смешивается с личными «Входящими».
// Напоминания незавершённого конкурса здесь не показываются — так решает сервер (D-058).
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import LetterView from '../components/LetterView.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { useSignals } from '../lib/connection.js'
import { formatDateTime } from '../lib/format.js'
import { KINDS, kindOf } from '../lib/mail.js'
import { notify } from '../lib/notify.js'
import { isOrganizer } from '../lib/session.js'

const now = useServerNow()
const letters = ref(null)
const contests = ref([])
const error = ref(null)
// «Письма этого конкурса» со страницы конкурса открывают журнал с выбранным конкурсом.
const route = useRoute()
const contestId = ref(route.query.contest ? Number(route.query.contest) : '')
const kind = ref('')
const recipient = ref('')
const selected = ref(null)

const PAGE = 50
const hasMore = ref(false)
const loadingMore = ref(false)

const query = (extra = {}) => ({
  contest_id: contestId.value || undefined,
  kind: kind.value || undefined,
  recipient: recipient.value.trim() || undefined,
  ...extra,
})

async function load() {
  const limit = Math.max(PAGE, letters.value?.length ?? 0)
  try {
    letters.value = await api.journal(query({ limit }))
    hasMore.value = letters.value.length === limit
    error.value = null
  } catch (failure) {
    if (!letters.value) error.value = failure
  }
}

async function loadMore() {
  const last = letters.value?.at(-1)
  if (!last || loadingMore.value) return
  loadingMore.value = true
  try {
    const page = await api.journal(query({ limit: PAGE, before_time: last.created_at, before_id: last.id }))
    const known = new Set(letters.value.map((letter) => letter.id))
    letters.value = [...letters.value, ...page.filter((letter) => !known.has(letter.id))]
    hasMore.value = page.length === PAGE
  } catch (failure) {
    notify.error(failure.message)
  } finally {
    loadingMore.value = false
  }
}

onMounted(async () => {
  load()
  // Список конкурсов для фильтра есть только у организатора; администратор фильтрует по получателю.
  if (isOrganizer()) contests.value = await api.contests().catch(() => [])
})

// Поиск по получателю — после паузы в наборе, а не на каждую букву.
let typing = null
watch(recipient, () => {
  clearTimeout(typing)
  typing = setTimeout(reload, 300)
})
watch([contestId, kind], reload)
onBeforeUnmount(() => clearTimeout(typing))

function reload() {
  letters.value = null
  load()
}

useSignals((message) => {
  if (message.type === 'mail_changed' || message.type === 'resync') load()
})

const kindOptions = computed(() => Object.entries(KINDS).map(([key, value]) => ({ key, label: value.label })))
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>Журнал рассылки</h1>
        <p class="subtitle">
          Все отправленные письма: кому, что и когда. Напоминания идущих конкурсов появятся здесь после финала — по их
          получателям можно было бы вычислить авторов идей.
        </p>
      </div>
    </header>

    <div class="toolbar">
      <label class="search">
        <span class="sr-only">Получатель</span>
        <Icon name="search" :size="16" class="icon" />
        <input v-model="recipient" class="input" type="search" placeholder="Получатель: имя или адрес" />
      </label>
      <select v-if="contests.length" v-model="contestId" class="select narrow" aria-label="Конкурс">
        <option value="">Все конкурсы</option>
        <option v-for="item in contests" :key="item.id" :value="item.id">{{ item.topic }}</option>
      </select>
      <select v-model="kind" class="select narrow" aria-label="Вид письма">
        <option value="">Все виды писем</option>
        <option v-for="item in kindOptions" :key="item.key" :value="item.key">{{ item.label }}</option>
      </select>
    </div>

    <EmptyState v-if="error" tone="error" icon="alert" title="Не удалось загрузить журнал" :text="error.message">
      <button class="btn" type="button" @click="load"><Icon name="refresh" /> Повторить</button>
    </EmptyState>
    <div v-else-if="!letters" class="card list"><div v-for="n in 5" :key="n" class="skeleton loading-row" /></div>
    <EmptyState v-else-if="!letters.length" icon="mail" title="Писем не найдено" text="Измените фильтры или подождите — письма появятся по расписанию конкурсов." />

    <div v-else class="card list">
      <div class="columns" aria-hidden="true"><span>Когда</span><span>Получатель</span><span>Письмо</span><span>Вид</span></div>
      <button
        v-for="letter in letters"
        :key="letter.id"
        class="journal-row"
        type="button"
        :data-journal-id="letter.id"
        @click="selected = letter"
      >
        <span class="faint when">{{ formatDateTime(letter.created_at, now) }}</span>
        <span class="who">
          <strong>{{ letter.recipient.display_name }}</strong>
          <span class="faint">{{ letter.to_address }}</span>
        </span>
        <span class="what">
          <span class="subject">{{ letter.subject }}</span>
          <span class="faint">{{ letter.contest_topic }}</span>
        </span>
        <span><span class="badge" :class="kindOf(letter.kind).tone">{{ kindOf(letter.kind).label }}</span></span>
      </button>
      <button v-if="hasMore" class="btn btn-ghost btn-sm more" type="button" :disabled="loadingMore" @click="loadMore">
        <span v-if="loadingMore" class="spinner" aria-hidden="true" /> Показать ещё
      </button>
    </div>

    <ModalDialog v-if="selected" title="Письмо" wide @close="selected = null">
      <LetterView :letter="selected" :now="now" />
    </ModalDialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.toolbar .search {
  flex: 1 1 240px;
  max-width: 360px;
}

.narrow {
  width: auto;
  max-width: 280px;
}

.list {
  --journal-columns: 150px minmax(0, 1.2fr) minmax(0, 2fr) minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}

.columns,
.journal-row {
  display: grid;
  grid-template-columns: var(--journal-columns);
  align-items: center;
  gap: 16px;
  padding: 10px 20px;
}

.columns {
  background: var(--surface-2);
  color: var(--text-3);
  font-size: var(--text-xs);
  font-weight: 500;
}

.journal-row {
  width: 100%;
  border: 0;
  border-top: 1px solid var(--border);
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.journal-row:hover {
  background: var(--surface-hover);
}

.who,
.what {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.who strong {
  font-weight: 500;
}

.who span,
.what span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.more {
  width: 100%;
  border-top: 1px solid var(--border);
  border-radius: 0;
}

.loading-row {
  height: 48px;
  margin: 12px 16px;
}

@media (max-width: 900px) {
  .columns {
    display: none;
  }

  .journal-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 12px;
  }

  .when {
    grid-column: 1 / -1;
  }

  .what {
    grid-column: 1 / -1;
    grid-row: 3;
  }
}
</style>
