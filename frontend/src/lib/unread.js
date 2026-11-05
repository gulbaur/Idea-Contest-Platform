// Число непрочитанных писем во «Входящих» (D-063) — для счётчика в меню.
import { reactive } from 'vue'

import { api } from './api.js'

export const unread = reactive({ count: 0 })

export async function refreshUnread() {
  try {
    unread.count = (await api.unreadCount()).count
  } catch {
    // Счётчик — подсказка: при сбое сети остаётся прежним и обновится со следующим сигналом.
  }
}
