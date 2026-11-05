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
  return { ...real, api: { updatePreferences: vi.fn(), changePassword: vi.fn(), health: vi.fn(), me: vi.fn() } }
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

// Переключатели — кнопки с role="radio" внутри группы с подписью (D-066).
const choice = (label, text) =>
  wrapper
    .findAll(`[role="radiogroup"][aria-labelledby="${label}"] [role="radio"]`)
    .find((button) => button.text().includes(text))

describe('настройки вида', () => {
  it('выбор темы, шрифта и размера текста применяется сразу и сохраняется на сервере', async () => {
    signIn(USERS.anna)
    const stored = { theme: 'light', font: 'inter', locale: 'ru', text_size: 'medium' } // как на сервере: правки копятся
    api.updatePreferences.mockImplementation(async (changes) => ({
      ...USERS.anna,
      preferences: Object.assign(stored, changes),
    }))
    ;({ wrapper } = await mountAt('/settings'))

    await choice('theme-label', 'Тёмная').trigger('click')
    expect(root.dataset.theme).toBe('dark') // ещё до ответа сервера
    await flushPromises()
    expect(api.updatePreferences).toHaveBeenCalledWith({ theme: 'dark' })
    expect(choice('theme-label', 'Тёмная').attributes('aria-checked')).toBe('true')

    await wrapper.find('#font-select').setValue('golos')
    await flushPromises()
    expect(root.dataset.font).toBe('golos')

    await choice('size-label', 'Большой').trigger('click')
    await flushPromises()
    expect(root.dataset.size).toBe('large')
    expect(session.user.preferences).toMatchObject({ theme: 'dark', font: 'golos', text_size: 'large' })
    expect(JSON.parse(localStorage.getItem('idea-contest.preferences'))).toEqual({
      theme: 'dark',
      font: 'golos',
      locale: 'ru',
      text_size: 'large',
    })
    expect(wrapper.text()).toContain('Сохранено')
  })

  it('если сервер не сохранил настройку — прежний вид и сообщение', async () => {
    signIn(USERS.anna)
    api.updatePreferences.mockRejectedValue(new ApiError(0, 'Нет связи с сервером.'))
    ;({ wrapper } = await mountAt('/settings'))

    await choice('theme-label', 'Тёмная').trigger('click')
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
    expect(normalize({ theme: 'pink', font: 'comic', locale: 'de', text_size: 'huge' })).toEqual({ theme: 'system', font: 'inter', locale: 'ru', text_size: 'medium' })
    expect(normalize(undefined)).toEqual({ theme: 'system', font: 'inter', locale: 'ru', text_size: 'medium' })
  })

  it('пароль меняется в окне; поля проверяются до отправки', async () => {
    signIn(USERS.anna)
    api.changePassword.mockResolvedValue(null)
    ;({ wrapper } = await mountAt('/settings'))
    expect(wrapper.find('#current-password').exists()).toBe(false) // формы на странице нет

    const open = wrapper.findAll('button').find((b) => b.text() === 'Сменить пароль')
    await open.trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)

    await wrapper.find('#current-password').setValue('старый-пароль')
    await wrapper.find('#next-password').setValue('новый-пароль-2026')
    await wrapper.find('#repeat-password').setValue('другой-пароль-2026')
    await wrapper.find('[role="dialog"] form').trigger('submit')
    expect(wrapper.text()).toContain('Новые пароли не совпадают')
    expect(api.changePassword).not.toHaveBeenCalled()

    await wrapper.find('#repeat-password').setValue('новый-пароль-2026')
    await wrapper.find('[role="dialog"] form').trigger('submit')
    await flushPromises()
    expect(api.changePassword).toHaveBeenCalledWith('старый-пароль', 'новый-пароль-2026')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(toasts.at(-1).text).toContain('Пароль изменён')
  })
})
