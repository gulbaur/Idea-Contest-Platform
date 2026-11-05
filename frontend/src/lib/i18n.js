// Переводы интерфейса (D-065): русский и английский. Словари — lib/messages/<раздел>.js,
// в каждом { ru: {...}, en: {...} }; ключ — «раздел.путь.к.строке», например t('mail.title').
//
//   t('staff.invited', { name: 'Анна' })      — подстановка {name}
//   tn('common.ideas', 5)                      — форма по числу: массив [одна, несколько, много]
//                                                для ru и [one, other] для en; {n} — само число
// t() читает текущий язык, поэтому шаблоны и computed пересчитываются при его смене.
import { ref } from 'vue'

export const LOCALES = ['ru', 'en']
export const locale = ref('ru')

const AREAS = Object.fromEntries(
  Object.entries(import.meta.glob('./messages/*.js', { eager: true })).map(([path, module]) => [
    path.replace(/^.*\/(.+)\.js$/, '$1'),
    module.default,
  ]),
)

export function setLocale(value) {
  locale.value = LOCALES.includes(value) ? value : 'ru'
  if (typeof document !== 'undefined') document.documentElement.lang = locale.value
}

function lookup(lang, key) {
  const [area, ...path] = key.split('.')
  let node = AREAS[area]?.[lang]
  for (const part of path) node = node?.[part]
  return node
}

function interpolate(text, params) {
  return String(text).replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match))
}

function resolve(key) {
  // Нет перевода — русская строка (её проверяет тест словарей), чтобы не показать ключ.
  return lookup(locale.value, key) ?? lookup('ru', key)
}

export function t(key, params = {}) {
  const value = resolve(key)
  return value == null ? key : interpolate(value, params)
}

/** Индекс формы множественного числа: ru — одна / несколько / много; en — one / other. */
export function pluralIndex(n, lang = locale.value) {
  if (lang === 'en') return n === 1 ? 0 : 1
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 0
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 1
  return 2
}

export function tn(key, n, params = {}) {
  const forms = resolve(key)
  if (!Array.isArray(forms)) return key
  return interpolate(forms[pluralIndex(n)] ?? forms.at(-1), { n, ...params })
}

/** Все словари — для теста полноты переводов. */
export const dictionaries = AREAS
