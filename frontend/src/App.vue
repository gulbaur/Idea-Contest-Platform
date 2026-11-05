<script setup>
// Корневой компонент: боковое меню (после входа), текущая страница, уведомления, диалог.
// Здесь же — жизненный цикл соединения WebSocket и реакция на окончание сессии.
import { onMounted, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import AppSidebar from './components/AppSidebar.vue'
import ConfirmHost from './components/ConfirmHost.vue'
import ToastHost from './components/ToastHost.vue'
import { api, onUnauthorized } from './lib/api.js'
import { realtime } from './lib/connection.js'
import { notify } from './lib/notify.js'
import { clearSession, session, updateUser } from './lib/session.js'

const router = useRouter()
const route = useRoute()

function toLogin(expired) {
  realtime.stop()
  clearSession()
  const redirect = route.name && route.name !== 'login' ? route.fullPath : undefined
  router.replace({ name: 'login', query: { ...(expired ? { expired: '1' } : {}), ...(redirect ? { redirect } : {}) } })
}

// Сервер ответил 401 или закрыл WebSocket с кодом 4401: вход этой вкладки больше не действует.
onUnauthorized(() => {
  if (session.token) toLogin(true)
})
realtime.onUnauthorized = () => {
  if (session.token) toLogin(true)
}

async function logout() {
  try {
    await api.logout()
  } catch {
    // Даже если сервер недоступен, вкладка выходит: токен удаляется из sessionStorage.
  }
  toLogin(false)
  notify.info('Вы вышли. Другие вкладки остаются в своих учётных записях.')
}

// Соединение живёт, пока в вкладке есть вход.
watch(
  () => session.token,
  (token) => (token ? realtime.start() : realtime.stop()),
  { immediate: true },
)

onMounted(async () => {
  if (!session.token) return
  try {
    updateUser(await api.me()) // проверить, что сохранённый вход ещё действует
  } catch {
    // 401 обработан выше; при сбое сети остаёмся на странице — данные загрузятся позже.
  }
})
</script>

<template>
  <div v-if="session.token" class="shell">
    <AppSidebar @logout="logout" />
    <main class="main">
      <RouterView />
    </main>
  </div>
  <RouterView v-else />
  <ToastHost />
  <ConfirmHost />
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  min-height: 100vh;
  /* Колонка меню — белая с границей на всю высоту, даже когда страница длиннее экрана. */
  background: linear-gradient(
    90deg,
    var(--surface) calc(var(--sidebar-w) - 1px),
    var(--border) calc(var(--sidebar-w) - 1px) var(--sidebar-w),
    transparent var(--sidebar-w)
  );
}

.main {
  min-width: 0;
}

@media (max-width: 1023px) {
  .shell {
    display: block;
    background: none;
  }
}
</style>
