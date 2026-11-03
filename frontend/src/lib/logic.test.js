// Логика без интерфейса: свежесть снимков, время и фазы, форматирование, идентификатор запроса.
import { describe, expect, it } from 'vitest'

import { nextDeadline, phaseAt, serverNow, syncServerTime } from './clock.js'
import { countOf, formatCountdown, localInputToIso, plural, toLocalInput } from './format.js'
import { isFresher } from './freshness.js'
import { newRequestId } from './requestId.js'

const snap = (revision, serverTime) => ({ revision, server_time: serverTime })

describe('isFresher — защита от устаревших снимков', () => {
  it('первый снимок применяется всегда', () => {
    expect(isFresher(snap(1, '2026-01-01T00:00:00Z'), null)).toBe(true)
  })

  it('больший revision новее, меньший — устарел, даже если пришёл позже', () => {
    const shown = snap(5, '2026-01-01T00:00:05Z')
    expect(isFresher(snap(6, '2026-01-01T00:00:01Z'), shown)).toBe(true)
    expect(isFresher(snap(4, '2026-01-01T00:00:09Z'), shown)).toBe(false)
  })

  it('при равном revision решает время сервера: снимок «до срока» не откатывает «после срока»', () => {
    const afterDeadline = snap(7, '2026-01-01T10:00:00.500Z')
    expect(isFresher(snap(7, '2026-01-01T09:59:59.900Z'), afterDeadline)).toBe(false)
    expect(isFresher(snap(7, '2026-01-01T10:00:01Z'), afterDeadline)).toBe(true)
    expect(isFresher(snap(7, '2026-01-01T10:00:00.500Z'), afterDeadline)).toBe(true)
  })
})

describe('часы и фазы', () => {
  const contest = { submission_deadline: '2026-01-01T10:00:00Z', voting_deadline: '2026-01-01T12:00:00Z' }
  const at = (iso) => Date.parse(iso)

  it('ровно в момент срока раунд уже закрыт — как на сервере', () => {
    expect(phaseAt(contest, at('2026-01-01T09:59:59.999Z'))).toBe('submission')
    expect(phaseAt(contest, at('2026-01-01T10:00:00Z'))).toBe('voting')
    expect(phaseAt(contest, at('2026-01-01T11:59:59.999Z'))).toBe('voting')
    expect(phaseAt(contest, at('2026-01-01T12:00:00Z'))).toBe('finished')
  })

  it('ближайший срок', () => {
    expect(nextDeadline(contest, at('2026-01-01T09:00:00Z'))).toBe(at('2026-01-01T10:00:00Z'))
    expect(nextDeadline(contest, at('2026-01-01T10:00:00Z'))).toBe(at('2026-01-01T12:00:00Z'))
    expect(nextDeadline(contest, at('2026-01-01T12:00:00Z'))).toBeNull()
  })

  it('время сервера учитывает отставание часов компьютера', () => {
    const browserNow = Date.now()
    syncServerTime(new Date(browserNow + 90_000).toISOString(), browserNow) // сервер на 90 с впереди
    expect(serverNow() - Date.now()).toBeGreaterThan(89_000)
    expect(serverNow() - Date.now()).toBeLessThan(91_000)
    syncServerTime(new Date().toISOString())
  })
})

describe('форматирование', () => {
  it('склонения', () => {
    expect([0, 1, 2, 5, 11, 21, 22, 112].map((n) => countOf(n, ['голос', 'голоса', 'голосов']))).toEqual([
      '0 голосов', '1 голос', '2 голоса', '5 голосов', '11 голосов', '21 голос', '22 голоса', '112 голосов',
    ])
    expect(plural(3, ['идея', 'идеи', 'идей'])).toBe('идеи')
  })

  it('обратный отсчёт', () => {
    expect(formatCountdown(9_000)).toBe('0:09')
    expect(formatCountdown(4 * 60_000 + 7_000)).toBe('4:07')
    expect(formatCountdown(3 * 3_600_000 + 5 * 60_000)).toBe('3 ч 05 мин')
    expect(formatCountdown(2 * 86_400_000 + 3 * 3_600_000)).toBe('2 д 3 ч')
    expect(formatCountdown(-5_000)).toBe('0:00')
  })

  it('поле datetime-local: местное время туда и обратно, на сервер — UTC с «Z»', () => {
    const moment = Date.parse('2026-03-10T08:30:00Z')
    const local = toLocalInput(moment)
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(localInputToIso(local)).toBe('2026-03-10T08:30:00.000Z')
    expect(localInputToIso('')).toBeNull()
    expect(localInputToIso('не дата')).toBeNull()
  })
})

describe('идентификатор запроса', () => {
  it('UUID v4 и без crypto.randomUUID (адрес не localhost и не https)', () => {
    const fallback = { getRandomValues: (array) => globalThis.crypto.getRandomValues(array) }
    const ids = new Set(Array.from({ length: 50 }, () => newRequestId(fallback)))
    expect(ids.size).toBe(50)
    for (const id of ids) expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })
})
