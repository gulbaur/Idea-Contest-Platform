// Клиент WebSocket с поддельным сокетом и управляемыми таймерами (D-049).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RealtimeClient } from './realtime.js'

class FakeSocket {
  static instances = []

  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    this.closed = false
    FakeSocket.instances.push(this)
  }

  send(text) {
    this.sent.push(JSON.parse(text))
  }

  close() {
    this.closed = true
  }

  // Действия «сервера» в тесте:
  open() {
    this.readyState = 1
    this.onopen?.()
  }

  receive(message) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  drop(code = 1006) {
    this.readyState = 3
    this.onclose?.({ code })
  }
}

const latest = () => FakeSocket.instances.at(-1)

describe('RealtimeClient', () => {
  let client
  let received
  let onUnauthorized

  beforeEach(() => {
    vi.useFakeTimers()
    FakeSocket.instances = []
    received = []
    onUnauthorized = vi.fn()
    client = new RealtimeClient({
      url: 'ws://test/api/ws',
      getToken: () => 'tab-token',
      onUnauthorized,
      WebSocketImpl: FakeSocket,
      random: () => 0.5, // без случайной добавки: пауза ровно базовая
    })
    client.subscribe((message) => received.push(message))
  })

  afterEach(() => {
    client.stop()
    vi.useRealTimers()
  })

  function connect() {
    client.start()
    latest().open()
    latest().receive({ type: 'ready', user_id: 1 })
  }

  it('первым сообщением отправляет токен; после ready — «в сети» и сигнал resync', () => {
    client.start()
    expect(client.state.status).toBe('connecting')
    latest().open()
    expect(latest().sent).toEqual([{ type: 'auth', token: 'tab-token' }])
    latest().receive({ type: 'ready', user_id: 1 })
    expect(client.state.status).toBe('online')
    expect(received).toEqual([{ type: 'resync' }])
  })

  it('передаёт сигналы подписчикам; pong не передаёт; мусор игнорирует', () => {
    connect()
    latest().receive({ type: 'contest_changed', contest_id: 3, revision: 9 })
    latest().receive({ type: 'pong' })
    latest().onmessage({ data: 'не json' })
    expect(received.slice(1)).toEqual([{ type: 'contest_changed', contest_id: 3, revision: 9 }])
  })

  it('ping раз в 15 секунд, пока на них отвечают', () => {
    connect()
    for (let n = 0; n < 3; n += 1) {
      vi.advanceTimersByTime(15_000)
      latest().receive({ type: 'pong' })
    }
    expect(latest().sent.filter((m) => m.type === 'ping')).toHaveLength(3)
    expect(client.state.status).toBe('online')
  })

  it('нет ответа на ping — связь «молча» потеряна: закрыть и переподключиться', () => {
    connect()
    const silent = latest()
    vi.advanceTimersByTime(15_000) // ping ушёл, ответа нет
    expect(client.state.status).toBe('online')
    vi.advanceTimersByTime(15_000) // следующий ping — ответа так и нет
    expect(silent.closed).toBe(true)
    expect(client.state.status).toBe('offline')
    vi.advanceTimersByTime(500)
    expect(FakeSocket.instances).toHaveLength(2)
    latest().open()
    latest().receive({ type: 'ready', user_id: 1 })
    expect(client.state.status).toBe('online')
    expect(received.filter((m) => m.type === 'resync')).toHaveLength(2)
  })

  it('после разрыва переподключается с нарастающей паузой и снова просит resync', () => {
    connect()
    latest().drop()
    expect(client.state.status).toBe('offline')

    vi.advanceTimersByTime(499)
    expect(FakeSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1) // 0,5 с
    expect(FakeSocket.instances).toHaveLength(2)

    latest().drop() // второй сбой подряд — пауза 1 с
    vi.advanceTimersByTime(999)
    expect(FakeSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.instances).toHaveLength(3)

    latest().open()
    latest().receive({ type: 'ready', user_id: 1 })
    expect(client.state.status).toBe('online')
    expect(client.state.attempts).toBe(0)
    expect(received.filter((m) => m.type === 'resync')).toHaveLength(2) // после первого входа и после восстановления
  })

  it('пауза не растёт больше 10 секунд', () => {
    client.start()
    for (let attempt = 0; attempt < 8; attempt += 1) {
      latest().drop()
      vi.advanceTimersByTime(10_000)
    }
    const before = FakeSocket.instances.length
    latest().drop()
    vi.advanceTimersByTime(9_999)
    expect(FakeSocket.instances).toHaveLength(before)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.instances).toHaveLength(before + 1)
  })

  it.each([4401, 4400])('код %i — вход недействителен: без переподключения, сообщить приложению', (code) => {
    connect()
    latest().drop(code)
    vi.advanceTimersByTime(60_000)
    expect(FakeSocket.instances).toHaveLength(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(client.state.status).toBe('idle')
  })

  it('stop() закрывает соединение и отменяет переподключение', () => {
    connect()
    latest().drop()
    client.stop()
    vi.advanceTimersByTime(60_000)
    expect(FakeSocket.instances).toHaveLength(1)
    expect(client.state.status).toBe('idle')
  })

  it('reconnectNow() подключает сразу, не дожидаясь паузы', () => {
    connect()
    latest().drop()
    client.reconnectNow()
    expect(FakeSocket.instances).toHaveLength(2)
  })

  it('без токена не подключается', () => {
    const idle = new RealtimeClient({ url: 'ws://x', getToken: () => null, WebSocketImpl: FakeSocket })
    idle.start()
    expect(FakeSocket.instances).toHaveLength(0)
  })
})
