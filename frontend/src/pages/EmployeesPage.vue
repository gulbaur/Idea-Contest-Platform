<script setup>
// Сотрудники и доступ — раздел администратора (D-062): приглашение, роли, отключение,
// ссылки для входа и журнал действий. Права проверяет сервер.
import { computed, onMounted, ref } from 'vue'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import StaffDialog from '../components/StaffDialog.vue'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { ROLE_LABELS, formatDateTime } from '../lib/format.js'
import { notify } from '../lib/notify.js'

const now = useServerNow()
const tab = ref('people')
const people = ref(null)
const error = ref(null)
const query = ref('')
const statusFilter = ref('all')
const dialogFor = ref(undefined) // undefined — закрыт; null — приглашение; объект — сотрудник

const STATUS = {
  active: { label: 'Активен', tone: 'badge-success' },
  invited: { label: 'Приглашён', tone: 'badge-primary' },
  disabled: { label: 'Отключён', tone: 'badge-danger' },
}
const STATUS_FILTERS = [
  { key: 'all', label: 'Все' },
  { key: 'active', label: 'Активные' },
  { key: 'invited', label: 'Приглашены' },
  { key: 'disabled', label: 'Отключены' },
]

async function load() {
  try {
    people.value = await api.staff()
    error.value = null
  } catch (failure) {
    if (!people.value) error.value = failure
    else notify.error(failure.message)
  }
}
onMounted(load)

const counts = computed(() => {
  const result = { all: 0, active: 0, invited: 0, disabled: 0 }
  for (const person of people.value ?? []) {
    result.all += 1
    result[person.status] += 1
  }
  return result
})

const visible = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase('ru')
  return (people.value ?? []).filter(
    (person) =>
      (statusFilter.value === 'all' || person.status === statusFilter.value) &&
      (!needle || [person.display_name, person.login, person.email].some((text) => text.toLocaleLowerCase('ru').includes(needle))),
  )
})

const initials = (name) =>
  name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()

// --- журнал действий ---------------------------------------------------------------
const ACTIONS = {
  user_invited: 'Приглашение',
  user_updated: 'Изменение данных',
  user_disabled: 'Доступ отключён',
  user_enabled: 'Доступ включён',
  password_reset: 'Сброс пароля',
  invite_reissued: 'Новая ссылка для входа',
  password_set: 'Пароль задан по ссылке',
  password_changed: 'Пароль изменён',
}
const events = ref(null)
const hasMore = ref(false)
const AUDIT_PAGE = 50

async function loadAudit(more = false) {
  try {
    const before = more ? events.value?.at(-1)?.id : undefined
    const page = await api.audit({ limit: AUDIT_PAGE, before_id: before })
    events.value = more ? [...events.value, ...page] : page
    hasMore.value = page.length === AUDIT_PAGE
  } catch (failure) {
    notify.error(failure.message)
  }
}

function openTab(key) {
  tab.value = key
  if (key === 'audit') loadAudit()
}

function changed() {
  load()
  if (tab.value === 'audit') loadAudit()
}
</script>

<template>
  <div class="container page">
    <header class="page-header">
      <div>
        <h1>Сотрудники</h1>
        <p class="subtitle">Учётные записи и доступ. Открытой регистрации нет — сотрудников приглашает администратор.</p>
      </div>
      <button class="btn btn-primary" type="button" @click="dialogFor = null"><Icon name="plus" /> Пригласить сотрудника</button>
    </header>

    <div class="segmented tabs" role="tablist" aria-label="Раздел">
      <button type="button" role="tab" :aria-selected="tab === 'people'" :class="{ active: tab === 'people' }" @click="openTab('people')">
        <Icon name="users" :size="16" /> Сотрудники
      </button>
      <button type="button" role="tab" :aria-selected="tab === 'audit'" :class="{ active: tab === 'audit' }" @click="openTab('audit')">
        <Icon name="list" :size="16" /> Журнал действий
      </button>
    </div>

    <template v-if="tab === 'people'">
      <EmptyState v-if="error" tone="error" icon="alert" title="Не удалось загрузить сотрудников" :text="error.message">
        <button class="btn" type="button" @click="load"><Icon name="refresh" /> Повторить</button>
      </EmptyState>
      <div v-else-if="!people" class="card list"><div v-for="n in 4" :key="n" class="skeleton loading-row" /></div>

      <template v-else>
        <div class="toolbar">
          <label class="search">
            <span class="sr-only">Поиск сотрудника</span>
            <Icon name="search" :size="16" class="icon" />
            <input v-model="query" class="input" type="search" placeholder="Имя, логин или почта" />
          </label>
          <div class="segmented" role="tablist" aria-label="Статус">
            <button
              v-for="item in STATUS_FILTERS"
              :key="item.key"
              type="button"
              role="tab"
              :aria-selected="statusFilter === item.key"
              :class="{ active: statusFilter === item.key }"
              @click="statusFilter = item.key"
            >
              {{ item.label }} <span class="count">{{ counts[item.key] }}</span>
            </button>
          </div>
        </div>

        <div v-if="visible.length" class="card list">
          <div class="columns" aria-hidden="true">
            <span>Сотрудник</span><span>Логин</span><span>Роль</span><span>Статус</span><span>Последний вход</span><span />
          </div>
          <div v-for="person in visible" :key="person.id" class="person-row" :data-login="person.login">
            <span class="who">
              <span class="avatar" :class="person.role" aria-hidden="true">{{ initials(person.display_name) }}</span>
              <span class="names">
                <strong>{{ person.display_name }}</strong>
                <span class="faint">{{ person.email }}</span>
              </span>
            </span>
            <span class="mono login">{{ person.login }}</span>
            <span class="role">{{ ROLE_LABELS[person.role] }}</span>
            <span class="status"><span class="badge" :class="STATUS[person.status].tone">{{ STATUS[person.status].label }}</span></span>
            <span class="faint last">{{ person.last_login_at ? formatDateTime(person.last_login_at, now) : '—' }}</span>
            <button class="btn btn-sm" type="button" :aria-label="`Управлять: ${person.display_name}`" @click="dialogFor = person">
              Управлять
            </button>
          </div>
        </div>
        <EmptyState v-else icon="search" title="Никого не найдено" text="Измените поиск или фильтр." />
      </template>
    </template>

    <template v-else>
      <div v-if="!events" class="card list"><div v-for="n in 4" :key="n" class="skeleton loading-row" /></div>
      <EmptyState v-else-if="!events.length" icon="list" title="Действий пока нет" />
      <div v-else class="card list">
        <div v-for="event in events" :key="event.id" class="event-row">
          <span class="faint when">{{ formatDateTime(event.created_at, now) }}</span>
          <span class="what">
            <strong>{{ ACTIONS[event.action] ?? event.action }}</strong>
            <span v-if="event.target" class="muted"> · {{ event.target }}</span>
            <span v-if="event.details" class="faint details">{{ event.details }}</span>
          </span>
          <span class="faint actor">{{ event.actor }}</span>
        </div>
        <button v-if="hasMore" class="btn btn-ghost btn-sm more" type="button" @click="loadAudit(true)">Показать ещё</button>
      </div>
    </template>

    <StaffDialog v-if="dialogFor !== undefined" :person="dialogFor" @close="dialogFor = undefined" @changed="changed" />
  </div>
</template>

<style scoped>
.tabs {
  margin-bottom: 16px;
}

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

.list {
  --staff-columns: minmax(0, 2.4fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.9fr) minmax(0, 1.1fr) auto;
  padding: 0;
  overflow: hidden;
}

.columns,
.person-row {
  display: grid;
  grid-template-columns: var(--staff-columns);
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

.person-row {
  border-top: 1px solid var(--border);
}

.who {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.names {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.names strong {
  font-weight: 500;
}

.names span,
.login {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--phase-submission-soft);
  color: var(--phase-submission);
  font-weight: 600;
  font-size: var(--text-xs);
}

.avatar.organizer {
  background: var(--gold-soft);
  color: var(--warning);
}

.avatar.admin {
  background: var(--phase-voting-soft);
  color: var(--phase-voting);
}

.event-row {
  display: grid;
  grid-template-columns: 170px minmax(0, 1fr) minmax(0, 200px);
  gap: 16px;
  padding: 10px 20px;
  border-top: 1px solid var(--border);
}

.event-row:first-child {
  border-top: 0;
}

.what strong {
  font-weight: 500;
}

.details {
  display: block;
  overflow-wrap: anywhere;
}

.actor {
  text-align: right;
}

.more {
  width: 100%;
  border-top: 1px solid var(--border);
  border-radius: 0;
}

.loading-row {
  height: 52px;
  margin: 12px 16px;
}

@media (max-width: 900px) {
  .columns {
    display: none;
  }

  /* Телефон: имя и кнопка, ниже — роль и статус в одну строку; логин и последний вход — в диалоге. */
  .person-row {
    grid-template-columns: max-content max-content minmax(0, 1fr) auto;
    grid-template-areas:
      'who who who btn'
      'role status . .';
    gap: 6px 10px;
  }

  .who {
    grid-area: who;
  }

  .person-row .btn {
    grid-area: btn;
  }

  .role {
    grid-area: role;
    padding-left: 44px;
    color: var(--text-2);
  }

  .status {
    grid-area: status;
  }

  .login,
  .last {
    display: none;
  }

  .event-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 2px;
  }

  .actor {
    text-align: left;
  }
}
</style>
