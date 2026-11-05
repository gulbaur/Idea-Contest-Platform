<script setup>
// Индикатор соединения WebSocket в шапке: видно, обновляется ли экран сам.
import { computed } from 'vue'

import { realtime } from '../lib/connection.js'

const view = computed(() => {
  switch (realtime.state.status) {
    case 'online':
      return { tone: 'online', text: 'Онлайн', hint: 'Изменения появляются без перезагрузки страницы' }
    case 'offline':
      return {
        tone: 'offline',
        text: 'Нет связи',
        hint: 'Соединение потеряно — переподключаемся автоматически; данные обновятся после восстановления',
      }
    default:
      return { tone: 'connecting', text: 'Подключение…', hint: 'Устанавливаем соединение для обновлений' }
  }
})
</script>

<template>
  <span class="status" :class="view.tone" :title="view.hint" role="status" aria-live="polite">
    <span class="dot" aria-hidden="true" />
    <span class="text">{{ view.text }}</span>
  </span>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 10px;
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text-2);
  font-size: var(--text-sm);
  font-weight: 600;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-3);
}

.online .dot {
  background: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
}

.connecting .dot {
  background: var(--warning);
}

.offline {
  background: var(--danger-soft);
  color: var(--danger);
}

.offline .dot {
  background: var(--danger);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.3;
  }
}

@media (max-width: 640px) {
  .text {
    display: none;
  }

  .status {
    padding: 8px;
  }
}
</style>
