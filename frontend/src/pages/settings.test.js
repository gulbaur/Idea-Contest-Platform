// Настройки вида (D-060): применяются сразу, сохраняются у пользователя, при ошибке — откат.
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../lib/api.js'
import { toasts } from '../lib/notify.js'
import { applyPreferences, normalize, preferences } from '../lib/preferences.js'
import { clearSession, session, setSession } from '../lib/session.js'
import { USERS, mountAt, signIn } from '../test/helpers.js'

vi.mock('../lib/api.js', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, api: { updatePreferences: vi.fn(), health: vi.fn(), me: vi.fn() } }
})
const { api } = await import('../lib/api.js')

const root = document.documentElement
let wrapper

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  applyPreferences({ theme: 'light', font: 'inter' })
})

afterEach(() => {
  toasts.splice(0)
  wrapper?.unmount()
  clearSession()
})

const radio = (name, value) => wrapper.find(`input[name="${name}"][value="${value}"]`)

describe('настройки вида', () => {
  it('выбор темы и шрифта применяется сразу и сохраняется на сервере', async () => {
    signIn(USERS.anna)
    const stored = { theme: 'light', font: 'inter', locale: 'ru' } // как на сервере: правки копятся
    api.updatePreferences.mockImplementation(async (changes) => ({
      ...USERS.anna,
      preferences: Object.assign(stored, changes),
    }))
    ;({ wrapper } = await mountAt('/settings'))

    await radio('theme', 'dark').trigger('change')
    expect(root.dataset.theme).toBe('dark') // ещё до ответа сервера
    await flushPromises()
    expect(api.updatePreferences).toHaveBeenCalledWith({ theme: 'dark' })

    await radio('font', 'golos').trigger('change')
    await flushPromises()
    expect(root.dataset.font).toBe('golos')
    expect(session.user.preferences).toMatchObject({ theme: 'dark', font: 'golos' })
    expect(JSON.parse(localStorage.getItem('idea-contest.preferences'))).toEqual({ theme: 'dark', font: 'golos' })
    expect(wrapper.text()).toContain('Сохранено')
  })

  it('если сервер не сохранил настройку — прежний вид и сообщение', async () => {
    signIn(USERS.anna)
    api.updatePreferences.mockRejectedValue(new ApiError(0, 'Нет связи с сервером.'))
    ;({ wrapper } = await mountAt('/settings'))

    await radio('theme', 'dark').trigger('change')
    await flushPromises()

    expect(root.dataset.theme).toBe('light')
    expect(preferences.theme).toBe('light')
    expect(toasts.at(-1).text).toContain('Настройка не сохранена')
  })

  it('вход применяет настройки этого пользователя', () => {
    setSession({ token: 't', user: { ...USERS.boris, preferences: { theme: 'dark', font: 'plex', locale: 'ru' } } })
    expect(root.dataset.theme).toBe('dark')
    expect(root.dataset.font).toBe('plex')
  })

  it('неизвестные значения из старого кеша заменяются значениями по умолчанию', () => {
    expect(normalize({ theme: 'pink', font: 'comic' })).toEqual({ theme: 'system', font: 'inter' })
    expect(normalize(undefined)).toEqual({ theme: 'system', font: 'inter' })
  })
})
