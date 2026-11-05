<script setup>
// Боковое меню (D-060): разделы, настройки, индикатор связи, кто вошёл в этой вкладке, выход.
// На широком экране меню всегда видно; на узком — открывается кнопкой поверх страницы.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { ROLE_LABELS } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import { useSignals } from '../lib/connection.js'
import { isAdmin, isOrganizer, session } from '../lib/session.js'
import { refreshUnread, unread } from '../lib/unread.js'
import ConnectionStatus from './ConnectionStatus.vue'
import Icon from './Icon.vue'

const emit = defineEmits(['logout'])
const route = useRoute()
const open = ref(false)

const initials = computed(() =>
  (session.user?.display_name ?? '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase(),
)

// Раздел подсвечен и на вложенных страницах: /contests/5 — это тоже «Конкурсы».
// Разделы зависят от роли (D-062): администратору — «Сотрудники», остальным — «Конкурсы».
const sections = computed(() => [
  ...(isAdmin()
    ? [{ to: '/employees', label: t('app.nav.employees'), icon: 'users', active: route.path.startsWith('/employees') }]
    : [{ to: '/contests', label: t('app.nav.contests'), icon: 'list', active: route.path.startsWith('/contests') }]),
  { to: '/mail', label: t('app.nav.mail'), icon: 'inbox', active: route.path.startsWith('/mail'), badge: unread.count },
  // Технический журнал всех писем — отдельно от личных «Входящих» (D-063).
  ...(isAdmin() || isOrganizer()
    ? [{ to: '/journal', label: t('app.nav.journal'), icon: 'mail', active: route.path.startsWith('/journal') }]
    : []),
])

// Счётчик непрочитанных: при входе, при новом письме и после восстановления связи.
onMounted(refreshUnread)
useSignals((message) => {
  if (message.type === 'mail_changed' || message.type === 'resync') refreshUnread()
})

// Переход по ссылке закрывает меню на узком экране.
watch(() => route.fullPath, () => (open.value = false))

function onKey(event) {
  if (event.key === 'Escape') open.value = false
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <header class="topbar">
    <button class="btn btn-ghost btn-sm menu" type="button" :aria-label="t('app.menu')" :aria-expanded="open" @click="open = true">
      <Icon name="menu" :size="20" />
    </button>
    <RouterLink to="/" class="brand" :aria-label="t('app.toHome')">
      <span class="logo"><Icon name="bulb" :size="16" /></span>
      <span>{{ t('app.brand') }}</span>
    </RouterLink>
  </header>

  <div v-if="open" class="backdrop" aria-hidden="true" @click="open = false" />

  <aside class="sidebar" :class="{ open }" :aria-label="t('app.menu')">
    <RouterLink to="/" class="brand" :aria-label="t('app.toHome')">
      <span class="logo"><Icon name="bulb" :size="16" /></span>
      <span>{{ t('app.brand') }}</span>
    </RouterLink>

    <nav class="nav" :aria-label="t('app.sections')">
      <RouterLink
        v-for="item in sections"
        :key="item.to"
        :to="item.to"
        class="nav-link"
        :class="{ active: item.active }"
        :aria-current="item.active ? 'page' : undefined"
      >
        <Icon :name="item.icon" :size="18" />
        <span>{{ item.label }}</span>
        <span v-if="item.badge" class="nav-badge" :aria-label="t('app.unreadBadge', { n: item.badge })">{{ item.badge }}</span>
      </RouterLink>
    </nav>

    <div class="spacer" />

    <nav class="nav" :aria-label="t('app.account')">
      <RouterLink
        to="/settings"
        class="nav-link"
        :class="{ active: route.path === '/settings' }"
        :aria-current="route.path === '/settings' ? 'page' : undefined"
      >
        <Icon name="settings" :size="18" />
        <span>{{ t('app.nav.settings') }}</span>
      </RouterLink>
    </nav>

    <div class="footer">
      <ConnectionStatus />
      <div class="user" :title="t('app.signedInAs', { login: session.user?.login })">
        <span class="avatar" :class="session.user?.role" aria-hidden="true">{{ initials }}</span>
        <span class="who">
          <strong>{{ session.user?.display_name }}</strong>
          <small>{{ ROLE_LABELS[session.user?.role] }}</small>
        </span>
        <button class="btn btn-ghost btn-sm logout" type="button" :aria-label="t('app.signOut')" :title="t('app.signOut')" @click="emit('logout')">
          <Icon name="logout" :size="18" />
        </button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: var(--sidebar-w);
  height: 100vh;
  padding: 16px 12px 12px;
  border-right: 1px solid var(--border);
  background: var(--surface);
  overflow-y: auto;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text);
  font-weight: 600;
  font-size: var(--text-lg);
  letter-spacing: -0.01em;
}

.sidebar > .brand {
  margin: 0 8px 20px;
}

.brand:hover {
  text-decoration: none;
}

.logo {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius);
  background: var(--primary);
  color: var(--on-primary);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius);
  color: var(--text-2);
  font-weight: 500;
}

.nav-link:hover {
  background: var(--surface-hover);
  color: var(--text);
  text-decoration: none;
}

.nav-link.active {
  background: var(--primary-soft);
  color: var(--primary-text);
}

.nav-badge {
  min-width: 20px;
  margin-left: auto;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--primary);
  color: var(--on-primary);
  font-size: var(--text-xs);
  font-weight: 600;
  line-height: 20px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.footer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.footer :deep(.status) {
  align-self: flex-start;
}

/* В меню подпись состояния связи видна всегда, в том числе на телефоне. */
.footer :deep(.status .text) {
  display: inline;
}

.footer :deep(.status) {
  padding: 4px 10px;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  display: grid;
  flex: none;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--phase-submission-soft);
  color: var(--phase-submission);
  font-weight: 600;
  font-size: var(--text-xs);
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
  flex: 1;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}

.who strong {
  overflow: hidden;
  font-weight: 500;
  font-size: var(--text-md);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.who small {
  color: var(--text-3);
  font-size: var(--text-xs);
}

.logout {
  flex: none;
  padding: 0 7px;
}

.topbar,
.backdrop {
  display: none;
}

/* Узкий экран: верхняя полоса с кнопкой меню; меню выезжает слева поверх страницы. */
@media (max-width: 1023px) {
  .topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 8px;
    height: var(--header-h);
    padding: 0 12px;
    border-bottom: 1px solid var(--border);
    background: color-mix(in srgb, var(--surface) 92%, transparent);
    backdrop-filter: blur(8px);
  }

  .menu {
    padding: 0 7px;
  }

  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: block;
    background: rgba(12, 14, 18, 0.45);
  }

  .sidebar {
    position: fixed;
    top: 0;
    left: 0;
    z-index: 40;
    max-width: 85vw;
    box-shadow: var(--shadow-lg);
    /* Закрытое меню скрыто и от клавиатуры и экранных дикторов, а не только сдвинуто. */
    visibility: hidden;
    transform: translateX(-105%);
    transition: transform 0.2s ease, visibility 0s linear 0.2s;
  }

  .sidebar.open {
    visibility: visible;
    transform: none;
    transition: transform 0.2s ease;
  }
}
</style>
