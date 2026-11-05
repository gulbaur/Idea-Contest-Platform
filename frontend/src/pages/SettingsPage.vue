<script setup>
// Настройки (D-060, D-065, D-066): тема, язык, шрифт и размер текста применяются сразу и
// сохраняются у пользователя на сервере — одинаковы во всех вкладках и на любом устройстве.
// Ошибка сохранения возвращает прежнее. Смена пароля — в модальном окне.
import { computed, reactive, ref } from 'vue'

import Icon from '../components/Icon.vue'
import ModalDialog from '../components/ModalDialog.vue'
import { api } from '../lib/api.js'
import { ROLE_LABELS } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import { notify } from '../lib/notify.js'
import { applyPreferences, preferences } from '../lib/preferences.js'
import { session, updateUser } from '../lib/session.js'

// Подписи — computed: пересчитываются при смене языка (D-065).
const THEMES = computed(() => [
  { value: 'system', label: t('settings.theme.system'), icon: 'monitor' },
  { value: 'light', label: t('settings.theme.light'), icon: 'sun' },
  { value: 'dark', label: t('settings.theme.dark'), icon: 'moon' },
])
// Название языка — на нём самом: так его найдёт и тот, кто не читает текущий язык.
const LOCALES = [
  { value: 'ru', label: 'Русский' },
  { value: 'en', label: 'English' },
]
const FONTS = computed(() => [
  { value: 'inter', label: 'Inter' },
  { value: 'plex', label: 'IBM Plex Sans' },
  { value: 'golos', label: 'Golos Text' },
  { value: 'system', label: t('settings.font.system') },
])
const SIZES = computed(() => ['small', 'medium', 'large'].map((value) => ({ value, label: t(`settings.size.${value}`) })))

const saving = ref(false)
const saved = ref(false)
let savedTimer

async function choose(field, value) {
  if (preferences[field] === value) return
  const previous = { ...preferences }
  applyPreferences({ ...previous, [field]: value }) // сразу видно, не дожидаясь сервера
  saving.value = true
  saved.value = false
  try {
    updateUser(await api.updatePreferences({ [field]: value }))
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 2500)
  } catch (failure) {
    applyPreferences(previous)
    notify.error(t('settings.notSaved', { error: failure.message }))
  } finally {
    saving.value = false
  }
}

// --- смена пароля (D-062) — в модальном окне -------------------------------------
const passwordOpen = ref(false)
const passwords = reactive({ current: '', next: '', repeat: '' })
const passwordError = ref('')
const changingPassword = ref(false)

function openPassword() {
  Object.assign(passwords, { current: '', next: '', repeat: '' })
  passwordError.value = ''
  passwordOpen.value = true
}

async function changePassword() {
  if (changingPassword.value) return
  passwordError.value = ''
  if (!passwords.current || !passwords.next) {
    passwordError.value = t('settings.password.empty')
    return
  }
  if (passwords.next !== passwords.repeat) {
    passwordError.value = t('settings.password.mismatch')
    return
  }
  changingPassword.value = true
  try {
    await api.changePassword(passwords.current, passwords.next)
    passwordOpen.value = false
    notify.success(t('settings.password.changed'))
  } catch (failure) {
    passwordError.value = failure.message
  } finally {
    changingPassword.value = false
  }
}
</script>

<template>
  <div class="container page settings">
    <header class="page-header">
      <div>
        <h1>{{ t('settings.title') }}</h1>
        <p class="subtitle">{{ t('settings.subtitle') }}</p>
      </div>
      <span class="status faint" role="status" aria-live="polite">
        <template v-if="saving"><span class="spinner" aria-hidden="true" /> {{ t('settings.saving') }}</template>
        <template v-else-if="saved"><Icon name="check" :size="16" /> {{ t('settings.saved') }}</template>
      </span>
    </header>

    <section class="card list">
      <h2 class="overline section-title">{{ t('settings.appearance') }}</h2>

      <div class="setting">
        <span id="theme-label" class="name">{{ t('settings.theme.title') }}</span>
        <div class="segmented" role="radiogroup" aria-labelledby="theme-label">
          <button
            v-for="option in THEMES"
            :key="option.value"
            type="button"
            role="radio"
            :aria-checked="preferences.theme === option.value"
            :class="{ active: preferences.theme === option.value }"
            @click="choose('theme', option.value)"
          >
            <Icon :name="option.icon" :size="15" /> {{ option.label }}
          </button>
        </div>
      </div>

      <div class="setting">
        <span class="name">
          <span id="language-label">{{ t('settings.language.title') }}</span>
          <span class="faint">{{ t('settings.language.hint') }}</span>
        </span>
        <div class="segmented" role="radiogroup" aria-labelledby="language-label">
          <button
            v-for="option in LOCALES"
            :key="option.value"
            type="button"
            role="radio"
            :lang="option.value"
            :aria-checked="preferences.locale === option.value"
            :class="{ active: preferences.locale === option.value }"
            @click="choose('locale', option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>

      <div class="setting">
        <label class="name" for="font-select">{{ t('settings.font.title') }}</label>
        <select id="font-select" class="select compact" :value="preferences.font" @change="choose('font', $event.target.value)">
          <option v-for="option in FONTS" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
      </div>

      <div class="setting">
        <span id="size-label" class="name">{{ t('settings.size.title') }}</span>
        <div class="segmented" role="radiogroup" aria-labelledby="size-label">
          <button
            v-for="option in SIZES"
            :key="option.value"
            type="button"
            role="radio"
            :aria-checked="preferences.text_size === option.value"
            :class="{ active: preferences.text_size === option.value }"
            @click="choose('text_size', option.value)"
          >
            {{ option.label }}
          </button>
        </div>
      </div>
    </section>

    <section class="card list">
      <h2 class="overline section-title">{{ t('settings.account') }}</h2>
      <div class="setting">
        <span class="name">{{ t('settings.profile.name') }}</span>
        <span class="value">{{ session.user?.display_name }}</span>
      </div>
      <div class="setting">
        <span class="name">{{ t('settings.profile.login') }}</span>
        <span class="value mono">{{ session.user?.login }}</span>
      </div>
      <div class="setting">
        <span class="name">{{ t('settings.profile.role') }}</span>
        <span class="value">{{ ROLE_LABELS[session.user?.role] }}</span>
      </div>
      <div class="setting">
        <span class="name">{{ t('settings.password.title') }}</span>
        <button class="btn btn-sm" type="button" @click="openPassword">{{ t('settings.password.open') }}</button>
      </div>
      <p class="faint footnote">{{ t('settings.profile.hint') }}</p>
    </section>

    <ModalDialog v-if="passwordOpen" :title="t('settings.password.dialog')" @close="passwordOpen = false">
      <form class="stack" novalidate @submit.prevent="changePassword">
        <p class="muted">{{ t('settings.password.text') }}</p>
        <div class="field">
          <label for="current-password">{{ t('settings.password.current') }}</label>
          <input id="current-password" v-model="passwords.current" class="input" type="password" autocomplete="current-password" />
        </div>
        <div class="field">
          <label for="next-password">{{ t('settings.password.next') }}</label>
          <input id="next-password" v-model="passwords.next" class="input" type="password" autocomplete="new-password" />
          <span class="hint">{{ t('settings.password.nextHint') }}</span>
        </div>
        <div class="field">
          <label for="repeat-password">{{ t('settings.password.repeat') }}</label>
          <input id="repeat-password" v-model="passwords.repeat" class="input" type="password" autocomplete="new-password" />
        </div>
        <div v-if="passwordError" class="notice notice-danger" role="alert"><Icon name="alert" class="icon" /> {{ passwordError }}</div>
        <div class="actions">
          <button class="btn" type="button" @click="passwordOpen = false">{{ t('common.cancel') }}</button>
          <button class="btn btn-primary" type="submit" :disabled="changingPassword">
            <span v-if="changingPassword" class="spinner" aria-hidden="true" /> {{ t('settings.password.submit') }}
          </button>
        </div>
      </form>
    </ModalDialog>
  </div>
</template>

<style scoped>
/* Узкая колонка: короткие строки настроек не растягиваются на весь экран. */
.settings .page-header,
.settings .list {
  max-width: 760px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
}

/* Пустая строка статуса не занимает места (на телефоне она переносилась под заголовок). */
.status:empty {
  display: none;
}

.list {
  margin-bottom: 16px;
  padding: 4px 20px;
}

.section-title {
  margin: 14px 0 6px;
}

/* Строка настройки: название слева, переключатель справа. */
.setting {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  min-height: 52px;
  padding: 10px 0;
  border-top: 1px solid var(--border);
}

.section-title + .setting {
  border-top: 0;
}

.name {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-weight: 500;
}

.name .faint {
  font-weight: 400;
}

.value {
  color: var(--text-2);
  overflow-wrap: anywhere;
}

.compact {
  width: auto;
  min-width: 180px;
}

.footnote {
  padding: 4px 0 14px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 520px) {
  .list {
    padding: 4px 16px;
  }

  /* На телефоне переключатель — под названием и во всю ширину строки. */
  .setting .segmented,
  .setting .compact {
    width: 100%;
  }

  /* Три варианта темы помещаются и при крупном тексте: без значков, с переносом слов. */
  .setting .segmented button {
    flex: 1 1 0;
    justify-content: center;
    min-width: 0;
    padding: 6px;
    white-space: normal;
    text-align: center;
  }

  .setting .segmented .icon {
    display: none;
  }
}
</style>
