<script setup>
// Вход. Каждая вкладка входит отдельно (D-003): в двух вкладках можно работать
// под разными пользователями, например участником и организатором.
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import Icon from '../components/Icon.vue'
import { api } from '../lib/api.js'
import { setSession } from '../lib/session.js'

// Синтетические демо-аккаунты (backend/app/seed.py). Пароль публичный — D-004.
const DEMO_PASSWORD = 'demo-password'
const DEMO_ACCOUNTS = [
  { login: 'organizer', name: 'Организатор', role: 'создаёт конкурсы, видит ход и итоги' },
  { login: 'anna', name: 'Анна Смирнова', role: 'участник' },
  { login: 'boris', name: 'Борис Котов', role: 'участник' },
  { login: 'vera', name: 'Вера Орлова', role: 'участник' },
  { login: 'gleb', name: 'Глеб Лебедев', role: 'участник' },
  { login: 'dina', name: 'Дина Ахметова', role: 'участник' },
]

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
    error.value = 'Введите логин и пароль'
    return
  }
  pending.value = true
  try {
    const result = await api.login(login.value.trim(), password.value)
    setSession({ token: result.token, user: result.user })
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/')
    await router.replace(redirect ? route.query.redirect : '/contests')
  } catch (failure) {
    error.value = failure.message
  } finally {
    pending.value = false
  }
}

function useDemo(account) {
  login.value = account.login
  password.value = DEMO_PASSWORD
  submit()
}
</script>

<template>
  <div class="login-page">
    <section class="hero">
      <div class="brand">
        <span class="logo"><Icon name="bulb" :size="26" /></span>
        <span>Конкурс идей</span>
      </div>
      <h1>Идеи сотрудников — от предложения до победителя</h1>
      <ol class="steps">
        <li>
          <span class="n">1</span>
          <div><strong>Приём идей.</strong> Участники предлагают идеи; чужие идеи до голосования не видны.</div>
        </li>
        <li>
          <span class="n">2</span>
          <div>
            <strong>Голосование.</strong> Анонимно, за любые чужие идеи — по одному голосу за каждую; голос можно
            отозвать.
          </div>
        </li>
        <li>
          <span class="n">3</span>
          <div><strong>Итоги.</strong> Раскрываются авторы и победитель, всем участникам приходит письмо.</div>
        </li>
      </ol>
    </section>

    <section class="panel">
      <form class="card form stack" novalidate @submit.prevent="submit">
        <div>
          <h2>Вход</h2>
          <p class="muted hint">В каждой вкладке браузера — свой вход: можно открыть организатора и участника рядом.</p>
        </div>

        <div v-if="expired" class="notice notice-warning" role="status">
          <Icon name="clock" class="icon" /> Сессия завершена — войдите снова.
        </div>

        <div class="field">
          <label for="login">Логин</label>
          <input id="login" v-model="login" class="input" autocomplete="username" autofocus :disabled="pending" />
        </div>
        <div class="field">
          <label for="password">Пароль</label>
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
          Войти
        </button>
      </form>

      <div class="card demo">
        <div class="row">
          <h3>Демо-аккаунты</h3>
          <span class="faint">пароль <code class="mono">{{ DEMO_PASSWORD }}</code></span>
        </div>
        <ul class="accounts">
          <li v-for="account in DEMO_ACCOUNTS" :key="account.login">
            <button class="account" type="button" :disabled="pending" @click="useDemo(account)">
              <span class="avatar" :class="{ organizer: account.login === 'organizer' }">
                <Icon :name="account.login === 'organizer' ? 'flag' : 'user'" :size="16" />
              </span>
              <span class="who">
                <strong>{{ account.name }}</strong>
                <small>{{ account.login }} · {{ account.role }}</small>
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
  grid-template-columns: 1.05fr 1fr;
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
  font-weight: 750;
  font-size: 1.15rem;
}

.logo {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--primary), var(--phase-voting));
  color: #fff;
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
  font-weight: 750;
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
  font-size: 0.9rem;
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

.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.who strong {
  font-size: 0.88rem;
}

.who small {
  overflow: hidden;
  color: var(--text-3);
  font-size: 0.75rem;
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
    grid-template-columns: 1fr;
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
    grid-template-columns: 1fr;
  }
}
</style>
