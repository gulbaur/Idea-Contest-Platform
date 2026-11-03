// Вход этой вкладки (D-003): токен и пользователь хранятся в sessionStorage,
// поэтому в каждой вкладке браузера — свой вход, и вкладки не мешают друг другу.
import { reactive } from 'vue'

const KEY = 'idea-contest.session'

function read() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY))
    return saved && saved.token && saved.user ? saved : null
  } catch {
    return null // хранилище недоступно (например, запрещено настройками браузера)
  }
}

function write(value) {
  try {
    if (value) sessionStorage.setItem(KEY, JSON.stringify(value))
    else sessionStorage.removeItem(KEY)
  } catch {
    // Без хранилища вход живёт до перезагрузки страницы — приложение всё равно работает.
  }
}

const saved = read()

export const session = reactive({
  token: saved?.token ?? null,
  user: saved?.user ?? null,
})

export function setSession({ token, user }) {
  session.token = token
  session.user = user
  write({ token, user })
}

export function updateUser(user) {
  session.user = user
  write({ token: session.token, user })
}

export function clearSession() {
  session.token = null
  session.user = null
  write(null)
}

export const isOrganizer = () => session.user?.role === 'organizer'
