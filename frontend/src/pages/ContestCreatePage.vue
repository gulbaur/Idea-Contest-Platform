<script setup>
// Создание конкурса (только организатор; маршрут и сервер проверяют роль).
// Сроки вводятся в часовом поясе браузера и отправляются в UTC (D-032, D-050).
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import { api } from '../lib/api.js'
import { serverNow, syncServerTime } from '../lib/clock.js'
import { confirmAction } from '../lib/confirm.js'
import { formatDateTime, localInputToIso, timezoneLabel, toLocalInput } from '../lib/format.js'
import { t, tn } from '../lib/i18n.js'
import { notify } from '../lib/notify.js'
import { newRequestId } from '../lib/requestId.js'

const TOPIC_MAX = 200
const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

const router = useRouter()

const topic = ref('')
const submissionInput = ref('')
const votingInput = ref('')
const employees = ref(null)
const employeesError = ref(null)
const selected = ref(new Set())
const touched = ref(false)
const pending = ref(false)
const serverError = ref('')
// Один идентификатор на эту форму: повтор после сбоя сети не создаст второй конкурс (D-031).
let requestId = newRequestId()

// Подпись — t(`contests.create.preset.${key}`) в шаблоне: меняется вместе с языком (D-065).
const PRESETS = [
  { key: 'demo3', submission: 3 * MINUTE, voting: 6 * MINUTE },
  { key: 'demo10', submission: 10 * MINUTE, voting: 20 * MINUTE },
  { key: 'days2', submission: 2 * DAY, voting: 4 * DAY },
  { key: 'week', submission: 7 * DAY, voting: 10 * DAY },
]

function applyPreset(preset) {
  const now = serverNow()
  // Округляем вверх до минуты: поле ввода не хранит секунды.
  const base = Math.ceil(now / MINUTE) * MINUTE
  submissionInput.value = toLocalInput(base + preset.submission)
  votingInput.value = toLocalInput(base + preset.voting)
}

async function loadEmployees() {
  employeesError.value = null
  try {
    const [list, health] = await Promise.all([api.employees(), api.health().catch(() => null)])
    if (health) syncServerTime(health.server_time)
    employees.value = list
    selected.value = new Set(list.map((person) => person.id)) // по умолчанию — все (D-009)
  } catch (failure) {
    employeesError.value = failure
  }
}

onMounted(() => {
  applyPreset(PRESETS[2])
  loadEmployees()
})

// Поиск по имени и логину (D-062): когда сотрудников много, список длинный.
// «Выбрать всех» при поиске выбирает (или снимает) только найденных.
const peopleQuery = ref('')
const shownEmployees = computed(() => {
  const needle = peopleQuery.value.trim().toLocaleLowerCase('ru')
  if (!needle) return employees.value ?? []
  return (employees.value ?? []).filter((person) =>
    [person.display_name, person.login].some((text) => text.toLocaleLowerCase('ru').includes(needle)),
  )
})
const allSelected = computed(
  () => shownEmployees.value.length > 0 && shownEmployees.value.every((person) => selected.value.has(person.id)),
)

function toggle(id) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAll() {
  const next = new Set(selected.value)
  for (const person of shownEmployees.value) {
    if (allSelected.value) next.delete(person.id)
    else next.add(person.id)
  }
  selected.value = next
}

const submissionIso = computed(() => localInputToIso(submissionInput.value))
const votingIso = computed(() => localInputToIso(votingInput.value))

const errors = computed(() => {
  const result = {}
  const value = topic.value.trim()
  if (!value) result.topic = t('contests.create.error.topic')
  else if (value.length > TOPIC_MAX) result.topic = t('contests.create.error.topicTooLong', { max: TOPIC_MAX })
  if (!submissionIso.value) result.submission = t('contests.create.error.dateRequired')
  else if (Date.parse(submissionIso.value) <= serverNow()) result.submission = t('contests.create.error.submissionPast')
  if (!votingIso.value) result.voting = t('contests.create.error.dateRequired')
  else if (submissionIso.value && Date.parse(votingIso.value) <= Date.parse(submissionIso.value)) {
    result.voting = t('contests.create.error.votingOrder')
  }
  if (!selected.value.size) result.participants = t('contests.create.error.participants')
  return result
})

function durationText(ms) {
  if (ms <= 0) return '—'
  const minutes = Math.round(ms / MINUTE)
  if (minutes < 60) return tn('contests.create.minutes', minutes)
  const hours = Math.round(ms / HOUR)
  if (hours < 48) return tn('contests.create.hours', hours)
  const days = Math.round(ms / DAY)
  return tn('contests.create.days', days)
}

const summary = computed(() => {
  if (!submissionIso.value || !votingIso.value) return null
  const start = serverNow()
  return {
    submission: durationText(Date.parse(submissionIso.value) - start),
    voting: durationText(Date.parse(votingIso.value) - Date.parse(submissionIso.value)),
    shortRound: Date.parse(votingIso.value) - start < 2 * DAY,
  }
})

async function submit() {
  touched.value = true
  serverError.value = ''
  if (Object.keys(errors.value).length || pending.value) return

  const confirmed = await confirmAction({
    title: t('contests.create.confirm.title'),
    message: t('contests.create.confirm.message', {
      topic: topic.value.trim(),
      submission: formatDateTime(submissionIso.value),
      voting: formatDateTime(votingIso.value),
      count: selected.value.size,
    }),
    confirmText: t('contests.create.confirm.confirmText'),
  })
  if (!confirmed) return

  pending.value = true
  try {
    const contest = await api.createContest({
      topic: topic.value.trim(),
      submission_deadline: submissionIso.value,
      voting_deadline: votingIso.value,
      participant_ids: [...selected.value],
      client_request_id: requestId,
    })
    notify.success(t('contests.create.created'))
    await router.push({ name: 'contest', params: { id: contest.id } })
  } catch (failure) {
    if (failure.detail?.code === 'request_id_reused') {
      // Первая отправка формы уже создала конкурс (ответ потерялся), а данные с тех пор
      // изменились. Новый идентификатор: следующее нажатие создаст конкурс с новыми данными (D-053).
      requestId = newRequestId()
      serverError.value = t('contests.create.error.requestReused')
    } else {
      serverError.value = failure.message
    }
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="container page narrow">
    <RouterLink class="back" :to="{ name: 'contests' }"><Icon name="arrow-left" /> {{ t('contests.create.back') }}</RouterLink>
    <header class="page-header">
      <div>
        <h1>{{ t('contests.create.title') }}</h1>
        <p class="subtitle">{{ t('contests.create.subtitle') }}</p>
      </div>
    </header>

    <form class="stack" novalidate @submit.prevent="submit">
      <section class="card stack">
        <div class="field">
          <div class="row">
            <label for="topic">{{ t('contests.create.topic') }}</label>
            <span class="counter" :class="{ over: topic.trim().length > TOPIC_MAX }">
              {{ topic.trim().length }}/{{ TOPIC_MAX }}
            </span>
          </div>
          <input
            id="topic"
            v-model="topic"
            class="input"
            maxlength="400"
            :placeholder="t('contests.create.topicPlaceholder')"
            :aria-invalid="touched && !!errors.topic"
            :disabled="pending"
          />
          <span v-if="touched && errors.topic" class="field-error">{{ errors.topic }}</span>
        </div>
      </section>

      <section class="card stack">
        <div class="card-title">
          <Icon name="calendar" />
          <h2>{{ t('contests.create.deadlines') }}</h2>
          <span class="faint">{{ t('contests.create.timezone', { zone: timezoneLabel() }) }}</span>
        </div>

        <div class="presets" role="group" :aria-label="t('contests.create.presets')">
          <button
            v-for="preset in PRESETS"
            :key="preset.key"
            class="btn btn-sm"
            type="button"
            :disabled="pending"
            @click="applyPreset(preset)"
          >
            {{ t(`contests.create.preset.${preset.key}`) }}
          </button>
        </div>

        <div class="dates">
          <div class="field">
            <label for="submission">{{ t('contests.create.submissionUntil') }}</label>
            <input
              id="submission"
              v-model="submissionInput"
              class="input"
              type="datetime-local"
              :aria-invalid="touched && !!errors.submission"
              :disabled="pending"
            />
            <span v-if="touched && errors.submission" class="field-error">{{ errors.submission }}</span>
            <span v-else-if="summary" class="hint">{{ t('contests.create.submissionLasts', { duration: summary.submission }) }}</span>
          </div>
          <div class="field">
            <label for="voting">{{ t('contests.create.votingUntil') }}</label>
            <input
              id="voting"
              v-model="votingInput"
              class="input"
              type="datetime-local"
              :aria-invalid="touched && !!errors.voting"
              :disabled="pending"
            />
            <span v-if="touched && errors.voting" class="field-error">{{ errors.voting }}</span>
            <span v-else-if="summary" class="hint">{{ t('contests.create.votingLasts', { duration: summary.voting }) }}</span>
          </div>
        </div>

        <div class="notice">
          <Icon name="bell" class="icon" />
          <span>
            {{ t('contests.create.reminder') }}
            <template v-if="summary?.shortRound"> {{ t('contests.create.shortRound') }}
              <code class="mono">REMINDER_LEAD</code> {{ t('contests.create.shortRoundAfter') }}</template>
          </span>
        </div>
      </section>

      <section class="card">
        <div class="card-title">
          <Icon name="users" />
          <h2>{{ t('contests.create.participants') }}</h2>
          <span v-if="employees" class="faint">{{ t('contests.create.selected', { selected: selected.size, total: employees.length }) }}</span>
          <span class="spacer" />
          <button v-if="employees?.length" class="btn btn-ghost btn-sm" type="button" @click="toggleAll">
            {{
              peopleQuery.trim()
                ? t(allSelected ? 'contests.create.unselectFound' : 'contests.create.selectFound')
                : t(allSelected ? 'contests.create.unselectAll' : 'contests.create.selectAll')
            }}
          </button>
        </div>
        <label v-if="employees?.length" class="search people-search">
          <span class="sr-only">{{ t('contests.create.searchEmployee') }}</span>
          <Icon name="search" :size="16" class="icon" />
          <input v-model="peopleQuery" class="input" type="search" :placeholder="t('contests.create.searchEmployeePlaceholder')" />
        </label>

        <EmptyState v-if="employeesError" tone="error" icon="alert" :title="t('contests.create.employeesError')" :text="employeesError.message">
          <button class="btn" type="button" @click="loadEmployees"><Icon name="refresh" /> {{ t('common.retry') }}</button>
        </EmptyState>
        <div v-else-if="!employees" class="people">
          <div v-for="n in 4" :key="n" class="skeleton" style="height: 44px" />
        </div>
        <div v-else class="people">
          <label v-for="person in shownEmployees" :key="person.id" class="person" :class="{ on: selected.has(person.id) }">
            <input type="checkbox" :checked="selected.has(person.id)" :disabled="pending" @change="toggle(person.id)" />
            <span>
              <strong>{{ person.display_name }}</strong>
              <small class="faint">{{ person.login }}</small>
            </span>
          </label>
        </div>
        <p v-if="touched && errors.participants" class="field-error top-gap">{{ errors.participants }}</p>
        <p class="faint top-gap">{{ t('contests.create.participantsNote') }}</p>
      </section>

      <div v-if="serverError" class="notice notice-danger" role="alert">
        <Icon name="alert" class="icon" /> {{ serverError }}
      </div>

      <div class="row submit-row">
        <RouterLink class="btn btn-ghost" :to="{ name: 'contests' }">{{ t('common.cancel') }}</RouterLink>
        <button class="btn btn-primary btn-lg" type="submit" :disabled="pending || !employees">
          <span v-if="pending" class="spinner" aria-hidden="true" />
          <Icon v-else name="check" />
          {{ t('contests.create.submit') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.narrow {
  max-width: 820px;
}

.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 14px;
  color: var(--text-2);
  font-weight: 600;
  font-size: var(--text-md);
}

.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dates {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.people {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.people-search {
  margin-bottom: 12px;
}

.person {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.person.on {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.person input {
  width: 18px;
  height: 18px;
  accent-color: var(--primary);
}

.person span {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.top-gap {
  margin-top: 12px;
}

.submit-row {
  justify-content: flex-end;
}

@media (max-width: 640px) {
  .dates {
    grid-template-columns: minmax(0, 1fr);
  }

  .submit-row .btn {
    flex: 1;
  }
}
</style>
