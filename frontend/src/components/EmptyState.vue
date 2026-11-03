<script setup>
// Пустой список или ошибка загрузки: значок, заголовок, пояснение и действия (слот).
import Icon from './Icon.vue'

defineProps({
  icon: { type: String, default: 'inbox' },
  title: { type: String, required: true },
  text: { type: String, default: '' },
  tone: { type: String, default: 'neutral' }, // neutral | error
})
</script>

<template>
  <div class="empty" :class="tone" :role="tone === 'error' ? 'alert' : undefined">
    <span class="mark"><Icon :name="icon" :size="26" /></span>
    <h3>{{ title }}</h3>
    <p v-if="text" class="muted">{{ text }}</p>
    <div v-if="$slots.default" class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 20px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface);
  text-align: center;
}

.empty p {
  max-width: 460px;
}

.mark {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin-bottom: 6px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-text);
}

.error .mark {
  background: var(--danger-soft);
  color: var(--danger);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 10px;
}
</style>
