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
import { formatDateTime, localInputToIso, plural, timezoneLabel, toLocalInput } from '../lib/format.js'
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

const PRESETS = [
  { label: 'Демо: 3 + 3 мин', submission: 3 * MINUTE, voting: 6 * MINUTE },
  { label: 'Демо: 10 + 10 мин', submission: 10 * MINUTE, voting: 20 * MINUTE },
  { label: '2 дня + 2 дня', submission: 2 * DAY, voting: 4 * DAY },
  { label: 'Неделя + 3 дня', submission: 7 * DAY, voting: 10 * DAY },
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

const allSelected = computed(() => employees.value?.length && selected.value.size === employees.value.length)

function toggle(id) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(employees.value.map((person) => person.id))
}

const submissionIso = computed(() => localInputToIso(submissionInput.value))
const votingIso = computed(() => localInputToIso(votingInput.value))

const errors = computed(() => {
  const result = {}
  const value = topic.value.trim()
  if (!value) result.topic = 'Укажите тему конкурса'
  else if (value.length > TOPIC_MAX) result.topic = `Не больше ${TOPIC_MAX} символов`
  if (!submissionIso.value) result.submission = 'Укажите дату и время'
  else if (Date.parse(submissionIso.value) <= serverNow()) result.submission = 'Срок должен быть в будущем'
  if (!votingIso.value) result.voting = 'Укажите дату и время'
  else if (submissionIso.value && Date.parse(votingIso.value) <= Date.parse(submissionIso.value)) {
    result.voting = 'Голосование должно закончиться позже приёма идей'
  }
  if (!selected.value.size) result.participants = 'Выберите хотя бы одного участника'
  return result
})

function durationText(ms) {
  if (ms <= 0) return '—'
  const minutes = Math.round(ms / MINUTE)
  if (minutes < 60) return `${minutes} ${plural(minutes, ['минута', 'минуты', 'минут'])}`
  const hours = Math.round(ms / HOUR)
  if (hours < 48) return `${hours} ${plural(hours, ['час', 'часа', 'часов'])}`
  const days = Math.round(ms / DAY)
  return `${days} ${plural(days, ['день', 'дня', 'дней'])}`
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
    title: 'Создать конкурс?',
    message:
      `«${topic.value.trim()}»\n` +
      `Приём идей — до ${formatDateTime(submissionIso.value)}\n` +
      `Голосование — до ${formatDateTime(votingIso.value)}\n` +
      `Участников: ${selected.value.size}\n\n` +
      'Сроки и список участников после создания изменить нельзя.',
    confirmText: 'Создать',
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
    notify.success('Конкурс создан — участники уже видят его в своём списке.')
    await router.push({ name: 'contest', params: { id: contest.id } })
  } catch (failure) {
    if (failure.detail?.code === 'request_id_reused') {
      // Первая отправка формы уже создала конкурс (ответ потерялся), а данные с тех пор
      // изменились. Новый идентификатор: следующее нажатие создаст конкурс с новыми данными (D-053).
      requestId = newRequestId()
      serverError.value =
        'Конкурс по первой отправке этой формы уже создан — он есть в списке конкурсов. ' +
        'Нажмите «Создать конкурс» ещё раз, чтобы создать ещё один с новыми данными.'
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
    <RouterLink class="back" :to="{ name: 'contests' }"><Icon name="arrow-left" /> Все конкурсы</RouterLink>
    <header class="page-header">
      <div>
        <h1>Новый конкурс</h1>
        <p class="subtitle">Тема, два срока и участники. Раунды переключатся сами в назначенное время.</p>
      </div>
    </header>

    <form class="stack" novalidate @submit.prevent="submit">
      <section class="card stack">
        <div class="field">
          <div class="row">
            <label for="topic">Тема конкурса</label>
            <span class="counter" :class="{ over: topic.trim().length > TOPIC_MAX }">
              {{ topic.trim().length }}/{{ TOPIC_MAX }}
            </span>
          </div>
          <input
            id="topic"
            v-model="topic"
            class="input"
            maxlength="400"
            placeholder="Например: как сделать офис удобнее"
            :aria-invalid="touched && !!errors.topic"
            :disabled="pending"
          />
          <span v-if="touched && errors.topic" class="field-error">{{ errors.topic }}</span>
        </div>
      </section>

      <section class="card stack">
        <div class="card-title">
          <Icon name="calendar" />
          <h2>Сроки</h2>
          <span class="faint">время вашего компьютера, {{ timezoneLabel() }}</span>
        </div>

        <div class="presets" role="group" aria-label="Быстрый выбор сроков">
          <button
            v-for="preset in PRESETS"
            :key="preset.label"
            class="btn btn-sm"
            type="button"
            :disabled="pending"
            @click="applyPreset(preset)"
          >
            {{ preset.label }}
          </button>
        </div>

        <div class="dates">
          <div class="field">
            <label for="submission">Приём идей — до</label>
            <input
              id="submission"
              v-model="submissionInput"
              class="input"
              type="datetime-local"
              :aria-invalid="touched && !!errors.submission"
              :disabled="pending"
            />
            <span v-if="touched && errors.submission" class="field-error">{{ errors.submission }}</span>
            <span v-else-if="summary" class="hint">длится {{ summary.submission }}, начинается сразу</span>
          </div>
          <div class="field">
            <label for="voting">Голосование — до</label>
            <input
              id="voting"
              v-model="votingInput"
              class="input"
              type="datetime-local"
              :aria-invalid="touched && !!errors.voting"
              :disabled="pending"
            />
            <span v-if="touched && errors.voting" class="field-error">{{ errors.voting }}</span>
            <span v-else-if="summary" class="hint">длится {{ summary.voting }}, затем итоги и письма</span>
          </div>
        </div>

        <div class="notice">
          <Icon name="bell" class="icon" />
          <span>
            За сутки до конца каждого раунда тем, кто ещё не участвовал, придёт напоминание. Если раунд короче
            суток, напоминания в нём не будет.
            <template v-if="summary?.shortRound"> Короткие сроки — для демонстрации: запустите сервис с небольшим
              <code class="mono">REMINDER_LEAD</code> (см. README).</template>
          </span>
        </div>
      </section>

      <section class="card">
        <div class="card-title">
          <Icon name="users" />
          <h2>Участники</h2>
          <span v-if="employees" class="faint">выбрано {{ selected.size }} из {{ employees.length }}</span>
          <span class="spacer" />
          <button v-if="employees?.length" class="btn btn-ghost btn-sm" type="button" @click="toggleAll">
            {{ allSelected ? 'Снять все' : 'Выбрать всех' }}
          </button>
        </div>

        <EmptyState v-if="employeesError" tone="error" icon="alert" title="Не удалось загрузить сотрудников" :text="employeesError.message">
          <button class="btn" type="button" @click="loadEmployees"><Icon name="refresh" /> Повторить</button>
        </EmptyState>
        <div v-else-if="!employees" class="people">
          <div v-for="n in 4" :key="n" class="skeleton" style="height: 44px" />
        </div>
        <div v-else class="people">
          <label v-for="person in employees" :key="person.id" class="person" :class="{ on: selected.has(person.id) }">
            <input type="checkbox" :checked="selected.has(person.id)" :disabled="pending" @change="toggle(person.id)" />
            <span>
              <strong>{{ person.display_name }}</strong>
              <small class="faint">{{ person.login }}</small>
            </span>
          </label>
        </div>
        <p v-if="touched && errors.participants" class="field-error top-gap">{{ errors.participants }}</p>
        <p class="faint top-gap">Только участники подают идеи, голосуют и получают письма. Организатор не участвует.</p>
      </section>

      <div v-if="serverError" class="notice notice-danger" role="alert">
        <Icon name="alert" class="icon" /> {{ serverError }}
      </div>

      <div class="row submit-row">
        <RouterLink class="btn btn-ghost" :to="{ name: 'contests' }">Отмена</RouterLink>
        <button class="btn btn-primary btn-lg" type="submit" :disabled="pending || !employees">
          <span v-if="pending" class="spinner" aria-hidden="true" />
          <Icon v-else name="check" />
          Создать конкурс
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
