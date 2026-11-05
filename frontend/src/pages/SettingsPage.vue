<script setup>
// Настройки (D-060, D-065): тема, язык и шрифт применяются сразу и сохраняются у пользователя на сервере —
// они одинаковы во всех его вкладках и на любом устройстве. Ошибка сохранения возвращает прежнее.
import { computed, reactive, ref } from 'vue'

import Icon from '../components/Icon.vue'
import { api } from '../lib/api.js'
import { ROLE_LABELS } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import { notify } from '../lib/notify.js'
import { applyPreferences, preferences } from '../lib/preferences.js'
import { session, updateUser } from '../lib/session.js'

// Подписи — computed: пересчитываются при смене языка (D-065).
const THEME_OPTIONS = computed(() => [
  { value: 'system', label: t('settings.theme.system'), hint: t('settings.theme.systemHint'), icon: 'monitor' },
  { value: 'light', label: t('settings.theme.light'), hint: t('settings.theme.lightHint'), icon: 'sun' },
  { value: 'dark', label: t('settings.theme.dark'), hint: t('settings.theme.darkHint'), icon: 'moon' },
])
// Название языка — на нём самом: так его найдёт и тот, кто не читает текущий язык.
const LOCALE_OPTIONS = [
  { value: 'ru', label: 'Русский', sample: 'Конкурс идей' },
  { value: 'en', label: 'English', sample: 'Idea Contest' },
]
const FONT_OPTIONS = computed(() => [
  { value: 'inter', label: 'Inter', hint: t('settings.font.interHint'), family: 'var(--font-inter)' },
  { value: 'plex', label: 'IBM Plex Sans', hint: t('settings.font.plexHint'), family: 'var(--font-plex)' },
  { value: 'golos', label: 'Golos Text', hint: t('settings.font.golosHint'), family: 'var(--font-golos)' },
  { value: 'system', label: t('settings.font.system'), hint: t('settings.font.systemHint'), family: 'var(--font-system)' },
])

const saving = ref(false)
const saved = ref(false)
let savedTimer

// --- смена пароля (D-062) ---------------------------------------------------------
const passwords = reactive({ current: '', next: '', repeat: '' })
const passwordError = ref('')
const changingPassword = ref(false)

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
    Object.assign(passwords, { current: '', next: '', repeat: '' })
    notify.success(t('settings.password.changed'))
  } catch (failure) {
    passwordError.value = failure.message
  } finally {
    changingPassword.value = false
  }
}

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

    <section class="card section">
      <div class="section-head">
        <h2>{{ t('settings.theme.title') }}</h2>
        <p class="muted">{{ t('settings.theme.text') }}</p>
      </div>
      <fieldset class="options themes">
        <legend class="sr-only">{{ t('settings.theme.title') }}</legend>
        <label
          v-for="option in THEME_OPTIONS"
          :key="option.value"
          class="option"
          :class="{ selected: preferences.theme === option.value }"
        >
          <input
            type="radio"
            name="theme"
            class="sr-only"
            :value="option.value"
            :checked="preferences.theme === option.value"
            @change="choose('theme', option.value)"
          />
          <span class="preview" :class="`preview-${option.value}`" aria-hidden="true">
            <span class="bar" /><span class="line" /><span class="line short" />
          </span>
          <span class="option-text">
            <span class="option-title"><Icon :name="option.icon" :size="16" /> {{ option.label }}</span>
            <span class="faint">{{ option.hint }}</span>
          </span>
        </label>
      </fieldset>
    </section>

    <section class="card section">
      <div class="section-head">
        <h2>{{ t('settings.language.title') }}</h2>
        <p class="muted">{{ t('settings.language.text') }}</p>
      </div>
      <fieldset class="options languages">
        <legend class="sr-only">{{ t('settings.language.title') }}</legend>
        <label
          v-for="option in LOCALE_OPTIONS"
          :key="option.value"
          class="option"
          :class="{ selected: preferences.locale === option.value }"
          :lang="option.value"
        >
          <input
            type="radio"
            name="locale"
            class="sr-only"
            :value="option.value"
            :checked="preferences.locale === option.value"
            @change="choose('locale', option.value)"
          />
          <span class="option-text">
            <span class="option-title">{{ option.label }}</span>
            <span class="faint">{{ option.sample }}</span>
          </span>
        </label>
      </fieldset>
    </section>

    <section class="card section">
      <div class="section-head">
        <h2>{{ t('settings.font.title') }}</h2>
        <p class="muted">{{ t('settings.font.text') }}</p>
      </div>
      <fieldset class="options fonts">
        <legend class="sr-only">{{ t('settings.font.title') }}</legend>
        <label
          v-for="option in FONT_OPTIONS"
          :key="option.value"
          class="option"
          :class="{ selected: preferences.font === option.value }"
        >
          <input
            type="radio"
            name="font"
            class="sr-only"
            :value="option.value"
            :checked="preferences.font === option.value"
            @change="choose('font', option.value)"
          />
          <span class="sample" :style="{ fontFamily: option.family }" aria-hidden="true">Аа Bb 123</span>
          <span class="option-text">
            <span class="option-title" :style="{ fontFamily: option.family }">{{ option.label }}</span>
            <span class="faint">{{ option.hint }}</span>
          </span>
        </label>
      </fieldset>
    </section>

    <section class="card section">
      <div class="section-head">
        <h2>{{ t('settings.password.title') }}</h2>
        <p class="muted">{{ t('settings.password.text') }}</p>
      </div>
      <form class="stack password-form" novalidate @submit.prevent="changePassword">
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
        <div>
          <button class="btn btn-primary" type="submit" :disabled="changingPassword">
            <span v-if="changingPassword" class="spinner" aria-hidden="true" /> {{ t('settings.password.submit') }}
          </button>
        </div>
      </form>
    </section>

    <section class="card section">
      <div class="section-head">
        <h2>{{ t('settings.profile.title') }}</h2>
        <p class="muted">{{ t('settings.profile.text') }}</p>
      </div>
      <dl class="profile">
        <div>
          <dt>{{ t('settings.profile.name') }}</dt>
          <dd>{{ session.user?.display_name }}</dd>
        </div>
        <div>
          <dt>{{ t('settings.profile.login') }}</dt>
          <dd class="mono">{{ session.user?.login }}</dd>
        </div>
        <div>
          <dt>{{ t('settings.profile.role') }}</dt>
          <dd>{{ ROLE_LABELS[session.user?.role] }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
}

.section {
  display: grid;
  grid-template-columns: minmax(0, 220px) minmax(0, 1fr);
  gap: 24px;
  margin-bottom: 16px;
}

.section-head h2 {
  font-size: var(--text-lg);
}

.section-head p {
  margin-top: 4px;
  font-size: var(--text-sm);
}

.options {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
  min-width: 0;
}

.themes {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.fonts,
.languages {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.option {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.option:hover {
  border-color: var(--border-strong);
}

.option.selected {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary);
}

/* Фокус с клавиатуры на скрытой радиокнопке показываем на всей карточке. */
.option:has(input:focus-visible) {
  box-shadow: var(--focus);
}

.option-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.option-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

/* Миниатюры тем: свои цвета, не зависящие от текущей темы. */
.preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 64px;
  padding: 10px;
  border: 1px solid #e4e7ec;
  border-radius: var(--radius);
  background: #f6f7f9;
}

.preview .bar {
  width: 40%;
  height: 8px;
  border-radius: 4px;
  background: #2563eb;
}

.preview .line {
  height: 6px;
  border-radius: 3px;
  background: #d0d5dd;
}

.preview .line.short {
  width: 60%;
}

.preview-dark {
  border-color: #262b34;
  background: #13161b;
}

.preview-dark .line {
  background: #353c47;
}

.preview-system {
  border-color: #d0d5dd;
  background: linear-gradient(115deg, #f6f7f9 50%, #13161b 50%);
}

.preview-system .line {
  background: #8b93a1;
}

.sample {
  font-size: var(--text-2xl);
  font-weight: 500;
  line-height: 1.2;
}

.password-form {
  max-width: 420px;
}

.profile {
  display: grid;
  gap: 12px;
  margin: 0;
}

.profile div {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px;
}

dt {
  color: var(--text-3);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

@media (max-width: 760px) {
  .section {
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
}

@media (max-width: 520px) {
  .themes,
  .fonts,
  .languages {
    grid-template-columns: minmax(0, 1fr);
  }

  .preview {
    display: none;
  }
}
</style>
