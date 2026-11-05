// Экраны на английском (D-065): нет русского текста, кроме данных (темы, имена, идеи).
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { setLocale } from '../lib/i18n.js'
import { clearSession } from '../lib/session.js'
import { NOW, SCHEDULE, STATS, USERS, contestIn, idea, mountAt, signIn, snapshot } from '../test/helpers.js'

vi.mock('../lib/api.js', async (importOriginal) => {
  const real = await importOriginal()
  const fn = () => vi.fn()
  return {
    ...real,
    api: {
      health: fn(), me: fn(), contests: fn(), contest: fn(), emails: fn(), participants: fn(), unreadCount: fn(),
      markRead: fn(), employees: fn(),
    },
  }
})
const { api } = await import('../lib/api.js')

// Данные в тестах — по-русски; их убираем, остальное должно быть без кириллицы.
const DATA = [/Как улучшить офис/g, /Анна Смирнова|Борис Котов|Организатор/g, /Идея \d+|Описание: Идея \d+/g]
const russianLeft = (text) => DATA.reduce((rest, pattern) => rest.replace(pattern, ''), text).match(/[А-Яа-яЁё]+/g)

let wrapper

beforeEach(() => {
  vi.clearAllMocks()
  setLocale('en')
  api.health.mockResolvedValue({ server_time: new Date(NOW).toISOString() })
  api.unreadCount.mockResolvedValue({ count: 0 })
})

afterEach(() => {
  wrapper?.unmount()
  clearSession()
  setLocale('ru')
})

describe('английский интерфейс', () => {
  it('список конкурсов', async () => {
    signIn(USERS.organizer)
    api.contests.mockResolvedValue([contestIn('submission'), { ...contestIn('finished'), id: 8 }])
    ;({ wrapper } = await mountAt('/contests'))
    expect(wrapper.find('h1').text()).toBe('Contests')
    expect(russianLeft(wrapper.text())).toBeNull()
  })

  it('страница конкурса организатора во время голосования', async () => {
    signIn(USERS.organizer)
    api.contest.mockResolvedValue(
      snapshot('voting', { ideas: [idea(1, 'Идея 1', { votes_count: 2 }), idea(2, 'Идея 2', { votes_count: 1 })], stats: STATS, schedule: SCHEDULE }),
    )
    api.participants.mockResolvedValue([{ id: 2, display_name: 'Анна Смирнова' }])
    ;({ wrapper } = await mountAt('/contests/7'))
    await flushPromises()
    expect(wrapper.text()).toContain('Voting')
    expect(russianLeft(wrapper.text())).toBeNull()
  })

  it('пустые «Входящие»', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([])
    api.emails.mockResolvedValue([])
    ;({ wrapper } = await mountAt('/mail'))
    expect(wrapper.find('h1').text()).toBe('Inbox')
    expect(russianLeft(wrapper.text())).toBeNull()
  })
})
