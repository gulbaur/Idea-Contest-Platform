<script setup>
// Модальное окно с произвольным содержимым (формы). Esc, крестик и клик мимо окна закрывают его.
// Для простого «Да / Отмена» — ConfirmHost.vue и lib/confirm.js.
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { dialog } from '../lib/confirm.js'
import Icon from './Icon.vue'

defineProps({
  title: { type: String, required: true },
  wide: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const box = ref(null)

function onKey(event) {
  // Esc при открытом подтверждении закрывает только подтверждение (ConfirmHost).
  if (event.key === 'Escape' && !dialog.open) emit('close')
}

onMounted(async () => {
  window.addEventListener('keydown', onKey)
  await nextTick()
  // Фокус — на первое поле формы, иначе на само окно: клавиатура сразу внутри диалога.
  const first = box.value?.querySelector('input:not([type=hidden]):not(:disabled), select, textarea, button.primary-focus')
  ;(first ?? box.value)?.focus()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="backdrop" @click.self="emit('close')">
    <div ref="box" class="modal" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
      <header class="head">
        <h2>{{ title }}</h2>
        <button class="btn btn-ghost btn-sm close" type="button" aria-label="Закрыть" @click="emit('close')">
          <Icon name="x" :size="18" />
        </button>
      </header>
      <div class="body">
        <slot />
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(12, 14, 18, 0.5);
  overflow-y: auto;
}

.modal {
  width: min(480px, 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.modal.wide {
  width: min(600px, 100%);
}

.modal:focus {
  outline: none;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px 0;
}

.close {
  padding: 0 6px;
}

.body {
  padding: 16px 20px 20px;
}
</style>
