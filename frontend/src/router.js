// Страницы приложения и проверка доступа при переходе.
// Это удобство интерфейса: настоящие права всё равно проверяет сервер (D-050).
import { createRouter, createWebHistory } from 'vue-router'

import { isAdmin, isOrganizer, session } from './lib/session.js'
import ContestCreatePage from './pages/ContestCreatePage.vue'
import ContestPage from './pages/ContestPage.vue'
import ContestsPage from './pages/ContestsPage.vue'
import EmployeesPage from './pages/EmployeesPage.vue'
import LoginPage from './pages/LoginPage.vue'
import MailPage from './pages/MailPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import SetupPasswordPage from './pages/SetupPasswordPage.vue'

export const routes = [
  { path: '/login', name: 'login', component: LoginPage, meta: { public: true, title: 'Вход' } },
  // Первый вход по одноразовой ссылке (D-062): без входа.
  { path: '/setup', name: 'setup', component: SetupPasswordPage, meta: { public: true, title: 'Задать пароль' } },
  { path: '/', redirect: () => (isAdmin() ? '/employees' : '/contests') },
  { path: '/contests', name: 'contests', component: ContestsPage, meta: { title: 'Конкурсы' } },
  {
    path: '/contests/new',
    name: 'contest-new',
    component: ContestCreatePage,
    meta: { organizer: true, title: 'Новый конкурс' },
  },
  { path: '/contests/:id(\\d+)', name: 'contest', component: ContestPage, props: true, meta: { title: 'Конкурс' } },
  { path: '/mail', name: 'mail', component: MailPage, meta: { title: 'Почта' } },
  { path: '/settings', name: 'settings', component: SettingsPage, meta: { title: 'Настройки' } },
  { path: '/employees', name: 'employees', component: EmployeesPage, meta: { admin: true, title: 'Сотрудники' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage, meta: { title: 'Не найдено' } },
]

export function guard(to) {
  if (!to.meta.public && !session.token) {
    return { name: 'login', query: to.fullPath !== '/contests' ? { redirect: to.fullPath } : {} }
  }
  if (to.name === 'login' && session.token) return '/'
  if (to.meta.organizer && !isOrganizer()) return '/'
  if (to.meta.admin && !isAdmin()) return '/'
  // Администратор конкурсов не ведёт и в них не участвует (D-062) — его раздел «Сотрудники».
  if (isAdmin() && to.path.startsWith('/contests')) return { name: 'employees' }
  return true
}

export function createAppRouter(history = createWebHistory()) {
  const router = createRouter({
    history,
    routes,
    scrollBehavior: (to, from, saved) => saved ?? { top: 0 },
  })
  router.beforeEach(guard)
  router.afterEach((to) => {
    document.title = `${to.meta.title ?? 'Конкурс идей'} — Конкурс идей`
  })
  return router
}
