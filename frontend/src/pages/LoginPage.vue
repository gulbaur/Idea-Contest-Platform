<script setup>
// Вход. Каждая вкладка входит отдельно (D-003): в двух вкладках можно работать
// под разными пользователями, например участником и организатором.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import Icon from '../components/Icon.vue'
import { api } from '../lib/api.js'
import { t } from '../lib/i18n.js'
import { setSession } from '../lib/session.js'

// Демо-аккаунты и их публичный пароль (D-004) сообщает сервер, и только в демо-режиме
// (D-059): вне его блок не показывается, а пароль не попадает в код страницы.
const demo = ref(null)
// Подписи ролей — computed: пересчитываются при смене языка (D-065).
const ROLE_NAMES = computed(() => ({
  admin: t('auth.login.role.admin'),
  organizer: t('auth.login.role.organizer'),
  employee: t('auth.login.role.employee'),
}))
const ROLE_ICONS = { admin: 'settings', organizer: 'flag', employee: 'user' }
onMounted(async () => {
  try {
    const info = await api.demo()
    demo.value = info?.enabled ? info : null
  } catch {
    demo.value = null // без блока демо-аккаунтов вход по логину и паролю всё равно работает
  }
})

const route = useRoute()
const router = useRouter()

const login = ref('')
const password = ref('')
const pending = ref(false)
const error = ref('')
const expired = computed(() => route.query.expired === '1')

async function submit() {
  if (pending.value) return
  error.value = ''
  if (!login.value.trim() || !password.value) {
    error.value = t('auth.login.empty')
    return
  }
  pending.value = true
  try {
    const result = await api.login(login.value.trim(), password.value)
    setSession({ token: result.token, user: result.user })
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
    await router.replace(redirect ? route.query.redirect : '/')
  } catch (failure) {
    error.value = failure.message
  } finally {
    pending.value = false
  }
}

function useDemo(account) {
  login.value = account.login
  password.value = demo.value.password
  submit()
}
</script>

<template>
  <div class="login-page">
    <section class="hero">
      <div class="brand">
        <span class="logo"><Icon name="bulb" :size="26" /></span>
        <span>{{ t('auth.brand') }}</span>
      </div>
      <h1>{{ t('auth.login.heroTitle') }}</h1>
      <ol class="steps">
        <li>
          <span class="n">1</span>
          <div><strong>{{ t('auth.login.step1Title') }}</strong> {{ t('auth.login.step1Text') }}</div>
        </li>
        <li>
          <span class="n">2</span>
          <div><strong>{{ t('auth.login.step2Title') }}</strong> {{ t('auth.login.step2Text') }}</div>
        </li>
        <li>
          <span class="n">3</span>
          <div><strong>{{ t('auth.login.step3Title') }}</strong> {{ t('auth.login.step3Text') }}</div>
        </li>
      </ol>
    </section>

    <section class="panel">
      <form class="card form stack" novalidate @submit.prevent="submit">
        <div>
          <h2>{{ t('auth.login.title') }}</h2>
          <p class="muted hint">{{ t('auth.login.hint') }}</p>
        </div>

        <div v-if="expired" class="notice notice-warning" role="status">
          <Icon name="clock" class="icon" /> {{ t('auth.login.expired') }}
        </div>

        <div class="field">
          <label for="login">{{ t('auth.login.login') }}</label>
          <input id="login" v-model="login" class="input" autocomplete="username" autofocus :disabled="pending" />
        </div>
        <div class="field">
          <label for="password">{{ t('auth.login.password') }}</label>
          <input
            id="password"
            v-model="password"
            class="input"
            type="password"
            autocomplete="current-password"
            :disabled="pending"
          />
        </div>

        <div v-if="error" class="notice notice-danger" role="alert">
          <Icon name="alert" class="icon" /> {{ error }}
        </div>

        <button class="btn btn-primary btn-lg btn-block" type="submit" :disabled="pending">
          <span v-if="pending" class="spinner" aria-hidden="true" />
          {{ t('auth.login.submit') }}
        </button>
      </form>

      <div v-if="demo" class="card demo">
        <div class="row">
          <h3>{{ t('auth.login.demoTitle') }}</h3>
          <span class="faint">{{ t('auth.login.demoPassword') }} <code class="mono">{{ demo.password }}</code></span>
        </div>
        <ul class="accounts">
          <li v-for="account in demo.accounts" :key="account.login">
            <button
              class="account"
              type="button"
              :title="t('auth.login.signInAs', { login: account.login })"
              :disabled="pending"
              @click="useDemo(account)"
            >
              <span class="avatar" :class="account.role">
                <Icon :name="ROLE_ICONS[account.role] ?? 'user'" :size="16" />
              </span>
              <span class="who">
                <strong>{{ account.display_name }}</strong>
                <small>{{ ROLE_NAMES[account.role] ?? account.role }} · {{ account.login }}</small>
              </span>
              <Icon name="arrow-left" class="go" :size="16" />
            </button>
          </li>
        </ul>
      </div>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  gap: 40px;
  align-items: center;
  max-width: 1080px;
  min-height: 100vh;
  margin: 0 auto;
  padding: 40px 24px;
}

.hero h1 {
  margin: 28px 0 24px;
  font-size: clamp(1.7rem, 1.2rem + 2vw, 2.5rem);
  line-height: 1.15;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-weight: 600;
  font-size: var(--text-xl);
}

.logo {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: var(--radius-lg);
  background: var(--primary);
  color: var(--on-primary);
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0;
  padding: 0;
  list-style: none;
  color: var(--text-2);
}

.steps li {
  display: flex;
  gap: 14px;
}

.n {
  display: grid;
  place-items: center;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--primary-soft);
  color: var(--primary-text);
  font-weight: 600;
}

.steps strong {
  color: var(--text);
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form {
  padding: 26px;
  box-shadow: var(--shadow);
}

.hint {
  margin-top: 4px;
  font-size: var(--text-md);
}

.demo .row {
  justify-content: space-between;
  margin-bottom: 10px;
}

.accounts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.account {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.account:hover:not(:disabled) {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.avatar {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--phase-submission-soft);
  color: var(--phase-submission);
}

.avatar.organizer {
  background: var(--gold-soft);
  color: var(--warning);
}

.avatar.admin {
  background: var(--phase-voting-soft);
  color: var(--phase-voting);
}

.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.who strong {
  font-size: var(--text-md);
}

.who small {
  overflow: hidden;
  color: var(--text-3);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.go {
  margin-left: auto;
  color: var(--text-3);
  transform: rotate(180deg);
}

@media (max-width: 860px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
    min-height: auto;
    padding: 28px 16px 48px;
  }

  .hero h1 {
    margin: 18px 0 16px;
  }
}

@media (max-width: 480px) {
  .accounts {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
