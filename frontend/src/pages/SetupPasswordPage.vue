<script setup>
// Первый вход по одноразовой ссылке (D-062): сотрудник сам задаёт пароль и сразу входит.
// Токен — в части адреса после «#»: она не уходит на сервер с запросом страницы и не попадает
// в журналы. Сразу после чтения токен убирается из адресной строки и истории браузера.
import { onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

import Icon from '../components/Icon.vue'
import { api } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { setSession } from '../lib/session.js'

const MIN_LENGTH = 10

const router = useRouter()
const token = ref('')
const person = ref(null)
const invalid = ref(false)
const password = ref('')
const repeat = ref('')
const error = ref('')
const pending = ref(false)

onMounted(async () => {
  token.value = decodeURIComponent(window.location.hash.replace(/^#/, ''))
  window.history.replaceState(window.history.state, '', window.location.pathname)
  if (!token.value) {
    invalid.value = true
    return
  }
  try {
    person.value = await api.setupCheck(token.value)
  } catch {
    invalid.value = true
  }
})

async function submit() {
  if (pending.value) return
  error.value = ''
  if (password.value.length < MIN_LENGTH) {
    error.value = t('auth.setup.tooShort', { min: MIN_LENGTH })
    return
  }
  if (password.value !== repeat.value) {
    error.value = t('auth.setup.mismatch')
    return
  }
  pending.value = true
  try {
    const result = await api.setup(token.value, password.value)
    setSession({ token: result.token, user: result.user })
    await router.replace('/')
  } catch (failure) {
    if (failure.status === 404) invalid.value = true
    else error.value = failure.message
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="setup-page">
    <div class="brand">
      <span class="logo"><Icon name="bulb" :size="18" /></span>
      <span>{{ t('auth.brand') }}</span>
    </div>

    <div v-if="invalid" class="card panel stack">
      <h1>{{ t('auth.setup.invalidTitle') }}</h1>
      <p class="muted">{{ t('auth.setup.invalidText') }}</p>
      <RouterLink class="btn" to="/login"><Icon name="arrow-left" /> {{ t('auth.setup.toLogin') }}</RouterLink>
    </div>

    <div v-else-if="!person" class="card panel"><div class="skeleton" style="height: 180px" /></div>

    <form v-else class="card panel stack" novalidate @submit.prevent="submit">
      <div>
        <h1>{{ t('auth.setup.hello', { name: person.display_name }) }}</h1>
        <p class="muted">{{ t('auth.setup.intro') }} <code class="mono">{{ person.login }}</code>.</p>
      </div>
      <div class="field">
        <label for="new-password">{{ t('auth.setup.password') }}</label>
        <input id="new-password" v-model="password" class="input" type="password" autocomplete="new-password" />
        <span class="hint">{{ t('auth.setup.passwordHint', { min: MIN_LENGTH }) }}</span>
      </div>
      <div class="field">
        <label for="repeat-password">{{ t('auth.setup.repeat') }}</label>
        <input id="repeat-password" v-model="repeat" class="input" type="password" autocomplete="new-password" />
      </div>
      <div v-if="error" class="notice notice-danger" role="alert"><Icon name="alert" class="icon" /> {{ error }}</div>
      <button class="btn btn-primary btn-lg btn-block" type="submit" :disabled="pending">
        <span v-if="pending" class="spinner" aria-hidden="true" /> {{ t('auth.setup.submit') }}
      </button>
    </form>
  </div>
</template>

<style scoped>
.setup-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  min-height: 100vh;
  padding: 64px 16px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: var(--text-lg);
}

.logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius);
  background: var(--primary);
  color: var(--on-primary);
}

.panel {
  width: min(440px, 100%);
  padding: 28px;
}

.panel h1 {
  font-size: var(--text-xl);
}

.panel p {
  margin-top: 6px;
}
</style>
