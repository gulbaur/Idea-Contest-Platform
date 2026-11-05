// Виды писем почтовой заглушки (D-045, D-063): подпись, значок и цвет — для «Входящих» и журнала.
// Подпись — «геттер»: читается на текущем языке при каждом обращении (D-065).
import { t } from './i18n.js'

const entry = (key, icon, tone) => ({
  get label() {
    return t(`mail.kind.${key}`)
  },
  icon,
  tone,
})

export const KINDS = {
  invitation: entry('invitation', 'users', 'badge-primary'),
  reminder_submission: entry('reminder_submission', 'bell', 'badge-warning'),
  voting_open: entry('voting_open', 'vote', 'badge-primary'),
  reminder_voting: entry('reminder_voting', 'bell', 'badge-warning'),
  final: entry('final', 'trophy', 'badge-gold'),
  org_submission_soon: entry('org_submission_soon', 'clock', ''),
  org_submission_closed: entry('org_submission_closed', 'flag', ''),
  org_voting_soon: entry('org_voting_soon', 'clock', ''),
  org_job_failed: entry('org_job_failed', 'alert', 'badge-danger'),
}

export const kindOf = (kind) => KINDS[kind] ?? { label: kind, icon: 'mail', tone: '' }
