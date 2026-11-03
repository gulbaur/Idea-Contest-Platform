// Всплывающие уведомления (успех, ошибка, информация). Показывает ToastHost.vue.
import { reactive } from 'vue'

export const toasts = reactive([])
let nextId = 1

function push(kind, text, timeoutMs) {
  const toast = { id: nextId++, kind, text }
  toasts.push(toast)
  setTimeout(() => dismiss(toast.id), timeoutMs)
  // Не больше четырёх одновременно — старые уходят первыми.
  while (toasts.length > 4) toasts.shift()
  return toast.id
}

export function dismiss(id) {
  const index = toasts.findIndex((toast) => toast.id === id)
  if (index !== -1) toasts.splice(index, 1)
}

export const notify = {
  success: (text) => push('success', text, 4000),
  info: (text) => push('info', text, 5000),
  error: (text) => push('error', text, 7000),
}
