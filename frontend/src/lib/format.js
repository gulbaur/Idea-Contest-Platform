// Форматирование для интерфейса: даты в часовом поясе браузера, обратный отсчёт, падежи.
import { locale, t } from './i18n.js'

// Даты — на языке интерфейса (D-065). Форматировщики создаются один раз на язык.
const formatters = new Map()

function formatter(kind) {
  const tag = locale.value === 'en' ? 'en-GB' : 'ru-RU'
  const key = `${tag}:${kind}`
  if (!formatters.has(key)) {
    const options = { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' }
    if (kind === 'year') options.year = 'numeric'
    if (kind === 'precise') options.second = '2-digit'
    formatters.set(key, new Intl.DateTimeFormat(tag, options))
  }
  return formatters.get(key)
}

/** «5 ноября, 14:30»; год — только если он не текущий. */
export function formatDateTime(iso, nowMs = Date.now()) {
  const date = new Date(iso)
  const sameYear = date.getFullYear() === new Date(nowMs).getFullYear()
  return formatter(sameYear ? 'date' : 'year').format(date)
}

/** С секундами — для ничьей: идеи часто поданы в одну и ту же минуту. */
export function formatPrecise(iso) {
  return formatter('precise').format(new Date(iso))
}

/** Часовой пояс браузера для подсказки: «UTC+5». */
export function timezoneLabel(date = new Date()) {
  const minutes = -date.getTimezoneOffset()
  const sign = minutes >= 0 ? '+' : '−'
  const hours = Math.floor(Math.abs(minutes) / 60)
  const rest = Math.abs(minutes) % 60
  return `UTC${sign}${hours}${rest ? `:${String(rest).padStart(2, '0')}` : ''}`
}

/** Русское склонение: plural(5, ['идея', 'идеи', 'идей']) → «идей». */
export function plural(n, [one, few, many]) {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

export const countOf = (n, forms) => `${n} ${plural(n, forms)}`

/** Обратный отсчёт: «2 д 3 ч», «3 ч 05 мин», «4:07», «0:09». */
export function formatCountdown(ms) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  if (days > 0) return t('common.countdown.days', { d: days, h: hours })
  if (hours > 0) return t('common.countdown.hours', { h: hours, m: String(minutes).padStart(2, '0') })
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** Значение для <input type="datetime-local"> в часовом поясе браузера. */
export function toLocalInput(ms) {
  const date = new Date(ms)
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** Обратно: местное время из поля ввода → ISO 8601 в UTC с «Z» (сервер требует пояс). */
export function localInputToIso(value) {
  if (!value) return null
  const date = new Date(value) // строка без пояса толкуется браузером как местное время
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

// Подписи — свойства-«геттеры»: читаются на текущем языке при каждом обращении (D-065).
export const PHASE_LABELS = {
  get submission() {
    return t('common.phase.submission')
  },
  get voting() {
    return t('common.phase.voting')
  },
  get finished() {
    return t('common.phase.finished')
  },
}

export const ROLE_LABELS = {
  get admin() {
    return t('common.role.admin')
  },
  get organizer() {
    return t('common.role.organizer')
  },
  get employee() {
    return t('common.role.employee')
  },
}
