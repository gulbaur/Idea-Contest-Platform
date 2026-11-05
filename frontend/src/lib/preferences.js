// Настройки вида (D-060): тема и шрифт. Хранятся у пользователя на сервере и следуют за ним
// в любой вкладке и на любом устройстве. Копия последних настроек — в localStorage: по ней
// страница входа и первая отрисовка (public/theme-init.js) сразу выглядят как надо.
import { reactive } from 'vue'

import { LOCALES, setLocale } from './i18n.js'

export const THEMES = ['system', 'light', 'dark']
export const FONTS = ['inter', 'plex', 'golos', 'system']
export const DEFAULTS = Object.freeze({ theme: 'system', font: 'inter', locale: 'ru' })

const KEY = 'idea-contest.preferences'

function readCache() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) ?? {}
  } catch {
    return {}
  }
}

function writeCache(value) {
  try {
    localStorage.setItem(KEY, JSON.stringify(value))
  } catch {
    // Хранилище недоступно — настройки всё равно применяются до перезагрузки.
  }
}

/** Только известные значения; неизвестное (старый кеш, чужие данные) заменяется значением по умолчанию. */
export function normalize(value = {}) {
  return {
    theme: THEMES.includes(value.theme) ? value.theme : DEFAULTS.theme,
    font: FONTS.includes(value.font) ? value.font : DEFAULTS.font,
    locale: LOCALES.includes(value.locale) ? value.locale : DEFAULTS.locale,
  }
}

export const preferences = reactive(normalize(readCache()))

const darkQuery = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null

/** Тема, которую видно на экране: «как в системе» превращается в светлую или тёмную. */
export function resolvedTheme(theme = preferences.theme) {
  if (theme === 'light' || theme === 'dark') return theme
  return darkQuery?.matches ? 'dark' : 'light'
}

function paint() {
  const root = document.documentElement
  root.dataset.theme = resolvedTheme()
  root.dataset.font = preferences.font
  setLocale(preferences.locale)
}

/** Применить настройки (после входа, смены в «Настройках» или выхода) и запомнить их в браузере. */
export function applyPreferences(value) {
  Object.assign(preferences, normalize(value))
  writeCache({ ...preferences })
  paint()
}

// Тема «как в системе» меняется вслед за системой без перезагрузки страницы.
darkQuery?.addEventListener?.('change', () => {
  if (preferences.theme === 'system') paint()
})

paint()
