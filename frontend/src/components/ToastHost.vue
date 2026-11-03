<script setup>
// Всплывающие уведомления (lib/notify.js). aria-live — их зачитывают экранные дикторы.
import { dismiss, toasts } from '../lib/notify.js'
import Icon from './Icon.vue'

const ICON = { success: 'check', error: 'alert', info: 'info' }
</script>

<template>
  <div class="toasts" aria-live="polite" aria-atomic="false">
    <TransitionGroup name="toast">
      <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.kind" role="status">
        <Icon :name="ICON[toast.kind]" />
        <span class="text">{{ toast.text }}</span>
        <button class="close" type="button" aria-label="Закрыть уведомление" @click="dismiss(toast.id)">
          <Icon name="x" :size="16" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  right: 16px;
  bottom: 16px;
  z-index: 60;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(420px, calc(100vw - 32px));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 12px 12px 14px;
  border: 1px solid var(--border);
  border-left: 4px solid var(--primary);
  border-radius: var(--radius);
  background: var(--surface);
  box-shadow: var(--shadow-lg);
  font-size: 0.92rem;
}

.toast .icon {
  margin-top: 2px;
  color: var(--primary);
}

.toast.success {
  border-left-color: var(--success);
}

.toast.success .icon {
  color: var(--success);
}

.toast.error {
  border-left-color: var(--danger);
}

.toast.error > .icon {
  color: var(--danger);
}

.text {
  flex: 1;
}

.close {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
}

.close:hover {
  background: var(--surface-hover);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.22s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
