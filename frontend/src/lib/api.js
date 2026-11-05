// Запросы к backend (D-049). Все адреса — относительные (/api/...): nginx передаёт их
// backend, поэтому браузер работает с одним адресом и CORS не нужен (D-048).
import { session } from './session.js'

export class ApiError extends Error {
  /**
   * @param {number} status  HTTP-код; 0 — сервер недоступен
   * @param {string} message понятное сообщение для пользователя
   * @param {any} detail     `detail` из ответа сервера (например, актуальная идея при 409)
   */
  constructor(status, message, detail = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

let unauthorizedHandler = () => {}

/** Что делать, если сервер ответил 401 на запрос с токеном (сессия истекла или выход). */
export function onUnauthorized(handler) {
  unauthorizedHandler = handler
}

const FIELD_LABELS = {
  login: 'Логин',
  password: 'Пароль',
  topic: 'Тема',
  title: 'Название',
  description: 'Описание',
  submission_deadline: 'Срок приёма идей',
  voting_deadline: 'Срок голосования',
  participant_ids: 'Участники',
  display_name: 'Имя',
  email: 'Почта',
  role: 'Роль',
}

function validationMessage(errors) {
  // Ответ 422 от Pydantic — список ошибок по полям. Показываем первую понятным текстом.
  const first = errors[0] ?? {}
  const field = FIELD_LABELS[first.loc?.at(-1)] ?? 'Данные'
  switch (first.type) {
    case 'string_too_short':
      return `${field}: поле не может быть пустым.`
    case 'string_too_long':
      return `${field}: не больше ${first.ctx?.max_length} символов.`
    case 'too_short':
      return `${field}: выберите хотя бы одного.`
    case 'timezone_aware':
    case 'datetime_from_date_parsing':
    case 'datetime_parsing':
      return `${field}: укажите дату и время.`
    default:
      return `${field}: ${String(first.msg ?? 'неверное значение').replace(/^Value error, /, '')}.`
  }
}

export function messageFor(status, data) {
  const detail = data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return validationMessage(detail)
  if (detail && typeof detail === 'object' && detail.message) return detail.message
  if (status >= 500) return 'Ошибка на сервере. Попробуйте ещё раз чуть позже.'
  return `Запрос не выполнен (код ${status}).`
}

export async function request(method, path, { body, query } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (session.token) headers.Authorization = `Bearer ${session.token}`

  let url = `/api${path}`
  if (query) {
    const params = new URLSearchParams(
      Object.entries(query).filter(([, value]) => value !== undefined && value !== null && value !== ''),
    )
    if ([...params].length) url += `?${params}`
  }

  let response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте подключение и попробуйте ещё раз.')
  }

  const text = response.status === 204 ? '' : await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null // например, страница ошибки прокси вместо JSON
    }
  }

  if (!response.ok) {
    if (response.status === 401 && headers.Authorization) unauthorizedHandler()
    throw new ApiError(response.status, messageFor(response.status, data), data?.detail ?? null)
  }
  return data
}

// Все запросы приложения в одном месте — формы данных описаны в README (раздел API).
export const api = {
  health: () => request('GET', '/health'),
  login: (login, password) => request('POST', '/auth/login', { body: { login, password } }),
  logout: () => request('POST', '/auth/logout'),
  me: () => request('GET', '/auth/me'),
  demo: () => request('GET', '/auth/demo'),
  updatePreferences: (changes) => request('PATCH', '/auth/me/preferences', { body: changes }),
  changePassword: (current_password, new_password) =>
    request('POST', '/auth/password', { body: { current_password, new_password } }),
  setupCheck: (token) => request('POST', '/auth/setup/check', { body: { token } }),
  setup: (token, password) => request('POST', '/auth/setup', { body: { token, password } }),

  staff: () => request('GET', '/admin/users'),
  inviteStaff: (payload) => request('POST', '/admin/users', { body: payload }),
  updateStaff: (id, changes) => request('PATCH', `/admin/users/${id}`, { body: changes }),
  disableStaff: (id) => request('POST', `/admin/users/${id}/disable`),
  enableStaff: (id) => request('POST', `/admin/users/${id}/enable`),
  issueSetupLink: (id) => request('POST', `/admin/users/${id}/setup-link`),
  audit: (query) => request('GET', '/admin/audit', { query }),

  employees: () => request('GET', '/users'),
  contests: () => request('GET', '/contests'),
  contest: (id) => request('GET', `/contests/${id}`),
  participants: (id) => request('GET', `/contests/${id}/participants`),
  createContest: (payload) => request('POST', '/contests', { body: payload }),

  submitIdea: (contestId, payload) => request('POST', `/contests/${contestId}/ideas`, { body: payload }),
  updateIdea: (ideaId, payload) => request('PUT', `/ideas/${ideaId}`, { body: payload }),
  deleteIdea: (ideaId) => request('DELETE', `/ideas/${ideaId}`),
  vote: (ideaId) => request('POST', `/ideas/${ideaId}/vote`),
  revokeVote: (ideaId) => request('DELETE', `/ideas/${ideaId}/vote`),

  emails: (query) => request('GET', '/emails', { query }),
}
