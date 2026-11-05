// Виды писем почтовой заглушки (D-045, D-063): подпись, значок и цвет — для «Входящих» и журнала.
export const KINDS = {
  invitation: { label: 'Приглашение', icon: 'users', tone: 'badge-primary' },
  reminder_submission: { label: 'Напоминание о подаче', icon: 'bell', tone: 'badge-warning' },
  voting_open: { label: 'Голосование открыто', icon: 'vote', tone: 'badge-primary' },
  reminder_voting: { label: 'Напоминание о голосовании', icon: 'bell', tone: 'badge-warning' },
  final: { label: 'Итоги', icon: 'trophy', tone: 'badge-gold' },
  org_submission_soon: { label: 'Скоро конец приёма идей', icon: 'clock', tone: '' },
  org_submission_closed: { label: 'Приём идей завершён', icon: 'flag', tone: '' },
  org_voting_soon: { label: 'Скоро конец голосования', icon: 'clock', tone: '' },
  org_job_failed: { label: 'Сбой рассылки', icon: 'alert', tone: 'badge-danger' },
}

export const kindOf = (kind) => KINDS[kind] ?? { label: kind, icon: 'mail', tone: '' }
