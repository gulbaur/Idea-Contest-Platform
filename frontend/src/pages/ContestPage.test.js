// Страница конкурса: что видно каждой роли в каждой фазе и как работают действия.
// API подменён: здесь проверяется интерфейс, права и сроки проверяют тесты backend.
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '../lib/api.js'
import { answer } from '../lib/confirm.js'
import { realtime } from '../lib/connection.js'
import { toasts } from '../lib/notify.js'
import { clearSession } from '../lib/session.js'
import {
  NOW,
  SCHEDULE,
  STATS,
  USERS,
  button,
  contestIn,
  deferred,
  idea,
  mountAt,
  signIn,
  snapshot,
} from '../test/helpers.js'

vi.mock('../lib/api.js', async (importOriginal) => {
  const real = await importOriginal()
  const fn = () => vi.fn()
  return {
    ...real,
    api: {
      contest: fn(), participants: fn(), submitIdea: fn(), updateIdea: fn(), deleteIdea: fn(),
      vote: fn(), revokeVote: fn(), contests: fn(), emails: fn(), health: fn(), me: fn(),
    },
  }
})
const { api } = await import('../lib/api.js')

let wrapper

async function open(user, snap) {
  signIn(user)
  api.contest.mockResolvedValue(snap)
  api.participants.mockResolvedValue([{ id: 2, display_name: 'Анна Смирнова' }])
  ;({ wrapper } = await mountAt('/contests/7'))
  return wrapper
}

const cards = () => wrapper.findAll('article[data-idea-id]')
const cardOf = (title) => cards().find((card) => card.find('h3').text() === title)

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  toasts.splice(0)
  answer(false)
  wrapper?.unmount()
  clearSession()
})

describe('участник, приём идей', () => {
  const mine = idea(11, 'Велопарковка', { is_mine: true })

  it('видит форму и только свои идеи; голосовать нельзя', async () => {
    await open(USERS.anna, snapshot('submission', { ideas: [mine] }))

    expect(wrapper.text()).toContain('Новая идея')
    expect(cards()).toHaveLength(1)
    expect(cardOf('Велопарковка').text()).toContain('Ваша идея')
    expect(button(wrapper, 'Голосовать')).toBeUndefined()
    expect(button(wrapper, 'Изменить')).toBeDefined()
    expect(wrapper.text()).toContain('Идеи других участников скрыты до начала голосования')
    expect(wrapper.text()).toContain('поданная раньше') // правило победителя видно с начала (D-008)
  })

  it('подача: при сбое повтор с тем же client_request_id, после успеха — новый', async () => {
    await open(USERS.anna, snapshot('submission'))
    api.submitIdea
      .mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.'))
      .mockResolvedValueOnce({ id: 12 })
      .mockResolvedValueOnce({ id: 13 })

    async function send(title) {
      await wrapper.find('#new-idea-title').setValue(title)
      await wrapper.find('#new-idea-description').setValue('Текст')
      await wrapper.find('form.idea-form').trigger('submit')
      await flushPromises()
    }

    await send('Первая')
    expect(document.body.textContent).toContain('Нет связи с сервером.')
    await send('Первая')
    await send('Вторая')

    const ids = api.submitIdea.mock.calls.map(([, payload]) => payload.client_request_id)
    expect(ids[0]).toBe(ids[1]) // повтор после сбоя — тот же запрос
    expect(ids[2]).not.toBe(ids[1]) // новая идея — новый запрос
    expect(api.submitIdea.mock.calls[0]).toEqual([7, { title: 'Первая', description: 'Текст', client_request_id: ids[0] }])
  })

  it('идентификатор уже использован с другим текстом — форма получает новый, текст остаётся', async () => {
    await open(USERS.anna, snapshot('submission'))
    const reused = { message: 'Этот запрос уже выполнен с другими данными', code: 'request_id_reused' }
    api.submitIdea
      .mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.'))
      .mockRejectedValueOnce(new ApiError(409, reused.message, reused))
      .mockResolvedValueOnce({ id: 14 })

    await wrapper.find('#new-idea-title').setValue('Первая')
    await wrapper.find('#new-idea-description').setValue('Текст')
    await wrapper.find('form.idea-form').trigger('submit')
    await flushPromises()
    await wrapper.find('#new-idea-title').setValue('Исправленная') // ответ потерялся, текст поменяли
    await wrapper.find('form.idea-form').trigger('submit')
    await flushPromises()

    expect(document.body.textContent).toContain('Предыдущая отправка этой формы уже принята')
    expect(wrapper.find('#new-idea-title').element.value).toBe('Исправленная')
    await wrapper.find('form.idea-form').trigger('submit')
    await flushPromises()

    const ids = api.submitIdea.mock.calls.map(([, payload]) => payload.client_request_id)
    expect(ids[1]).toBe(ids[0])
    expect(ids[2]).not.toBe(ids[1]) // иначе форма навсегда застряла бы на 409
    expect(api.contest.mock.calls.length).toBeGreaterThan(1) // снимок перечитан — видна принятая идея
  })

  it('переход к другому конкурсу без пересоздания страницы — новая форма и новый идентификатор', async () => {
    signIn(USERS.anna)
    api.contest.mockImplementation(async (id) => ({ ...snapshot('submission'), contest: { ...contestIn('submission'), id } }))
    api.participants.mockResolvedValue([])
    let router
    ;({ wrapper, router } = await mountAt('/contests/7'))
    api.submitIdea.mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.')).mockResolvedValueOnce({ id: 15 })

    await wrapper.find('#new-idea-title').setValue('Для седьмого')
    await wrapper.find('#new-idea-description').setValue('Текст')
    await wrapper.find('form.idea-form').trigger('submit')
    await flushPromises()
    await router.push('/contests/8')
    await flushPromises()

    expect(wrapper.find('#new-idea-title').element.value).toBe('')
    await wrapper.find('#new-idea-title').setValue('Для восьмого')
    await wrapper.find('#new-idea-description').setValue('Текст')
    await wrapper.find('form.idea-form').trigger('submit')
    await flushPromises()

    const [[firstContest, first], [secondContest, second]] = api.submitIdea.mock.calls
    expect([firstContest, secondContest]).toEqual([7, 8])
    expect(second.client_request_id).not.toBe(first.client_request_id)
  })

  it('пустую идею не отправляет — показывает подсказку', async () => {
    await open(USERS.anna, snapshot('submission'))
    await wrapper.find('#new-idea-title').setValue('   ')
    await wrapper.find('form.idea-form').trigger('submit')
    expect(api.submitIdea).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Введите название идеи')
  })

  it('правка из другой вкладки: форма не подменяется на лету, при сохранении — актуальный текст', async () => {
    await open(USERS.anna, snapshot('submission', { ideas: [mine] }))
    await button(wrapper, 'Изменить').trigger('click')
    await wrapper.find('#edit-11-description').setValue('Моя правка')

    // Другая вкладка сохранила свою правку — пришёл сигнал, снимок перечитан.
    api.contest.mockResolvedValue(
      snapshot('submission', { revision: 2, ideas: [{ ...mine, title: 'Велопарковка (крытая)', version: 2 }] }),
    )
    realtime.emit({ type: 'contest_changed', contest_id: 7, revision: 2 })
    await flushPromises()

    expect(wrapper.find('#edit-11-title').element.value).toBe('Велопарковка') // набранное не пропало
    expect(wrapper.find('#edit-11-description').element.value).toBe('Моя правка')
    expect(wrapper.text()).toContain('Пока вы редактировали, идею изменили в другой вкладке')

    const current = { ...mine, title: 'Велопарковка (крытая)', version: 2 }
    api.updateIdea.mockRejectedValueOnce(
      new ApiError(409, 'Идея уже изменена в другой вкладке', { message: 'Идея уже изменена в другой вкладке', current }),
    )
    await wrapper.find('section.editing form').trigger('submit')
    await flushPromises()

    expect(api.updateIdea).toHaveBeenCalledWith(11, { title: 'Велопарковка', description: 'Моя правка', version: 1 })
    expect(wrapper.text()).toContain('Идею уже изменили в другой вкладке')
    expect(wrapper.find('#edit-11-title').element.value).toBe('Велопарковка (крытая)')

    api.updateIdea.mockResolvedValueOnce({ ...current, version: 3 })
    await wrapper.find('section.editing form').trigger('submit')
    await flushPromises()
    expect(api.updateIdea).toHaveBeenLastCalledWith(11, expect.objectContaining({ version: 2 }))
    expect(wrapper.find('section.editing').exists()).toBe(false)
  })

  it('удаление — только после подтверждения; «уже удалена» (404) — не ошибка', async () => {
    await open(USERS.anna, snapshot('submission', { ideas: [mine] }))

    await button(wrapper, 'Удалить').trigger('click')
    expect(document.body.textContent).toContain('Удалить идею?')
    answer(false)
    await flushPromises()
    expect(api.deleteIdea).not.toHaveBeenCalled()

    api.deleteIdea.mockRejectedValueOnce(new ApiError(404, 'Идея не найдена'))
    await button(wrapper, 'Удалить').trigger('click')
    answer(true)
    await flushPromises()
    expect(api.deleteIdea).toHaveBeenCalledWith(11)
    expect(document.body.textContent).toContain('Идея уже удалена')
    expect(document.body.textContent).not.toContain('Идея не найдена')
  })
})

describe('участник, голосование', () => {
  const ideas = [
    idea(11, 'Своя', { is_mine: true }),
    idea(12, 'Чужая', { voted_by_me: true }),
    idea(13, 'Ещё чужая'),
  ]

  it('голосует за чужие идеи; за свою — нет; авторов и счёта не видно', async () => {
    await open(USERS.anna, snapshot('voting', { ideas }))

    expect(cards()).toHaveLength(3)
    expect(button(wrapper, 'Голосовать', cardOf('Своя'))).toBeUndefined()
    expect(button(wrapper, 'Удалить', cardOf('Своя'))).toBeDefined()
    expect(cardOf('Чужая').text()).toContain('Вы проголосовали')
    expect(button(wrapper, 'Отозвать', cardOf('Чужая'))).toBeDefined()
    expect(button(wrapper, 'Голосовать', cardOf('Ещё чужая'))).toBeDefined()
    expect(wrapper.find('[data-test=my-votes]').text()).toBe('Ваших голосов: 1 из 2')
    expect(wrapper.text()).not.toContain('Анна Смирнова') // авторы скрыты
    expect(wrapper.find('[data-test=votes]').exists()).toBe(false)
  })

  it('повторное нажатие, пока голос в пути, не отправляет второй запрос', async () => {
    await open(USERS.anna, snapshot('voting', { ideas }))
    const pending = deferred()
    api.vote.mockReturnValueOnce(pending.promise)

    const vote = button(wrapper, 'Голосовать', cardOf('Ещё чужая'))
    await vote.trigger('click')
    await vote.trigger('click')
    expect(api.vote).toHaveBeenCalledTimes(1)
    expect(vote.attributes('disabled')).toBeDefined()

    pending.resolve({ idea_id: 13, voted: true })
    await flushPromises()
    expect(api.contest).toHaveBeenCalledTimes(2) // после голоса — свежий снимок
  })

  it('отзыв голоса', async () => {
    await open(USERS.anna, snapshot('voting', { ideas }))
    api.revokeVote.mockResolvedValueOnce(null)
    await button(wrapper, 'Отозвать', cardOf('Чужая')).trigger('click')
    await flushPromises()
    expect(api.revokeVote).toHaveBeenCalledWith(12)
  })

  it('отказ сервера (голосование уже закрыто) — сообщение и перечитанный снимок', async () => {
    await open(USERS.anna, snapshot('voting', { ideas }))
    api.vote.mockRejectedValueOnce(new ApiError(409, 'Голосование закрыто'))
    await button(wrapper, 'Голосовать', cardOf('Ещё чужая')).trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Голосование закрыто')
    expect(api.contest).toHaveBeenCalledTimes(2)
  })

  it('удаление своей идеи во время голосования предупреждает о голосах', async () => {
    await open(USERS.anna, snapshot('voting', { ideas }))
    api.deleteIdea.mockResolvedValueOnce(null)
    await button(wrapper, 'Удалить', cardOf('Своя')).trigger('click')
    expect(document.body.textContent).toContain('вместе со всеми голосами за неё')
    answer(true)
    await flushPromises()
    expect(api.deleteIdea).toHaveBeenCalledWith(11)
  })
})

describe('итоги', () => {
  // Снимок с точки зрения пользователя: is_mine — только у его идей.
  const tiedFor = (user) =>
    [
      idea(21, 'Ранняя', { votes_count: 2, author: { id: 2, display_name: 'Анна Смирнова' } }),
      idea(22, 'Поздняя', { votes_count: 2, author: { id: 3, display_name: 'Борис Котов' } }),
      idea(23, 'Без голосов', { votes_count: 0, author: { id: 3, display_name: 'Борис Котов' } }),
    ].map((item) => ({ ...item, is_mine: item.author.id === user.id }))

  it('победитель, раскрытые авторы, пояснение ничьей по правилу ранней идеи', async () => {
    await open(USERS.boris, snapshot('finished', { ideas: tiedFor(USERS.boris), winner: 21 }))

    const rows = wrapper.findAll('li[data-idea-id]')
    expect(rows.map((row) => row.find('h3').text())).toEqual(['Ранняя', 'Поздняя', 'Без голосов'])
    expect(rows[0].classes()).toContain('winner')
    expect(rows[0].text()).toContain('Победитель')
    expect(rows.map((row) => row.find('[data-test=author]').text())).toEqual([
      'Анна Смирнова',
      'Борис Котов',
      'Борис Котов',
    ])
    const tie = wrapper.find('[data-test=tie-note]').text()
    expect(tie).toContain('поровну')
    expect(tie).toContain('Победила идея, поданная раньше: «Ранняя»')
    expect(tie).toMatch(/\d{2}:\d{2}:\d{2}/) // с секундами: идеи поданы в одну минуту
    expect(wrapper.text()).not.toContain('Ваша идея победила!')
  })

  it('автор победившей идеи видит поздравление', async () => {
    await open(USERS.anna, snapshot('finished', { ideas: tiedFor(USERS.anna), winner: 21 }))
    expect(wrapper.text()).toContain('Ваша идея победила!')
  })

  it('без голосов — самая ранняя идея; без идей — победителя нет', async () => {
    const zero = [idea(31, 'Первая', { votes_count: 0 }), idea(32, 'Вторая', { votes_count: 0 })]
    await open(USERS.boris, snapshot('finished', { ideas: zero, winner: 31 }))
    expect(wrapper.find('[data-test=tie-note]').text()).toContain('Голосов нет')
    wrapper.unmount()

    await open(USERS.boris, snapshot('finished', { ideas: [] }))
    expect(wrapper.text()).toContain('Конкурс завершён без победителя')
  })
})

describe('отметка «изменена»', () => {
  it('только у своей правленой идеи: у чужих сервер не отдаёт время правки', async () => {
    const own = idea(51, 'Своя', { is_mine: true, updated_at: new Date(NOW - 60_000).toISOString(), version: 2 })
    await open(USERS.anna, snapshot('voting', { ideas: [own, idea(52, 'Чужая')] }))
    expect(cardOf('Своя').text()).toContain('изменена')
    expect(cardOf('Чужая').text()).not.toContain('изменена')
  })
})

describe('организатор', () => {
  it('во время подачи — только счётчики, без текстов идей', async () => {
    await open(USERS.organizer, snapshot('submission', { stats: STATS, schedule: SCHEDULE }))
    expect(wrapper.find('[data-test=ideas-count]').text()).toBe('2')
    expect(wrapper.text()).toContain('Идеи скрыты до начала голосования')
    expect(wrapper.find('form.idea-form').exists()).toBe(false) // организатор идеи не подаёт
  })

  it('расписание и статистика — человеческими словами: победитель по названию, «из 4 человек»', async () => {
    const ideas = [idea(41, 'Лидер', { votes_count: 2, author: { display_name: 'Анна Смирнова' } })]
    const schedule = [
      { kind: 'remind_voting', run_at: SCHEDULE[1].run_at, status: 'done', finished_at: SCHEDULE[1].run_at, note: 'писем: 0' },
      { kind: 'finalize', run_at: SCHEDULE[1].run_at, status: 'done', finished_at: SCHEDULE[1].run_at, note: 'писем: 4; победитель — идея 41' },
    ]
    await open(USERS.organizer, snapshot('finished', { ideas, stats: STATS, schedule, winner: 41 }))

    expect(wrapper.text()).toContain('получателей не было')
    expect(wrapper.text()).toContain('отправлено писем: 4; победила «Лидер»')
    expect(wrapper.text()).not.toContain('идея 41')
    expect(wrapper.text()).toContain('из 4')
    expect(wrapper.text()).toMatch(/человек\s+проголосовал\s/) // 1 из 4 человек проголосовал
  })

  it('во время голосования — живые результаты без авторов, статистика, расписание, участники', async () => {
    const ideas = [idea(41, 'Лидер', { votes_count: 2 }), idea(42, 'Вторая', { votes_count: 1 })]
    await open(USERS.organizer, snapshot('voting', { ideas, stats: STATS, schedule: SCHEDULE }))

    expect(wrapper.findAll('[data-test=votes]').map((cell) => cell.text())).toEqual(['2', '1'])
    expect(wrapper.find('[data-test=author]').exists()).toBe(false)
    expect(wrapper.text()).toContain('автор скрыт до финала')
    expect(wrapper.find('[data-test=voters-count]').text()).toContain('1')
    expect(button(wrapper, 'Голосовать')).toBeUndefined()
    expect(wrapper.text()).toContain('Пропущено')
    expect(wrapper.text()).toContain('отправлено писем: 2')
    expect(api.participants).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('Анна Смирнова') // из списка участников

    // Новый голос — сигнал — снимок перечитан, счёт обновился без перезагрузки.
    api.contest.mockResolvedValue(
      snapshot('voting', {
        revision: 5,
        ideas: [idea(41, 'Лидер', { votes_count: 3 }), idea(42, 'Вторая', { votes_count: 1 })],
        stats: STATS,
        schedule: SCHEDULE,
      }),
    )
    realtime.emit({ type: 'contest_changed', contest_id: 7, revision: 5 })
    await flushPromises()
    expect(wrapper.findAll('[data-test=votes]').map((cell) => cell.text())).toEqual(['3', '1'])
  })
})

describe('обновление по сигналам', () => {
  it('перечитывает только свой конкурс и только по новым изменениям', async () => {
    await open(USERS.anna, snapshot('voting', { revision: 4 }))
    expect(api.contest).toHaveBeenCalledTimes(1)

    realtime.emit({ type: 'contest_changed', contest_id: 8, revision: 9 }) // чужой конкурс
    realtime.emit({ type: 'contest_changed', contest_id: 7, revision: 4 }) // уже показано
    await flushPromises()
    expect(api.contest).toHaveBeenCalledTimes(1)

    realtime.emit({ type: 'phase_changed', contest_id: 7, revision: 4 }) // срок: revision тот же
    await flushPromises()
    expect(api.contest).toHaveBeenCalledTimes(2)

    realtime.emit({ type: 'resync' }) // переподключение
    await flushPromises()
    expect(api.contest).toHaveBeenCalledTimes(3)
  })

  it('устаревший ответ, пришедший позже, не откатывает экран', async () => {
    await open(USERS.anna, snapshot('voting', { revision: 6, ideas: [idea(51, 'Новая версия')] }))
    api.contest.mockResolvedValueOnce(snapshot('voting', { revision: 5, ideas: [idea(51, 'Старая версия')] }))
    realtime.emit({ type: 'resync' })
    await flushPromises()
    expect(wrapper.text()).toContain('Новая версия')
    expect(wrapper.text()).not.toContain('Старая версия')
  })

  it('не участник видит «Конкурс не найден»', async () => {
    signIn(USERS.boris)
    api.contest.mockRejectedValue(new ApiError(404, 'Конкурс не найден'))
    ;({ wrapper } = await mountAt('/contests/7'))
    expect(wrapper.text()).toContain('Конкурс не найден')
    expect(wrapper.text()).toContain('вы не входите в список его участников')
  })

  it('сбой обновления — прежние данные остаются, предложено обновить', async () => {
    await open(USERS.anna, snapshot('voting', { ideas: [idea(61, 'Видна')] }))
    api.contest.mockRejectedValueOnce(new ApiError(0, 'Нет связи с сервером.'))
    realtime.emit({ type: 'resync' })
    await flushPromises()
    expect(wrapper.text()).toContain('Видна')
    expect(wrapper.text()).toContain('Не удалось обновить данные')
  })
})
