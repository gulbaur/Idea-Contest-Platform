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
      login: fn(), logout: fn(), me: fn(), demo: fn(), health: fn(), contests: fn(), contest: fn(), employees: fn(),
      createContest: fn(), emails: fn(), participants: fn(), journal: fn(), unreadCount: fn(), markRead: fn(),
      markAllRead: fn(),
    },
  }
})
const { api } = await import('../lib/api.js')

let wrapper
let router

beforeEach(() => {
  vi.clearAllMocks()
  api.health.mockResolvedValue({ server_time: new Date(NOW).toISOString() })
  api.demo.mockResolvedValue({
    enabled: true,
    password: 'demo-password',
    accounts: [
      { login: 'organizer', display_name: 'Организатор', role: 'organizer' },
      { login: 'boris', display_name: 'Борис Котов', role: 'employee' },
    ],
  })
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

  it('вне демо-режима нет ни демо-аккаунтов, ни пароля', async () => {
    api.demo.mockResolvedValue({ enabled: false, password: null, accounts: [] })
    ;({ wrapper } = await mountAt('/login'))
    expect(wrapper.text()).not.toContain('Демо-аккаунты')
    expect(wrapper.text()).not.toContain('demo-password')
    expect(wrapper.find('form').exists()).toBe(true)
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

    const topics = () => wrapper.findAll('.contest-row h3').map((h) => h.text())
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
    expect(wrapper.findAll('.contest-row h3').map((h) => h.text())).toEqual(['Новый'])
  })

  it('участнику сверху — «Ждут вашего действия»; в строке — его участие', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([
      { ...contests[1], my: { ideas_count: 2, votes_count: 0, can_vote: false } },
      { ...contests[2], my: { ideas_count: 0, votes_count: 0, can_vote: true } },
      { ...contests[0], my: { ideas_count: 1, votes_count: 3, can_vote: false } },
    ])
    ;({ wrapper } = await mountAt('/contests'))

    const groups = wrapper.findAll('section.list').map((section) => ({
      title: section.find('h2').text(),
      topics: section.findAll('.contest-row h3').map((h) => h.text()),
    }))
    expect(groups).toEqual([
      { title: 'Ждут вашего действия', topics: ['Идёт голосование'] },
      { title: 'Идут', topics: ['Новый'] },
      { title: 'Завершены', topics: ['Прошлый'] },
    ])
    expect(wrapper.text()).toContain('Нужно проголосовать')
    expect(wrapper.text()).toContain('Вы подали 2 идеи')
  })

  it('поиск по теме; если ничего нет — пояснение и сброс', async () => {
    signIn(USERS.organizer)
    api.contests.mockResolvedValue(contests)
    ;({ wrapper } = await mountAt('/contests'))

    await wrapper.find('input[type="search"]').setValue('голосов')
    expect(wrapper.findAll('.contest-row h3').map((h) => h.text())).toEqual(['Идёт голосование'])

    await wrapper.find('input[type="search"]').setValue('обеды')
    expect(wrapper.text()).toContain('Ничего не найдено')
    await button(wrapper, 'Сбросить поиск').trigger('click')
    expect(wrapper.findAll('.contest-row')).toHaveLength(3)
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

  it('поиск участников: «Выбрать найденных» не трогает остальных', async () => {
    await openForm()
    await button(wrapper, 'Снять все').trigger('click')
    await wrapper.find('input[type="search"]').setValue('котов')
    expect(wrapper.findAll('.person strong').map((n) => n.text())).toEqual(['Борис Котов'])
    await button(wrapper, 'Выбрать найденных').trigger('click')
    await wrapper.find('input[type="search"]').setValue('')
    expect(wrapper.text()).toContain('выбрано 1 из 2')
    expect(wrapper.findAll('.person input').map((input) => input.element.checked)).toEqual([false, true])
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

  it('идентификатор уже использован с другими данными — следующая отправка с новым', async () => {
    await openForm()
    await wrapper.find('#topic').setValue('Обеды')
    const reused = { message: 'Этот запрос уже выполнен с другими данными', code: 'request_id_reused' }
    api.createContest
      .mockRejectedValueOnce(new ApiError(409, reused.message, reused))
      .mockResolvedValueOnce({ ...contestIn('submission'), id: 10 })

    await wrapper.find('form').trigger('submit')
    answer(true)
    await flushPromises()
    expect(wrapper.text()).toContain('Конкурс по первой отправке этой формы уже создан')
    await wrapper.find('form').trigger('submit')
    answer(true)
    await flushPromises()

    const [first, second] = api.createContest.mock.calls.map(([payload]) => payload)
    expect(second.client_request_id).not.toBe(first.client_request_id)
    expect(router.currentRoute.value.path).toBe('/contests/10')
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
  const letter = (id, recipient, kind, subject, extra = {}) => ({
    id,
    contest_id: 7,
    contest_topic: 'Как улучшить офис',
    recipient,
    to_address: `${recipient.login}@example.com`,
    kind,
    subject,
    body: `Здравствуйте!\n\nТекст письма ${id}`,
    created_at: new Date(NOW - id * 60_000).toISOString(),
    read_at: null,
    ...extra,
  })

  beforeEach(() => {
    api.unreadCount.mockResolvedValue({ count: 0 })
    api.markRead.mockResolvedValue(null)
  })

  it('«Входящие»: свои письма; открытое письмо становится прочитанным', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([contestIn('finished')])
    api.emails.mockResolvedValue([
      letter(1, USERS.anna, 'final', 'Ваша идея победила в конкурсе «Как улучшить офис»'),
      letter(2, USERS.anna, 'invitation', 'Вас пригласили в конкурс идей', { read_at: new Date(NOW).toISOString() }),
    ])
    ;({ wrapper } = await mountAt('/mail'))

    expect(wrapper.find('h1').text()).toBe('Входящие')
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(2)
    expect(wrapper.find('[data-letter-id="1"]').classes()).toContain('unread')
    expect(wrapper.find('[data-letter-id="2"]').classes()).not.toContain('unread')
    expect(wrapper.find('[data-letter-id="2"]').text()).toContain('Приглашение')

    await wrapper.find('button[data-letter-id="1"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.letter .body').text()).toContain('Текст письма 1')
    expect(api.markRead).toHaveBeenCalledWith(1)
    expect(wrapper.find('[data-letter-id="1"]').classes()).not.toContain('unread')

    await wrapper.find('button[data-letter-id="2"]').trigger('click')
    expect(api.markRead).toHaveBeenCalledTimes(1) // уже прочитанное повторно не отмечается
  })

  it('фильтры конкурса и «Непрочитанные» уходят на сервер', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([contestIn('finished')])
    api.emails.mockResolvedValue([])
    ;({ wrapper } = await mountAt('/mail?contest=7'))
    expect(api.emails).toHaveBeenCalledWith({ contest_id: 7, unread: undefined, limit: 50 })

    await button(wrapper, 'Непрочитанные').trigger('click')
    await flushPromises()
    expect(api.emails).toHaveBeenLastCalledWith({ contest_id: 7, unread: true, limit: 50 })
    expect(wrapper.text()).toContain('Непрочитанных писем нет')
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

  it('письма догружаются порциями: «Показать ещё» продолжает с последнего письма', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([])
    const first = Array.from({ length: 50 }, (_, n) => letter(n + 1, USERS.anna, 'final', `Письмо ${n + 1}`))
    api.emails.mockResolvedValueOnce(first).mockResolvedValueOnce([letter(51, USERS.anna, 'final', 'Письмо 51')])
    ;({ wrapper } = await mountAt('/mail'))
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(50)

    await button(wrapper, 'Показать ещё').trigger('click')
    await flushPromises()

    expect(api.emails).toHaveBeenLastCalledWith({
      contest_id: undefined,
      unread: undefined,
      limit: 50,
      before_time: first[49].created_at,
      before_id: 50,
    })
    expect(wrapper.findAll('button[data-letter-id]')).toHaveLength(51)
    expect(wrapper.text()).not.toContain('Показать ещё')
  })

  it('журнал рассылки — организатору: все письма с получателями, письмо открывается в окне', async () => {
    signIn(USERS.organizer)
    api.contests.mockResolvedValue([contestIn('finished')])
    api.journal.mockResolvedValue([letter(3, USERS.boris, 'final', 'Итоги конкурса')])
    ;({ wrapper } = await mountAt('/journal?contest=7'))

    expect(api.journal).toHaveBeenCalledWith({ contest_id: 7, kind: undefined, recipient: undefined, limit: 50 })
    expect(wrapper.find('[data-journal-id="3"]').text()).toContain('Борис Котов')
    await wrapper.find('[data-journal-id="3"]').trigger('click')
    expect(wrapper.find('[role="dialog"] pre.body').text()).toContain('Текст письма 3')
  })

  it('журнал рассылки участнику недоступен', async () => {
    signIn(USERS.anna)
    api.contests.mockResolvedValue([])
    ;({ wrapper, router } = await mountAt('/journal'))
    expect(router.currentRoute.value.name).toBe('contests')
    expect(api.journal).not.toHaveBeenCalled()
  })
})
