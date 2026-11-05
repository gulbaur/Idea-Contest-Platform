// Точка входа: подключить стили, настройки вида, маршруты и смонтировать приложение в #app.
import { createApp } from 'vue'

import App from './App.vue'
import './lib/preferences.js' // тема и шрифт — до первой отрисовки (D-060)
import { createAppRouter } from './router.js'
import './styles/fonts.css'
import './styles/base.css'

createApp(App).use(createAppRouter()).mount('#app')
