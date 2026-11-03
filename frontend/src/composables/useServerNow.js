// «Сейчас» по часам сервера, обновляется раз в секунду, пока компонент на экране.
import { computed, onBeforeUnmount, onMounted } from 'vue'

import { startTicking, stopTicking, ticking } from '../lib/clock.js'

export function useServerNow() {
  onMounted(startTicking)
  onBeforeUnmount(stopTicking)
  return computed(() => ticking.now)
}
