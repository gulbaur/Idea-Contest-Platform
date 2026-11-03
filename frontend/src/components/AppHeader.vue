<script setup>
// Шапка: название, разделы, кто вошёл в этой вкладке, индикатор связи, выход.
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { ROLE_LABELS } from '../lib/format.js'
import { session } from '../lib/session.js'
import ConnectionStatus from './ConnectionStatus.vue'
import Icon from './Icon.vue'

const emit = defineEmits(['logout'])
const route = useRoute()

const initials = computed(() =>
  (session.user?.display_name ?? '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase(),
)
const inContests = computed(() => route.path.startsWith('/contests'))
</script>

<template>
  <header class="app-header">
    <div class="container bar">
      <RouterLink to="/contests" class="brand" aria-label="Конкурс идей — на главную">
        <span class="logo"><Icon name="bulb" :size="20" /></span>
        <span class="brand-text">Конкурс идей</span>
      </RouterLink>

      <nav class="nav" aria-label="Разделы">
        <RouterLink to="/contests" class="nav-link" :class="{ active: inContests }" aria-label="Конкурсы">
          <Icon name="list" />
          <span>Конкурсы</span>
        </RouterLink>
        <RouterLink to="/mail" class="nav-link" active-class="active" aria-label="Почта">
          <Icon name="mail" />
          <span>Почта</span>
        </RouterLink>
      </nav>

      <div class="spacer" />

      <ConnectionStatus />

      <div class="user" :title="`Вход в этой вкладке: ${session.user?.login}`">
        <span class="avatar" :class="session.user?.role" aria-hidden="true">{{ initials }}</span>
        <span class="who">
          <strong>{{ session.user?.display_name }}</strong>
          <small>{{ ROLE_LABELS[session.user?.role] }}</small>
        </span>
      </div>

      <!-- На телефоне подписи скрыты — aria-label оставляет имя для экранных дикторов. -->
      <button class="btn btn-ghost btn-sm logout" type="button" aria-label="Выйти" @click="emit('logout')">
        <Icon name="logout" />
        <span class="logout-text">Выйти</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 20;
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(10px);
  border-bottom: 1px solid var(--border);
}

.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: var(--header-h);
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  color: var(--text);
  font-weight: 750;
  font-size: 1.02rem;
  letter-spacing: -0.01em;
}

.brand:hover {
  text-decoration: none;
}

.logo {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary), var(--phase-voting));
  color: #fff;
}

.nav {
  display: flex;
  gap: 4px;
  margin-left: 12px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: var(--radius);
  color: var(--text-2);
  font-weight: 600;
  font-size: 0.92rem;
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

.user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-left: 4px;
}

.avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--phase-submission-soft);
  color: var(--phase-submission);
  font-weight: 750;
  font-size: 0.8rem;
}

.avatar.organizer {
  background: var(--gold-soft);
  color: var(--warning);
}

.who {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.who strong {
  font-size: 0.88rem;
}

.who small {
  color: var(--text-3);
  font-size: 0.75rem;
}

@media (max-width: 900px) {
  .who {
    display: none;
  }
}

@media (max-width: 640px) {
  .brand-text,
  .nav-link span,
  .logout-text {
    display: none;
  }

  .nav {
    margin-left: 4px;
  }

  .bar {
    gap: 8px;
  }
}
</style>
