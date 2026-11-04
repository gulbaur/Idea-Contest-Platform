// Общее для тестов компонентов: снимки конкурса, вход, монтирование с маршрутизатором.
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'

import ConfirmHost from '../components/ConfirmHost.vue'
import ToastHost from '../components/ToastHost.vue'
import { createAppRouter } from '../router.js'
import { setSession } from '../lib/session.js'

export const NOW = Date.parse('2026-05-10T09:00:00Z')
const HOUR = 3_600_000
const iso = (ms) => new Date(ms).toISOString()

export const USERS = {
  organizer: { id: 1, login: 'organizer', display_name: 'Организатор', role: 'organizer' },
  anna: { id: 2, login: 'anna', display_name: 'Анна Смирнова', role: 'employee' },
  boris: { id: 3, login: 'boris', display_name: 'Борис Котов', role: 'employee' },
}

export function signIn(user) {
  setSession({ token: `token-${user.login}`, user })
}

/** Сроки конкурса так, чтобы в момент NOW шла нужная фаза. */
export function contestIn(phase, extra = {}) {
  const shift = { submission: 0, voting: -1.5 * HOUR, finished: -3 * HOUR }[phase]
  return {
    id: 7,
    topic: 'Как улучшить офис',
    created_at: iso(NOW - HOUR + shift),
    submission_deadline: iso(NOW + HOUR + shift),
    voting_deadline: iso(NOW + 2 * HOUR + shift),
    phase,
    ...extra,
  }
}

export function idea(id, title, extra = {}) {
  const mine = Boolean(extra.is_mine) // у чужих идей сервер не отдаёт время и номер правки (D-058)
  return {
    id,
    title,
    description: `Описание: ${title}`,
    submitted_at: iso(NOW - 10 * 60_000 + id * 1000),
    updated_at: mine ? iso(NOW - 10 * 60_000 + id * 1000) : null,
    version: mine ? 1 : null,
    is_mine: false,
    author: null,
    votes_count: null,
    voted_by_me: false,
    ...extra,
  }
}

export function snapshot(phase, { ideas = [], revision = 1, stats = null, schedule = null, winner = null } = {}) {
  return {
    contest: contestIn(phase),
    revision,
    server_time: iso(NOW),
    ideas,
    stats,
    schedule,
    winner_idea_id: winner,
  }
}

export const STATS = { participants_count: 4, ideas_count: 2, voters_count: 1, votes_count: 3 }
export const SCHEDULE = [
  { kind: 'remind_submission', run_at: iso(NOW - HOUR), status: 'skipped', finished_at: iso(NOW - HOUR), note: 'раунд короче срока напоминания' },
  { kind: 'remind_voting', run_at: iso(NOW), status: 'done', finished_at: iso(NOW), note: 'писем: 2' },
  { kind: 'finalize', run_at: iso(NOW + HOUR), status: 'pending', finished_at: null, note: null },
]

/** Смонтировать приложение на нужном адресе: страница + уведомления + диалог. */
export async function mountAt(path) {
  const router = createAppRouter(createMemoryHistory())
  router.push(path)
  await router.isReady()
  const wrapper = mount(
    {
      components: { ToastHost, ConfirmHost },
      template: '<RouterView /><ToastHost /><ConfirmHost />',
    },
    { global: { plugins: [router] }, attachTo: document.body },
  )
  await flushPromises()
  return { wrapper, router }
}

/** Promise, который тест разрешает сам — чтобы проверить состояние «запрос в пути». */
export function deferred() {
  let resolve
  let reject
  const promise = new Promise((ok, fail) => {
    resolve = ok
    reject = fail
  })
  return { promise, resolve, reject }
}

export const button = (wrapper, text, within = wrapper) =>
  within.findAll('button').find((candidate) => candidate.text().includes(text))
