// Диалог подтверждения необратимых действий (D-050). Показывает ConfirmHost.vue.
//   if (await confirmAction({ title, message, confirmText, danger: true })) { … }
import { reactive } from 'vue'

import { t } from './i18n.js'

export const dialog = reactive({ open: false, title: '', message: '', confirmText: '', danger: false })
let resolver = null

export function confirmAction({ title, message, confirmText = t('app.confirm'), danger = false }) {
  if (resolver) resolver(false) // предыдущий диалог закрывается как «отмена»
  Object.assign(dialog, { open: true, title, message, confirmText, danger })
  return new Promise((resolve) => (resolver = resolve))
}

export function answer(confirmed) {
  dialog.open = false
  const resolve = resolver
  resolver = null
  if (resolve) resolve(confirmed)
}
