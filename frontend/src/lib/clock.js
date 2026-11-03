// Время сервера и фазы конкурса (D-007, D-049).
//
// Фазу определяет сервер. Чтобы обратный отсчёт и переключение экрана не зависели
// от неточных часов компьютера, запоминаем сдвиг: «время сервера − время браузера».
import { reactive, readonly } from 'vue'

const state = reactive({ offsetMs: 0, now: Date.now() })

/** Запомнить время сервера из ответа (`server_time`) в момент получения ответа. */
export function syncServerTime(serverTimeIso, receivedAtMs = Date.now()) {
  const server = Date.parse(serverTimeIso)
  if (!Number.isNaN(server)) state.offsetMs = server - receivedAtMs
}

/** «Сейчас» по часам сервера, в миллисекундах. */
export function serverNow() {
  return Date.now() + state.offsetMs
}

/** Те же правила, что на сервере: ровно в момент срока раунд уже закрыт. */
export function phaseAt(contest, nowMs) {
  if (nowMs < Date.parse(contest.submission_deadline)) return 'submission'
  if (nowMs < Date.parse(contest.voting_deadline)) return 'voting'
  return 'finished'
}

/** Ближайший ещё не наступивший срок конкурса (мс) или null. */
export function nextDeadline(contest, nowMs) {
  const moments = [contest.submission_deadline, contest.voting_deadline]
    .map((iso) => Date.parse(iso))
    .filter((moment) => moment > nowMs)
  return moments.length ? Math.min(...moments) : null
}

// Один общий «тик» раз в секунду для всех обратных отсчётов на странице.
let ticker = null
let subscribers = 0

export const ticking = readonly(state)

export function startTicking() {
  subscribers += 1
  if (!ticker) {
    state.now = serverNow()
    ticker = setInterval(() => (state.now = serverNow()), 1000)
  }
}

export function stopTicking() {
  subscribers = Math.max(0, subscribers - 1)
  if (subscribers === 0 && ticker) {
    clearInterval(ticker)
    ticker = null
  }
}
