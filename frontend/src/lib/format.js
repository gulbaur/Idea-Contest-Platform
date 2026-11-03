// Форматирование для интерфейса: даты в часовом поясе браузера, обратный отсчёт, падежи.

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
})
const dateTimeWithYear = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** «5 ноября, 14:30»; год — только если он не текущий. */
export function formatDateTime(iso, nowMs = Date.now()) {
  const date = new Date(iso)
  const sameYear = date.getFullYear() === new Date(nowMs).getFullYear()
  return (sameYear ? dateTime : dateTimeWithYear).format(date)
}

const precise = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

/** С секундами — для ничьей: идеи часто поданы в одну и ту же минуту. */
export function formatPrecise(iso) {
  return precise.format(new Date(iso))
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
  if (days > 0) return `${days} д ${hours} ч`
  if (hours > 0) return `${hours} ч ${String(minutes).padStart(2, '0')} мин`
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

export const PHASE_LABELS = {
  submission: 'Приём идей',
  voting: 'Голосование',
  finished: 'Завершён',
}

export const ROLE_LABELS = { organizer: 'Организатор', employee: 'Участник' }
