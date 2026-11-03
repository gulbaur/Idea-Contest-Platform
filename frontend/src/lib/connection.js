// Одно соединение WebSocket на вкладку и подписка компонентов на сигналы.
import { onBeforeUnmount } from 'vue'

import { RealtimeClient } from './realtime.js'
import { session } from './session.js'

function socketUrl() {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/api/ws`
}

export const realtime = new RealtimeClient({
  url: typeof window === 'undefined' ? '' : socketUrl(),
  getToken: () => session.token,
})

if (typeof window !== 'undefined') {
  // Вкладка «проснулась» или вернулась сеть — не ждём паузу переподключения.
  window.addEventListener('online', () => realtime.reconnectNow())
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') realtime.reconnectNow()
  })
}

/**
 * Подписать компонент на сигналы на время его жизни.
 * handler получает сообщение сервера или `{type: "resync"}` после (пере)подключения.
 */
export function useSignals(handler) {
  const unsubscribe = realtime.subscribe(handler)
  onBeforeUnmount(unsubscribe)
  return unsubscribe
}
