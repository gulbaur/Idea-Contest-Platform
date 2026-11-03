// Точка входа: подключить стили, маршруты и смонтировать приложение в #app.
import { createApp } from 'vue'

import App from './App.vue'
import { createAppRouter } from './router.js'
import './styles/base.css'

createApp(App).use(createAppRouter()).mount('#app')
