// Снимок конкурса, который сам остаётся актуальным (D-028, D-049).
//
// Снимок перечитывается:
// - по сигналам WebSocket об этом конкурсе;
// - после переподключения (за время разрыва сигналы могли потеряться);
// - в момент ближайшего срока — запасной путь, если сигнал о сроке не дошёл.
// Ответ применяется, только если он не старее показанного (isFresher), поэтому
// поздно пришедший старый ответ не откатит экран.
import { onBeforeUnmount, ref, watch } from 'vue'

import { api } from '../lib/api.js'
import { nextDeadline, serverNow, syncServerTime } from '../lib/clock.js'
import { useSignals } from '../lib/connection.js'
import { isFresher } from '../lib/freshness.js'

const CONTEST_SIGNALS = new Set(['contest_changed', 'phase_changed', 'schedule_changed'])
const AFTER_DEADLINE_MS = 400 // запрос чуть позже срока: сервер уже точно в новой фазе
const MAX_TIMER_MS = 2_000_000_000 // setTimeout не умеет ждать дольше ~24 дней

export function useContest(idRef) {
  const snapshot = ref(null)
  const error = ref(null) // ошибка первой загрузки — показать вместо страницы
  const refreshFailed = ref(false) // не удалось обновить — показываем прежние данные
  const loading = ref(false)

  let running = null
  let queued = false
  let deadlineTimer = null
  let disposed = false

  const currentId = () => Number(idRef.value)

  async function fetchOnce() {
    const requested = currentId()
    try {
      const data = await api.contest(requested)
      if (disposed || requested !== currentId()) return
      syncServerTime(data.server_time)
      if (isFresher(data, snapshot.value)) snapshot.value = data
      error.value = null
      refreshFailed.value = false
      armDeadlineTimer()
    } catch (failure) {
      if (disposed || requested !== currentId()) return
      if (snapshot.value && failure.status !== 404) refreshFailed.value = true
      else error.value = failure
    }
  }

  /** Перечитать снимок. Несколько вызовов подряд сливаются в один-два запроса. */
  function load() {
    if (running) {
      queued = true
      return running
    }
    loading.value = !snapshot.value
    running = (async () => {
      do {
        queued = false
        await fetchOnce()
      } while (queued && !disposed)
    })().finally(() => {
      running = null
      loading.value = false
    })
    return running
  }

  function armDeadlineTimer() {
    clearTimeout(deadlineTimer)
    const contest = snapshot.value?.contest
    if (!contest) return
    const next = nextDeadline(contest, serverNow())
    if (next === null) return
    const delay = next - serverNow() + AFTER_DEADLINE_MS
    if (delay < MAX_TIMER_MS) deadlineTimer = setTimeout(load, delay)
  }

  useSignals((message) => {
    if (message.type === 'resync') {
      load()
      return
    }
    if (!CONTEST_SIGNALS.has(message.type) || message.contest_id !== currentId()) return
    // Сигнал об изменении, которое уже видно на экране, — перечитывать незачем.
    if (message.type === 'contest_changed' && snapshot.value && message.revision <= snapshot.value.revision) return
    load()
  })

  watch(
    () => idRef.value,
    () => {
      snapshot.value = null
      error.value = null
      clearTimeout(deadlineTimer)
      load()
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    disposed = true
    clearTimeout(deadlineTimer)
  })

  return { snapshot, error, refreshFailed, loading, reload: load }
}
