// Клиент API: заголовок входа, понятные сообщения об ошибках, реакция на 401.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api, ApiError, messageFor, onUnauthorized } from './api.js'
import { clearSession, setSession } from './session.js'

function respond(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => (body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body)),
  }
}

describe('api', () => {
  let fetchMock

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    clearSession()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    onUnauthorized(() => {})
  })

  it('отправляет токен вкладки и JSON', async () => {
    setSession({ token: 'tab-token', user: { id: 1, role: 'employee' } })
    fetchMock.mockResolvedValue(respond(201, { id: 7 }))

    const result = await api.submitIdea(3, { title: 'А', description: 'Б', client_request_id: 'x' })

    expect(result).toEqual({ id: 7 })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/contests/3/ideas')
    expect(init.method).toBe('POST')
    expect(init.headers.Authorization).toBe('Bearer tab-token')
    expect(JSON.parse(init.body)).toEqual({ title: 'А', description: 'Б', client_request_id: 'x' })
  })

  it('пустые параметры запроса не попадают в адрес', async () => {
    fetchMock.mockResolvedValue(respond(200, []))
    await api.emails({ contest_id: undefined })
    await api.emails({ contest_id: 5 })
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/emails', '/api/emails?contest_id=5'])
  })

  it('204 — без тела', async () => {
    fetchMock.mockResolvedValue(respond(204))
    await expect(api.revokeVote(4)).resolves.toBeNull()
  })

  it('ошибка сервера превращается в ApiError с текстом и деталями', async () => {
    const current = { id: 4, title: 'Новое', version: 3 }
    fetchMock.mockResolvedValue(respond(409, { detail: { message: 'Идея уже изменена в другой вкладке', current } }))

    const failure = await api.updateIdea(4, {}).catch((error) => error)

    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.status).toBe(409)
    expect(failure.message).toBe('Идея уже изменена в другой вкладке')
    expect(failure.detail.current).toEqual(current)
  })

  it('нет связи с сервером — понятное сообщение, код 0', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const failure = await api.contests().catch((error) => error)
    expect(failure.status).toBe(0)
    expect(failure.message).toMatch(/Нет связи с сервером/)
  })

  it('401 на запрос с токеном — вызывает обработчик окончания сессии; при входе — нет', async () => {
    const handler = vi.fn()
    onUnauthorized(handler)
    fetchMock.mockResolvedValue(respond(401, { detail: 'Требуется вход' }))

    await api.login('anna', 'wrong').catch(() => {})
    expect(handler).not.toHaveBeenCalled() // токена нет — это просто неверный пароль

    setSession({ token: 'old', user: { id: 1, role: 'employee' } })
    await api.contests().catch(() => {})
    expect(handler).toHaveBeenCalledTimes(1)
  })

  it('ответ не-JSON (например, страница ошибки прокси)', async () => {
    fetchMock.mockResolvedValue(respond(502, '<html>Bad Gateway</html>'))
    const failure = await api.contests().catch((error) => error)
    expect(failure.message).toBe('Ошибка на сервере. Попробуйте ещё раз чуть позже.')
  })
})

describe('messageFor — ошибки проверки данных (422)', () => {
  it.each([
    [{ type: 'string_too_short', loc: ['body', 'title'] }, 'Название: поле не может быть пустым.'],
    [{ type: 'string_too_long', loc: ['body', 'topic'], ctx: { max_length: 200 } }, 'Тема: не больше 200 символов.'],
    [{ type: 'too_short', loc: ['body', 'participant_ids'] }, 'Участники: выберите хотя бы одного.'],
    [
      { type: 'value_error', loc: ['body', 'login'], msg: 'Value error, Текст содержит недопустимый символ NUL' },
      'Логин: Текст содержит недопустимый символ NUL.',
    ],
  ])('%o', (error, text) => {
    expect(messageFor(422, { detail: [error] })).toBe(text)
  })

  it('строковая ошибка сервера показывается как есть', () => {
    expect(messageFor(422, { detail: 'Срок окончания приёма идей должен быть в будущем' })).toBe(
      'Срок окончания приёма идей должен быть в будущем',
    )
  })
})
