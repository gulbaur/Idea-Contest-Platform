// Вход, список конкурсов, создание конкурса, почта и правила маршрутов.
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../lib/api.js'
import { answer } from '../lib/confirm.js'
import { realtime } from '../lib/connection.js'
import { toasts } from '../lib/notify.js'
import { clearSession, session } from '../lib/session.js'
import { NOW, USERS, button, contestIn, mountAt, signIn } from '../test/helpers.js'

vi.mock('../lib/api.js', async (importOriginal) => {
  const real = await importOriginal()
  const fn = () => vi.fn()
  return {
    ...real,
    api: {
      login: fn(), logout: fn(), me: fn(), health: fn(), contests: fn(), contest: fn(), employees: fn(),
      createContest: fn(), emails: fn(), participants: fn(),
    },
  }
})
const { api } = await import('../lib/api.js')

let wrapper
let router

beforeEach(() => {
  vi.clearAllMocks()
  api.health.mockResolvedValue({ server_time: new Date(NOW).toISOString() })
})

afterEach(() => {
  toasts.splice(0)
  answer(false)
  wrapper?.unmount()
  clearSession()
})

describe('маршруты', () => {
  it('без входа любая страница ведёт на вход с возвратом после входа', async () => {
    ;({ wrapper, router } = await mountAt('/mail'))
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/mail')
  })

  it('создание конкурса — только организатору', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([])
    ;({ wrapper, router } = await mountAt('/contests/new'))
    expect(router.currentRoute.value.name).toBe('contests')
  })

  it('неизвестный адрес — страница «не найдена»', async () => {
    signIn(USERS.anna)
    ;({ wrapper } = await mountAt('/что-то/другое'))
    expect(wrapper.text()).toContain('Страница не найдена')
  })
})

describe('вход', () => {
  it('успешный вход сохраняет сессию вкладки и возвращает на нужную страницу', async () => {
    api.login.mockResolvedValue({ token: 't-1', user: USERS.anna })
    api.emails.mockResolvedValue([])
    api.contests.mockResolvedValue([])
    ;({ wrapper, router } = await mountAt('/login?redirect=/mail'))

    await wrapper.find('#login').setValue('  anna ')
    await wrapper.find('#password').setValue('demo-password')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(api.login).toHaveBeenCalledWith('anna', 'demo-password')
    expect(session.token).toBe('t-1')
    expect(sessionStorage.getItem('idea-contest.session')).toContain('t-1')
    expect(router.currentRoute.value.path).toBe('/mail')
  })

  it('неверный пароль — сообщение сервера, вход не сохраняется', async () => {
    api.login.mockRejectedValue(new ApiError(401, 'Неверный логин или пароль'))
    ;({ wrapper } = await mountAt('/login'))
    await wrapper.find('#login').setValue('anna')
    await wrapper.find('#password').setValue('wrong')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('Неверный логин или пароль')
    expect(session.token).toBeNull()
  })

  it('кнопка демо-аккаунта входит под ним', async () => {
    api.login.mockResolvedValue({ token: 't-2', user: USERS.organizer })
    api.contests.mockResolvedValue([])
    ;({ wrapper } = await mountAt('/login'))
    await button(wrapper, 'Борис Котов').trigger('click')
    await flushPromises()
    expect(api.login).toHaveBeenCalledWith('boris', 'demo-password')
  })
})

describe('список конкурсов', () => {
  const contests = [
    { ...contestIn('finished'), id: 1, topic: 'Прошлый' },
    { ...contestIn('submission'), id: 2, topic: 'Новый' },
    { ...contestIn('voting'), id: 3, topic: 'Идёт голосование' },
  ]

  it('идущие сверху, фильтр по этапу, организатору — кнопка создания', async () => {
    signIn(USERS.organizer)
    api.contests.mockResolvedValue(contests)
    ;({ wrapper } = await mountAt('/contests'))

    const topics = () => wrapper.findAll('.contest-card h3').map((h) => h.text())
    expect(topics()).toEqual(['Идёт голосование', 'Новый', 'Прошлый'])
    expect(wrapper.text()).toContain('Новый конкурс')

    await button(wrapper, 'Завершены').trigger('click')
    expect(topics()).toEqual(['Прошлый'])
  })

  it('участник без конкурсов видит пояснение; новый конкурс появляется по сигналу', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValueOnce([]).mockResolvedValueOnce([contests[1]])
    ;({ wrapper } = await mountAt('/contests'))
    expect(wrapper.text()).toContain('Вас пока не пригласили в конкурс')
    expect(wrapper.text()).not.toContain('Новый конкурс')

    realtime.emit({ type: 'contests_changed' })
    await flushPromises()
    expect(wrapper.findAll('.contest-card h3').map((h) => h.text())).toEqual(['Новый'])
  })

  it('ошибка загрузки — сообщение и «Повторить»', async () => {
    signIn(USERS.anna)
    api.contests.mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.')).mockResolvedValueOnce([])
    ;({ wrapper } = await mountAt('/contests'))
    expect(wrapper.text()).toContain('Не удалось загрузить конкурсы')
    await button(wrapper, 'Повторить').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Вас пока не пригласили')
  })
})

describe('создание конкурса', () => {
  const employees = [
    { id: 2, login: 'anna', display_name: 'Анна Смирнова' },
    { id: 3, login: 'boris', display_name: 'Борис Котов' },
  ]

  async function openForm() {
    signIn(USERS.organizer)
    api.employees.mockResolvedValue(employees)
    api.contest.mockResolvedValue(null)
    ;({ wrapper, router } = await mountAt('/contests/new'))
  }

  it('проверяет поля до отправки', async () => {
    await openForm()
    await button(wrapper, 'Снять все').trigger('click')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.text()).toContain('Укажите тему конкурса')
    expect(wrapper.text()).toContain('Выберите хотя бы одного участника')
    expect(api.createContest).not.toHaveBeenCalled()
  })

  it('отправляет сроки в UTC и выбранных участников после подтверждения; повтор — тот же запрос', async () => {
    await openForm()
    await wrapper.find('#topic').setValue('  Обеды  ')
    await button(wrapper, 'Демо: 3 + 3 мин').trigger('click')
    await wrapper.findAll('.person input')[1].setValue(false) // без Бориса

    api.createContest
      .mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.'))
      .mockResolvedValueOnce({ ...contestIn('submission'), id: 9 })

    await wrapper.find('form').trigger('submit')
    expect(document.body.textContent).toContain('Сроки и список участников после создания изменить нельзя')
    answer(true)
    await flushPromises()
    expect(wrapper.text()).toContain('Нет связи с сервером.')

    await wrapper.find('form').trigger('submit')
    answer(true)
    await flushPromises()

    const [first, second] = api.createContest.mock.calls.map(([payload]) => payload)
    expect(first.topic).toBe('Обеды')
    expect(first.participant_ids).toEqual([2])
    expect(first.submission_deadline).toMatch(/Z$/)
    expect(Date.parse(first.voting_deadline) - Date.parse(first.submission_deadline)).toBe(3 * 60_000)
    expect(second.client_request_id).toBe(first.client_request_id) // повтор не создаст второй конкурс
    expect(router.currentRoute.value.path).toBe('/contests/9')
  })

  it('отмена в диалоге — ничего не отправляется', async () => {
    await openForm()
    await wrapper.find('#topic').setValue('Тема')
    await wrapper.find('form').trigger('submit')
    answer(false)
    await flushPromises()
    expect(api.createContest).not.toHaveBeenCalled()
  })
})

describe('почта', () => {
  const letter = (id, recipient, kind, subject) => ({
    id,
    contest_id: 7,
    contest_topic: 'Как улучшить офис',
    recipient,
    to_address: `${recipient.display_name}@example.com`,
    kind,
    subject,
    body: `Здравствуйте!\n\nТекст письма ${id}`,
    created_at: new Date(NOW - id * 60_000).toISOString(),
  })

  it('участник видит свои письма и читает выбранное', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([contestIn('finished')])
    api.emails.mockResolvedValue([
      letter(1, USERS.anna, 'final', 'Ваша идея победила в конкурсе «Как улучшить офис»'),
      letter(2, USERS.anna, 'reminder_voting', 'Напоминание: голосование закрывается'),
    ])
    ;({ wrapper } = await mountAt('/mail'))

    expect(wrapper.text()).toContain('Письма, отправленные вам')
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(2)
    expect(wrapper.find('.meta').text()).not.toContain('Анна Смирнова') // своё имя в списке не нужно

    await wrapper.find('button[data-letter-id="1"]').trigger('click')
    expect(wrapper.find('.letter .body').text()).toContain('Текст письма 1')

    await button(wrapper, 'Напоминания').trigger('click')
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(1)
  })

  it('организатор видит журнал с получателями; фильтр по конкурсу уходит на сервер', async () => {
    signIn(USERS.organizer)
    api.contests.mockResolvedValue([contestIn('finished')])
    api.emails.mockResolvedValue([letter(3, USERS.boris, 'final', 'Итоги конкурса')])
    ;({ wrapper } = await mountAt('/mail?contest=7'))

    expect(api.emails).toHaveBeenCalledWith({ contest_id: 7 })
    expect(wrapper.text()).toContain('Журнал всех писем')
    expect(wrapper.find('.meta').text()).toContain('Борис Котов')
  })

  it('новое письмо появляется по сигналу без перезагрузки; пустой ящик — пояснение', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([])
    api.emails.mockResolvedValueOnce([]).mockResolvedValueOnce([letter(4, USERS.anna, 'final', 'Итоги')])
    ;({ wrapper } = await mountAt('/mail'))
    expect(wrapper.text()).toContain('Писем пока нет')

    realtime.emit({ type: 'mail_changed' })
    await flushPromises()
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(1)
  })
})
