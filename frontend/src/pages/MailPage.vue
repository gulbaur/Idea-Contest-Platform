<script setup>
// «Входящие» (D-016, D-045, D-063): только письма, адресованные мне, — у любой роли.
// Технический журнал всех писем — отдельная страница «Журнал рассылки» (JournalPage.vue).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import LetterView from '../components/LetterView.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { useSignals } from '../lib/connection.js'
import { formatDateTime } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import { kindOf } from '../lib/mail.js'
import { notify } from '../lib/notify.js'
import { refreshUnread, unread } from '../lib/unread.js'

const route = useRoute()
const router = useRouter()
const now = useServerNow()

const letters = ref(null)
const contests = ref([])
const error = ref(null)
const onlyUnread = ref(false)
const selectedId = ref(null)

const contestFilter = computed({
  get: () => (route.query.contest ? Number(route.query.contest) : ''),
  set: (value) => router.replace({ query: value ? { contest: value } : {} }),
})

// Письма приходят порциями от новых к старым (D-059); «Показать ещё» догружает следующую.
const PAGE = 50
const hasMore = ref(false)
const loadingMore = ref(false)

function query(extra = {}) {
  return { contest_id: contestFilter.value || undefined, unread: onlyUnread.value || undefined, ...extra }
}

async function load() {
  // Перечитываем столько писем, сколько уже показано: догруженные старые не пропадают.
  const limit = Math.max(PAGE, letters.value?.length ?? 0)
  try {
    const [list, contestList] = await Promise.all([
      api.emails(query({ limit })),
      contests.value.length ? Promise.resolve(contests.value) : api.contests().catch(() => []),
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
    const page = await api.emails(query({ limit: PAGE, before_time: last.created_at, before_id: last.id }))
    const known = new Set(letters.value.map((letter) => letter.id))
    letters.value = [...letters.value, ...page.filter((letter) => !known.has(letter.id))]
    hasMore.value = page.length === PAGE
  } catch (failure) {
    notify.error(failure.message)
  } finally {
    loadingMore.value = false
  }
}

// Открытое письмо становится прочитанным — на сервере и сразу на экране.
async function open(letter) {
  selectedId.value = letter.id
  if (letter.read_at) return
  letter.read_at = new Date(now.value).toISOString()
  unread.count = Math.max(0, unread.count - 1)
  try {
    await api.markRead(letter.id)
  } catch {
    // Не страшно: письмо останется непрочитанным на сервере и обновится при следующей загрузке.
  }
  refreshUnread()
}

async function readAll() {
  try {
    await api.markAllRead()
    await Promise.all([load(), refreshUnread()])
  } catch (failure) {
    notify.error(failure.message)
  }
}

useSignals((message) => {
  if (message.type === 'mail_changed' || message.type === 'resync') load()
})
onMounted(load)
watch([contestFilter, onlyUnread], () => {
  selectedId.value = null
  letters.value = null // новый фильтр — снова с первой порции
  load()
})

const selected = computed(() => letters.value?.find((letter) => letter.id === selectedId.value) ?? null)
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>{{ t('mail.title') }}</h1>
        <p class="subtitle">{{ t('mail.subtitle') }}</p>
      </div>
      <button v-if="unread.count" class="btn btn-sm" type="button" @click="readAll">
        <Icon name="check" :size="16" /> {{ t('mail.readAll') }}
      </button>
    </header>

    <div class="toolbar">
      <select v-model="contestFilter" class="select contest-select" :aria-label="t('mail.contest')">
        <option value="">{{ t('mail.allContests') }}</option>
        <option v-for="item in contests" :key="item.id" :value="item.id">{{ item.topic }}</option>
      </select>
      <div class="segmented" role="tablist" :aria-label="t('mail.whichLetters')">
        <button type="button" role="tab" :aria-selected="!onlyUnread" :class="{ active: !onlyUnread }" @click="onlyUnread = false">
          {{ t('mail.all') }}
        </button>
        <button type="button" role="tab" :aria-selected="onlyUnread" :class="{ active: onlyUnread }" @click="onlyUnread = true">
          {{ t('mail.unread') }} <span class="count">{{ unread.count }}</span>
        </button>
      </div>
    </div>

    <div class="notice stub">
      <Icon name="info" class="icon" />
      <span>{{ t('mail.demoNotice') }}</span>
    </div>

    <EmptyState v-if="error" tone="error" icon="alert" :title="t('mail.loadFailed')" :text="error.message">
      <button class="btn" type="button" @click="load"><Icon name="refresh" /> {{ t('common.retry') }}</button>
    </EmptyState>

    <div v-else-if="!letters" class="stack-sm">
      <div v-for="n in 4" :key="n" class="skeleton" style="height: 64px" />
    </div>

    <EmptyState
      v-else-if="!letters.length"
      icon="mail"
      :title="onlyUnread ? t('mail.noUnread') : t('mail.empty')"
      :text="t('mail.emptyText')"
    />

    <div v-else class="mailbox" :class="{ reading: selected }">
      <ul class="list card" :aria-label="t('mail.letters')">
        <li v-for="letter in letters" :key="letter.id">
          <button
            class="item"
            :class="{ active: letter.id === selectedId, unread: !letter.read_at }"
            type="button"
            :data-letter-id="letter.id"
            @click="open(letter)"
          >
            <span class="kind-mark" :class="letter.kind"><Icon :name="kindOf(letter.kind).icon" :size="16" /></span>
            <span class="summary">
              <span class="subject">{{ letter.subject }}</span>
              <span class="meta">{{ kindOf(letter.kind).label }} · {{ letter.contest_topic }}</span>
            </span>
            <span class="time faint">{{ formatDateTime(letter.created_at, now) }}</span>
            <span v-if="!letter.read_at" class="dot" :aria-label="t('mail.notRead')" />
          </button>
        </li>
        <li v-if="hasMore" class="more">
          <button class="btn btn-ghost btn-sm" type="button" :disabled="loadingMore" @click="loadMore">
            <span v-if="loadingMore" class="spinner" aria-hidden="true" /> {{ t('common.showMore') }}
          </button>
        </li>
      </ul>

      <article v-if="selected" class="letter card" aria-live="polite">
        <button class="btn btn-ghost btn-sm close" type="button" @click="selectedId = null">
          <Icon name="arrow-left" /> {{ t('mail.backToList') }}
        </button>
        <LetterView :letter="selected" :now="now" />
      </article>
      <div v-else class="letter placeholder">
        <Icon name="mail" :size="28" />
        <p class="muted">{{ t('mail.choose') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 16px;
}

.contest-select {
  width: auto;
  max-width: 320px;
}

.stub {
  margin-bottom: 16px;
}

.mailbox {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 16px;
  align-items: start;
}

.list {
  margin: 0;
  padding: 0;
  overflow: hidden;
  list-style: none;
}

.list li + li {
  border-top: 1px solid var(--border);
}

.item {
  position: relative;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 12px 28px 12px 14px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.item:hover {
  background: var(--surface-hover);
}

.item.active {
  background: var(--primary-soft);
}

.kind-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--surface-hover);
  color: var(--text-2);
}

.kind-mark.final {
  background: var(--gold-soft);
  color: var(--warning);
}

.kind-mark.invitation,
.kind-mark.voting_open {
  background: var(--primary-soft);
  color: var(--primary-text);
}

.kind-mark.reminder_submission,
.kind-mark.reminder_voting {
  background: var(--warning-soft);
  color: var(--warning);
}

.kind-mark.org_job_failed {
  background: var(--danger-soft);
  color: var(--danger);
}

.summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.subject {
  /* Длинная тема — не больше двух строк. */
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow-wrap: anywhere;
}

.item.unread .subject {
  font-weight: 600;
}

.meta {
  overflow: hidden;
  color: var(--text-3);
  font-size: var(--text-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  white-space: nowrap;
}

.dot {
  position: absolute;
  top: 50%;
  right: 12px;
  width: 8px;
  height: 8px;
  margin-top: -4px;
  border-radius: 50%;
  background: var(--primary);
}

.more {
  display: flex;
  justify-content: center;
  padding: 6px;
}

.letter {
  position: sticky;
  top: var(--sticky-top);
}

.letter .close {
  display: none;
  margin-bottom: 8px;
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

/* Узкий экран: список или письмо — по очереди. */
@media (max-width: 860px) {
  .mailbox {
    grid-template-columns: minmax(0, 1fr);
  }

  .mailbox.reading .list,
  .mailbox:not(.reading) .letter {
    display: none;
  }

  .letter {
    position: static;
  }

  .letter .close {
    display: inline-flex;
  }

  .time {
    display: none;
  }
}
</style>
