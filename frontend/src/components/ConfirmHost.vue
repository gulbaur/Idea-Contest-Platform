<script setup>
// Модальное окно подтверждения (lib/confirm.js). Esc и клик мимо окна — «Отмена».
import { nextTick, ref, watch } from 'vue'

import { answer, dialog } from '../lib/confirm.js'
import Icon from './Icon.vue'

const confirmButton = ref(null)

watch(
  () => dialog.open,
  async (open) => {
    if (open) {
      await nextTick()
      confirmButton.value?.focus()
    }
  },
)

function onKeydown(event) {
  if (event.key === 'Escape') answer(false)
}
</script>

<template>
  <Transition name="fade">
    <div v-if="dialog.open" class="backdrop" @click.self="answer(false)" @keydown="onKeydown">
      <div
        class="dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
      >
        <div class="head">
          <span class="mark" :class="{ danger: dialog.danger }">
            <Icon :name="dialog.danger ? 'alert' : 'info'" :size="20" />
          </span>
          <h2 id="confirm-title">{{ dialog.title }}</h2>
        </div>
        <p id="confirm-message" class="message">{{ dialog.message }}</p>
        <div class="actions">
          <button class="btn" type="button" @click="answer(false)">Отмена</button>
          <button
            ref="confirmButton"
            class="btn"
            :class="dialog.danger ? 'btn-danger' : 'btn-primary'"
            type="button"
            @click="answer(true)"
          >
            {{ dialog.confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(12, 14, 26, 0.45);
}

.dialog {
  width: min(460px, 100%);
  padding: 22px;
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
}

.head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-text);
}

.mark.danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.message {
  margin: 14px 0 22px;
  color: var(--text-2);
  white-space: pre-line;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
