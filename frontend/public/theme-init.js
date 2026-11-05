// Тема и шрифт до запуска приложения (D-060): без этого страница на мгновение
// мелькала бы светлой темой. Отдельный файл, а не встроенный скрипт, — так его
// разрешает политика безопасности (CSP, D-059). Логика совпадает с src/lib/preferences.js.
;(function () {
  var prefs = {}
  try {
    // Сначала — настройки пользователя этой вкладки, затем — последние использованные.
    var session = JSON.parse(sessionStorage.getItem('idea-contest.session') || 'null')
    prefs = (session && session.user && session.user.preferences) ||
      JSON.parse(localStorage.getItem('idea-contest.preferences') || '{}') || {}
  } catch (e) {
    prefs = {}
  }
  var theme = prefs.theme === 'light' || prefs.theme === 'dark' ? prefs.theme : null
  if (!theme) {
    theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  var root = document.documentElement
  root.setAttribute('data-theme', theme)
  root.setAttribute('data-font', typeof prefs.font === 'string' ? prefs.font : 'inter')
  root.setAttribute('lang', prefs.locale === 'en' ? 'en' : 'ru')
  root.setAttribute('data-size', prefs.text_size === 'small' || prefs.text_size === 'large' ? prefs.text_size : 'medium')
})()
