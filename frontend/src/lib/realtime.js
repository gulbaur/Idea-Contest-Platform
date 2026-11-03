// Соединение WebSocket вкладки (D-039, D-049).
//
// Сервер присылает только сигналы «что-то изменилось» — без данных. Получив сигнал,
// страница перечитывает нужные данные обычным запросом, где сервер проверяет права.
//
// Что делает клиент:
// - первым сообщением отправляет токен входа;
// - раз в 15 секунд шлёт ping: соединение не закроют прокси, а если ответа (pong) нет
//   к следующему ping, связь считается потерянной — даже когда браузер этого не заметил
//   (сон компьютера, смена сети);
// - после разрыва переподключается с нарастающей паузой (0,5 → 10 с);
// - после каждого (пере)подключения сообщает подписчикам `{type: "resync"}`:
//   за время разрыва сигналы могли потеряться, поэтому данные надо перечитать;
// - коды 4401/4400 (вход недействителен) — без переподключения.
import { reactive } from 'vue'

export const CLOSE_BAD_MESSAGE = 4400
export const CLOSE_UNAUTHORIZED = 4401
const PING_INTERVAL_MS = 15_000
const RETRY_BASE_MS = 500
const RETRY_MAX_MS = 10_000

export class RealtimeClient {
  constructor({
    url,
    getToken,
    onUnauthorized = () => {},
    WebSocketImpl = globalThis.WebSocket,
    random = Math.random,
    timers = globalThis,
  }) {
    this.url = url
    this.getToken = getToken
    this.onUnauthorized = onUnauthorized
    this.WebSocketImpl = WebSocketImpl
    this.random = random
    this.timers = timers
    this.listeners = new Set()
    // status: idle — не запущено; connecting — подключаемся; online — сигналы приходят;
    // offline — связи нет, ждём переподключения.
    this.state = reactive({ status: 'idle', attempts: 0 })
    this.socket = null
    this.running = false
    this.retryTimer = null
    this.pingTimer = null
    this.awaitingPong = false
  }

  /** Подписаться на сигналы; возвращает функцию отписки. */
  subscribe(listener) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  start() {
    if (this.running) return
    this.running = true
    this.state.attempts = 0
    this.connect()
  }

  stop() {
    this.running = false
    this.timers.clearTimeout(this.retryTimer)
    this.timers.clearInterval(this.pingTimer)
    this.retryTimer = this.pingTimer = null
    const socket = this.socket
    this.socket = null
    if (socket) {
      socket.onclose = socket.onmessage = socket.onopen = socket.onerror = null
      socket.close()
    }
    this.state.status = 'idle'
  }

  /** Подключиться немедленно, не дожидаясь паузы (вкладка снова видима, сеть вернулась). */
  reconnectNow() {
    if (!this.running || this.state.status === 'online' || this.state.status === 'connecting') return
    this.timers.clearTimeout(this.retryTimer)
    this.connect()
  }

  connect() {
    const token = this.getToken()
    if (!token) return
    this.state.status = 'connecting'
    const socket = new this.WebSocketImpl(this.url)
    this.socket = socket
    socket.onopen = () => socket.send(JSON.stringify({ type: 'auth', token }))
    socket.onmessage = (event) => this.handleMessage(event.data)
    socket.onclose = (event) => this.handleClose(socket, event.code)
    socket.onerror = () => {} // за ошибкой всегда следует close — обрабатываем там
  }

  handleMessage(raw) {
    let message
    try {
      message = JSON.parse(raw)
    } catch {
      return
    }
    if (message.type === 'pong') {
      this.awaitingPong = false
      return
    }
    if (message.type === 'ready') {
      this.state.status = 'online'
      this.state.attempts = 0
      this.awaitingPong = false
      this.timers.clearInterval(this.pingTimer)
      this.pingTimer = this.timers.setInterval(() => this.heartbeat(), PING_INTERVAL_MS)
      this.emit({ type: 'resync' })
      return
    }
    this.emit(message)
  }

  handleClose(socket, code) {
    if (socket !== this.socket) return // закрылось старое соединение
    this.timers.clearInterval(this.pingTimer)
    this.socket = null
    if (!this.running) return
    if (code === CLOSE_UNAUTHORIZED || code === CLOSE_BAD_MESSAGE) {
      this.running = false
      this.state.status = 'idle'
      this.onUnauthorized()
      return
    }
    this.state.status = 'offline'
    const delay = Math.min(RETRY_MAX_MS, RETRY_BASE_MS * 2 ** this.state.attempts)
    this.state.attempts += 1
    // Случайная добавка ±20%: вкладки после сбоя сервера не подключаются все разом.
    this.retryTimer = this.timers.setTimeout(() => this.connect(), delay * (0.8 + 0.4 * this.random()))
  }

  heartbeat() {
    if (this.awaitingPong) {
      // Ответа на прошлый ping нет — соединение «молча» умерло. Закрываем и переподключаемся.
      const socket = this.socket
      if (socket) {
        socket.onclose = socket.onmessage = socket.onopen = socket.onerror = null
        socket.close()
        this.handleClose(socket, 4000)
      }
      return
    }
    this.awaitingPong = true
    this.send({ type: 'ping' })
  }

  send(message) {
    if (this.socket && this.socket.readyState === 1) this.socket.send(JSON.stringify(message))
  }

  emit(message) {
    for (const listener of [...this.listeners]) listener(message)
  }
}
