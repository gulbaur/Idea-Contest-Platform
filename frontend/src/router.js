// Страницы приложения и проверка доступа при переходе.
// Это удобство интерфейса: настоящие права всё равно проверяет сервер (D-050).
import { watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import { locale, t } from './lib/i18n.js'
import { isAdmin, isOrganizer, session } from './lib/session.js'
import ContestCreatePage from './pages/ContestCreatePage.vue'
import ContestPage from './pages/ContestPage.vue'
import ContestsPage from './pages/ContestsPage.vue'
import EmployeesPage from './pages/EmployeesPage.vue'
import JournalPage from './pages/JournalPage.vue'
import LoginPage from './pages/LoginPage.vue'
import MailPage from './pages/MailPage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import SetupPasswordPage from './pages/SetupPasswordPage.vue'

export const routes = [
  { path: '/login', name: 'login', component: LoginPage, meta: { public: true, titleKey: 'app.pageTitle.login' } },
  // Первый вход по одноразовой ссылке (D-062): без входа.
  { path: '/setup', name: 'setup', component: SetupPasswordPage, meta: { public: true, titleKey: 'app.pageTitle.setup' } },
  { path: '/', redirect: () => (isAdmin() ? '/employees' : '/contests') },
  { path: '/contests', name: 'contests', component: ContestsPage, meta: { titleKey: 'app.pageTitle.contests' } },
  {
    path: '/contests/new',
    name: 'contest-new',
    component: ContestCreatePage,
    meta: { organizer: true, titleKey: 'app.pageTitle.contestNew' },
  },
  { path: '/contests/:id(\\d+)', name: 'contest', component: ContestPage, props: true, meta: { titleKey: 'app.pageTitle.contest' } },
  { path: '/mail', name: 'mail', component: MailPage, meta: { titleKey: 'app.pageTitle.mail' } },
  { path: '/journal', name: 'journal', component: JournalPage, meta: { staff: true, titleKey: 'app.pageTitle.journal' } },
  { path: '/settings', name: 'settings', component: SettingsPage, meta: { titleKey: 'app.pageTitle.settings' } },
  { path: '/employees', name: 'employees', component: EmployeesPage, meta: { admin: true, titleKey: 'app.pageTitle.employees' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage, meta: { titleKey: 'app.pageTitle.notFound' } },
]

export function guard(to) {
  if (!to.meta.public && !session.token) {
    return { name: 'login', query: to.fullPath !== '/contests' ? { redirect: to.fullPath } : {} }
  }
  if (to.name === 'login' && session.token) return '/'
  if (to.meta.organizer && !isOrganizer()) return '/'
  if (to.meta.admin && !isAdmin()) return '/'
  if (to.meta.staff && !isAdmin() && !isOrganizer()) return '/'
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
  // Заголовок вкладки — на языке интерфейса (D-065). При смене языка он обновляется, только если его
  // не заменила сама страница (например, тема конкурса на ContestPage).
  let routeTitle = ''
  const titleOf = (route) => `${route.meta.titleKey ? t(route.meta.titleKey) : t('app.brand')} — ${t('app.brand')}`
  router.afterEach((to) => {
    document.title = routeTitle = titleOf(to)
  })
  watch(locale, () => {
    if (document.title === routeTitle) document.title = routeTitle = titleOf(router.currentRoute.value)
  })
  return router
}
