// Правила списка конкурсов (D-061): что показать в колонке «Участие», что «ждёт действия»,
// поиск и порядок. Без интерфейса — проверяется тестами отдельно от страницы.
import { countOf } from './format.js'
import { phaseAt } from './clock.js'

const IDEAS = ['идея', 'идеи', 'идей']
const IDEAS_GEN = ['идею', 'идеи', 'идей']

/**
 * Состояние участия для строки списка.
 * tone: action — нужно что-то сделать; done — сделано; muted — справочно.
 * Организатор видит только счётчики, которые сервер ему отдал (D-005); участник — своё участие.
 */
export function participation(contest, phase, organizer) {
  if (organizer) {
    const stats = contest.stats ?? {}
    if (phase === 'submission') {
      return {
        tone: 'muted',
        text: countOf(stats.ideas_count ?? 0, IDEAS),
        detail: `участников: ${stats.participants_count ?? 0}`,
      }
    }
    return {
      tone: 'muted',
      text: `проголосовали ${stats.voters_count ?? 0} из ${stats.participants_count ?? 0}`,
      detail: countOf(stats.ideas_count ?? 0, IDEAS),
    }
  }

  const my = contest.my ?? { ideas_count: 0, votes_count: 0, can_vote: false }
  if (phase === 'submission') {
    return my.ideas_count > 0
      ? { tone: 'done', text: `Вы подали ${countOf(my.ideas_count, IDEAS_GEN)}` }
      : { tone: 'action', text: 'Подайте идею' }
  }
  if (phase === 'voting') {
    if (my.votes_count > 0) return { tone: 'done', text: `Вы проголосовали: ${countOf(my.votes_count, ['голос', 'голоса', 'голосов'])}` }
    if (my.can_vote) return { tone: 'action', text: 'Нужно проголосовать' }
    return { tone: 'muted', text: 'Чужих идей нет' }
  }
  return { tone: 'muted', text: 'Итоги подведены' }
}

/** Участнику нужно что-то сделать в этом конкурсе прямо сейчас. */
export function needsAction(contest, phase, organizer) {
  return !organizer && participation(contest, phase, organizer).tone === 'action'
}

/** Ближайший срок идущего конкурса или окончание голосования завершённого (мс). */
function keyMoment(contest, phase) {
  return Date.parse(phase === 'submission' ? contest.submission_deadline : contest.voting_deadline)
}

export const SORTS = [
  { key: 'deadline', label: 'Ближайший срок' },
  { key: 'newest', label: 'Сначала новые' },
  { key: 'oldest', label: 'Сначала старые' },
]

/**
 * Конкурсы с фазой в нужном порядке.
 * «Ближайший срок»: сначала идущие — у кого срок раньше; затем завершённые — недавние выше.
 */
export function arrange(contests, nowMs, { query = '', phase = 'all', sort = 'deadline' } = {}) {
  const needle = query.trim().toLocaleLowerCase('ru')
  const items = contests
    .map((contest) => ({ contest, phase: phaseAt(contest, nowMs) }))
    .filter((item) => phase === 'all' || item.phase === phase)
    .filter((item) => !needle || item.contest.topic.toLocaleLowerCase('ru').includes(needle))

  const created = (item) => Date.parse(item.contest.created_at)
  const byId = (a, b) => b.contest.id - a.contest.id
  const compare = {
    newest: (a, b) => created(b) - created(a) || byId(a, b),
    oldest: (a, b) => created(a) - created(b) || -byId(a, b),
    deadline: (a, b) => {
      const doneA = a.phase === 'finished'
      const doneB = b.phase === 'finished'
      if (doneA !== doneB) return doneA ? 1 : -1
      const diff = keyMoment(a.contest, a.phase) - keyMoment(b.contest, b.phase)
      return (doneA ? -diff : diff) || byId(a, b)
    },
  }[sort]
  return items.sort(compare)
}

/** Доля прошедшего времени конкурса (0…1) и доля, которую занимает приём идей. */
export function timeline(contest, nowMs) {
  const start = Date.parse(contest.created_at)
  const middle = Date.parse(contest.submission_deadline)
  const end = Date.parse(contest.voting_deadline)
  const total = Math.max(1, end - start)
  return {
    split: Math.min(1, Math.max(0, (middle - start) / total)),
    progress: Math.min(1, Math.max(0, (nowMs - start) / total)),
  }
}
