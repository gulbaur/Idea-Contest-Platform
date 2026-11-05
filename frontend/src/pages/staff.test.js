// Сотрудники и доступ (D-062): раздел администратора, первый вход по ссылке, маршруты по ролям.
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../lib/api.js'
import { answer } from '../lib/confirm.js'
import { toasts } from '../lib/notify.js'
import { clearSession, session } from '../lib/session.js'
import { NOW, USERS, button, mountAt, signIn } from '../test/helpers.js'

vi.mock('../lib/api.js', async (importOriginal) => {
  const real = await importOriginal()
  const fn = () => vi.fn()
  return {
    ...real,
    api: {
      health: fn(), me: fn(), contests: fn(), emails: fn(), staff: fn(), inviteStaff: fn(), updateStaff: fn(),
      disableStaff: fn(), enableStaff: fn(), issueSetupLink: fn(), audit: fn(), setupCheck: fn(), setup: fn(),
    },
  }
})
const { api } = await import('../lib/api.js')

const ADMIN = { id: 9, login: 'admin', display_name: 'Администратор', role: 'admin' }
const iso = (ms) => new Date(ms).toISOString()
const person = (id, login, name, extra = {}) => ({
  id,
  login,
  display_name: name,
  email: `${login}@example.com`,
  role: 'employee',
  status: 'active',
  created_at: iso(NOW - 86_400_000),
  last_login_at: null,
  active_contests: [],
  ...extra,
})
const STAFF = [
  person(9, 'admin', 'Администратор', { role: 'admin' }),
  person(2, 'anna', 'Анна Смирнова', { active_contests: ['Как сделать офис уютнее'] }),
  person(3, 'boris', 'Борис Котов', { status: 'disabled' }),
  person(4, 'petr', 'Пётр Сидоров', { status: 'invited' }),
]

let wrapper
let router

beforeEach(() => {
  vi.clearAllMocks()
  api.health.mockResolvedValue({ server_time: iso(NOW) })
  api.staff.mockResolvedValue(STAFF)
  api.contests.mockResolvedValue([])
})

afterEach(() => {
  toasts.splice(0)
  answer(false)
  wrapper?.unmount()
  clearSession()
  window.history.replaceState(null, '', '/')
})

describe('маршруты по ролям', () => {
  it('администратор попадает в «Сотрудники», а не в конкурсы', async () => {
    signIn(ADMIN)
    ;({ wrapper, router } = await mountAt('/contests'))
    expect(router.currentRoute.value.name).toBe('employees')
    ;({ wrapper, router } = await mountAt('/'))
    expect(router.currentRoute.value.name).toBe('employees')
  })

  it('организатору и сотруднику раздел «Сотрудники» недоступен', async () => {
    for (const user of [USERS.organizer, USERS.anna]) {
      signIn(user)
      ;({ wrapper, router } = await mountAt('/employees'))
      expect(router.currentRoute.value.name).toBe('contests')
      wrapper.unmount()
    }
    wrapper = null
    expect(api.staff).not.toHaveBeenCalled()
  })
})

describe('раздел «Сотрудники»', () => {
  it('список со статусами, поиск и фильтр', async () => {
    signIn(ADMIN)
    ;({ wrapper } = await mountAt('/employees'))
    const rows = () => wrapper.findAll('.person-row').map((row) => row.attributes('data-login'))
    expect(rows()).toEqual(['admin', 'anna', 'boris', 'petr'])
    expect(wrapper.find('[data-login="boris"]').text()).toContain('Отключён')
    expect(wrapper.find('[data-login="petr"]').text()).toContain('Приглашён')

    await wrapper.find('input[type="search"]').setValue('котов')
    expect(rows()).toEqual(['boris'])
    await wrapper.find('input[type="search"]').setValue('')
    await button(wrapper, 'Приглашены').trigger('click')
    expect(rows()).toEqual(['petr'])
  })

  it('приглашение показывает одноразовую ссылку с токеном после «#»', async () => {
    signIn(ADMIN)
    api.inviteStaff.mockResolvedValue({
      user: person(5, 'lena', 'Елена Ким', { status: 'invited' }),
      setup: { token: 'секрет-токен', expires_at: iso(NOW + 72 * 3_600_000) },
    })
    ;({ wrapper } = await mountAt('/employees'))
    await button(wrapper, 'Пригласить сотрудника').trigger('click')
    await wrapper.find('#staff-name').setValue('Елена Ким')
    await wrapper.find('#staff-login').setValue('lena')
    await wrapper.find('#staff-email').setValue('lena@example.com')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(api.inviteStaff).toHaveBeenCalledWith({
      display_name: 'Елена Ким',
      login: 'lena',
      email: 'lena@example.com',
      role: 'employee',
    })
    expect(wrapper.find('#setup-link').element.value).toBe(`${window.location.origin}/setup#секрет-токен`)
  })

  it('роль участника идущего конкурса не меняется — с объяснением', async () => {
    signIn(ADMIN)
    ;({ wrapper } = await mountAt('/employees'))
    await wrapper.find('[data-login="anna"] button').trigger('click')
    expect(wrapper.find('#staff-role').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('«Как сделать офис уютнее»')
  })

  it('отключение — только после подтверждения', async () => {
    signIn(ADMIN)
    api.disableStaff.mockResolvedValue(person(4, 'petr', 'Пётр Сидоров', { status: 'disabled' }))
    ;({ wrapper } = await mountAt('/employees'))
    await wrapper.find('[data-login="petr"] button').trigger('click')

    await button(wrapper, 'Отключить доступ').trigger('click')
    await flushPromises()
    answer(false)
    await flushPromises()
    expect(api.disableStaff).not.toHaveBeenCalled()

    await button(wrapper, 'Отключить доступ').trigger('click')
    await flushPromises()
    answer(true)
    await flushPromises()
    expect(api.disableStaff).toHaveBeenCalledWith(4)
  })
})

describe('первый вход по ссылке', () => {
  it('токен читается из «#», убирается из адреса; после пароля — вход', async () => {
    window.history.replaceState(null, '', '/setup#abc123')
    api.setupCheck.mockResolvedValue({ login: 'petr', display_name: 'Пётр Сидоров' })
    api.setup.mockResolvedValue({ token: 't-petr', user: { ...USERS.anna, login: 'petr' } })
    ;({ wrapper, router } = await mountAt('/setup'))
    await flushPromises()

    expect(api.setupCheck).toHaveBeenCalledWith('abc123')
    expect(window.location.hash).toBe('')
    expect(wrapper.text()).toContain('Здравствуйте, Пётр Сидоров!')

    await wrapper.find('#new-password').setValue('короткий')
    await wrapper.find('#repeat-password').setValue('короткий')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('не короче 10 символов')
    expect(api.setup).not.toHaveBeenCalled()

    await wrapper.find('#new-password').setValue('длинный-пароль-2026')
    await wrapper.find('#repeat-password').setValue('длинный-пароль-2026')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(api.setup).toHaveBeenCalledWith('abc123', 'длинный-пароль-2026')
    expect(session.token).toBe('t-petr')
  })

  it('устаревшая ссылка — понятное объяснение', async () => {
    window.history.replaceState(null, '', '/setup#old')
    api.setupCheck.mockRejectedValue(new ApiError(404, 'Ссылка недействительна'))
    ;({ wrapper } = await mountAt('/setup'))
    await flushPromises()
    expect(wrapper.text()).toContain('Ссылка недействительна')
    expect(wrapper.find('form').exists()).toBe(false)
  })
})
