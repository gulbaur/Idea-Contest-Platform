// Страницы приложения и проверка доступа при переходе.
// Это удобство интерфейса: настоящие права всё равно проверяет сервер (D-050).
import { createRouter, createWebHistory } from 'vue-router'

import { isOrganizer, session } from './lib/session.js'
import ContestCreatePage from './pages/ContestCreatePage.vue'
import ContestPage from './pages/ContestPage.vue'
import ContestsPage from './pages/ContestsPage.vue'
import LoginPage from './pages/LoginPage.vue'
import MailPage from './pages/MailPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'

export const routes = [
  { path: '/login', name: 'login', component: LoginPage, meta: { public: true, title: 'Вход' } },
  { path: '/', redirect: '/contests' },
  { path: '/contests', name: 'contests', component: ContestsPage, meta: { title: 'Конкурсы' } },
  {
    path: '/contests/new',
    name: 'contest-new',
    component: ContestCreatePage,
    meta: { organizer: true, title: 'Новый конкурс' },
  },
  { path: '/contests/:id(\\d+)', name: 'contest', component: ContestPage, props: true, meta: { title: 'Конкурс' } },
  { path: '/mail', name: 'mail', component: MailPage, meta: { title: 'Почта' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage, meta: { title: 'Не найдено' } },
]

export function guard(to) {
  if (!to.meta.public && !session.token) {
    return { name: 'login', query: to.fullPath !== '/contests' ? { redirect: to.fullPath } : {} }
  }
  if (to.name === 'login' && session.token) return { name: 'contests' }
  if (to.meta.organizer && !isOrganizer()) return { name: 'contests' }
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
