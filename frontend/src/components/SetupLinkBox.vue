<script setup>
// Одноразовая ссылка для задания пароля (D-062). Показывается один раз: сервер хранит
// только её хеш. Токен — после «#»: эта часть адреса не отправляется на сервер и не попадает
// в журналы, страница /setup читает её сама.
import { computed, ref } from 'vue'

import { formatDateTime } from '../lib/format.js'
import Icon from './Icon.vue'

const props = defineProps({
  name: { type: String, required: true },
  setup: { type: Object, required: true }, // { token, expires_at }
})

const url = computed(() => `${window.location.origin}/setup#${props.setup.token}`)
const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(url.value)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    // Буфер обмена недоступен (например, не HTTPS) — ссылку можно выделить и скопировать вручную.
    document.getElementById('setup-link')?.select()
  }
}
</script>

<template>
  <div class="stack-sm link-box">
    <div class="notice notice-success">
      <Icon name="check" class="icon" />
      <span>Ссылка для входа готова: {{ name }}. Передайте её по рабочему каналу — по этой ссылке сотрудник сам задаст пароль.</span>
    </div>
    <label class="label" for="setup-link">Одноразовая ссылка</label>
    <div class="copy-row">
      <input id="setup-link" class="input mono" :value="url" readonly @focus="$event.target.select()" />
      <button class="btn" type="button" @click="copy">
        <Icon :name="copied ? 'check' : 'send'" :size="16" /> {{ copied ? 'Скопировано' : 'Скопировать' }}
      </button>
    </div>
    <p class="faint">
      Действует до {{ formatDateTime(setup.expires_at) }}, только один раз. Ссылка показывается сейчас и больше нигде
      не хранится — если она потеряется, выдайте новую. В рабочем режиме с настоящей почтой её следует отправлять письмом.
    </p>
  </div>
</template>

<style scoped>
.copy-row {
  display: flex;
  gap: 8px;
}

.copy-row .input {
  font-size: var(--text-sm);
}

.copy-row .btn {
  flex: none;
}

@media (max-width: 520px) {
  .copy-row {
    flex-direction: column;
  }
}
</style>
