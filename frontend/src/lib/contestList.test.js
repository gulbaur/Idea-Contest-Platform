// Правила списка конкурсов (D-061): участие, «ждут действия», поиск, порядок, шкала времени.
import { describe, expect, it } from 'vitest'

import { arrange, needsAction, participation, timeline } from './contestList.js'

const NOW = Date.parse('2026-05-10T09:00:00Z')
const H = 3_600_000
const at = (ms) => new Date(ms).toISOString()
const contest = (id, topic, createdH, submissionH, votingH, extra = {}) => ({
  id,
  topic,
  created_at: at(NOW + createdH * H),
  submission_deadline: at(NOW + submissionH * H),
  voting_deadline: at(NOW + votingH * H),
  ...extra,
})

describe('participation — колонка «Участие»', () => {
  const my = (ideas, votes, canVote = false) => ({ my: { ideas_count: ideas, votes_count: votes, can_vote: canVote } })

  it('участник: подача — «Подайте идею» или сколько подано', () => {
    expect(participation(my(0, 0), 'submission', false)).toEqual({ tone: 'action', text: 'Подайте идею' })
    expect(participation(my(1, 0), 'submission', false).text).toBe('Вы подали 1 идею')
    expect(participation(my(5, 0), 'submission', false).text).toBe('Вы подали 5 идей')
  })

  it('участник: голосование — нужно, сделано или не за что', () => {
    expect(participation(my(0, 0, true), 'voting', false).tone).toBe('action')
    expect(participation(my(0, 2, true), 'voting', false)).toEqual({ tone: 'done', text: 'Вы проголосовали: 2 голоса' })
    expect(participation(my(3, 0, false), 'voting', false)).toEqual({ tone: 'muted', text: 'Чужих идей нет' })
  })

  it('«ждут действия» — только у участника и только когда действие возможно', () => {
    expect(needsAction(my(0, 0, true), 'voting', false)).toBe(true)
    expect(needsAction(my(0, 0, false), 'voting', false)).toBe(false)
    expect(needsAction(my(0, 0), 'finished', false)).toBe(false)
    expect(needsAction({ stats: { participants_count: 3, ideas_count: 0, voters_count: null } }, 'submission', true)).toBe(false)
  })

  it('организатор: счётчики; проголосовавшие — с начала голосования', () => {
    const stats = { stats: { participants_count: 12, ideas_count: 8, voters_count: 5 } }
    expect(participation(stats, 'submission', true)).toEqual({ tone: 'muted', text: '8 идей', detail: 'участников: 12' })
    expect(participation(stats, 'voting', true)).toEqual({ tone: 'muted', text: 'проголосовали 5 из 12', detail: '8 идей' })
  })
})

describe('arrange — поиск и порядок', () => {
  const list = [
    contest(1, 'Обеды', -100, -50, -10), // завершён давно
    contest(2, 'Офис уютнее', -2, 30, 60), // подача, срок через 30 ч
    contest(3, 'Совещания', -50, -1, 5), // голосование, срок через 5 ч
    contest(4, 'Парковка', -30, -20, -1), // завершён недавно
  ]
  const ids = (items) => items.map((item) => item.contest.id)

  it('ближайший срок: идущие по сроку, затем завершённые — недавние выше', () => {
    expect(ids(arrange(list, NOW))).toEqual([3, 2, 4, 1])
  })

  it('сначала новые и сначала старые — по времени создания', () => {
    expect(ids(arrange(list, NOW, { sort: 'newest' }))).toEqual([2, 4, 3, 1])
    expect(ids(arrange(list, NOW, { sort: 'oldest' }))).toEqual([1, 3, 4, 2])
  })

  it('фильтр по этапу и поиск без учёта регистра', () => {
    expect(ids(arrange(list, NOW, { phase: 'finished' }))).toEqual([4, 1])
    expect(ids(arrange(list, NOW, { query: '  офис ' }))).toEqual([2])
    expect(ids(arrange(list, NOW, { query: 'нет такого' }))).toEqual([])
  })
})

describe('timeline — шкала времени конкурса', () => {
  it('доля приёма идей и прошедшего времени, в пределах 0…1', () => {
    const item = contest(1, 'x', -10, 10, 30)
    expect(timeline(item, NOW)).toEqual({ split: 0.5, progress: 0.25 })
    expect(timeline(item, NOW + 100 * H).progress).toBe(1)
    expect(timeline(item, NOW - 100 * H).progress).toBe(0)
  })
})
