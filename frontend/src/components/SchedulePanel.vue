<script setup>
// Расписание конкурса для организатора (D-051): напоминания и подведение итогов.
import { RouterLink } from 'vue-router'

import { formatCountdown, formatDateTime } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import Icon from './Icon.vue'

const props = defineProps({
  schedule: { type: Array, required: true },
  contestId: { type: Number, required: true },
  now: { type: Number, required: true },
  ideas: { type: Array, default: () => [] }, // чтобы назвать победителя по названию, а не по номеру
})

// Названия заданий и состояний — через t() в шаблоне: пересчитываются при смене языка (D-065).
const KIND_ICON = { remind_submission: 'bell', open_voting: 'vote', remind_voting: 'bell', finalize: 'flag' }

// Пояснение сервера приходит по-русски («писем: 4; победитель — идея 12», «раунд уже закрыт»).
// Части через «; » узнаём по русскому тексту и показываем человеческими словами на языке интерфейса;
// незнакомую часть оставляем как есть.
const NOTE_PHRASES = {
  'идей нет': 'noIdeas',
  'идей нет — голосовать не за что': 'nothingToVote',
  'раунд уже закрыт': 'roundClosed',
  'голосование уже завершилось': 'votingEnded',
  'раунд короче срока напоминания': 'roundTooShort',
  'конкурс создан до появления этого письма': 'createdBefore',
}

function describePart(part) {
  const sent = part.match(/^писем: (\d+)$/)
  if (sent) {
    return Number(sent[1]) === 0
      ? t('contest.schedule.note.noRecipients')
      : t('contest.schedule.note.sent', { n: sent[1] })
  }
  const winner = part.match(/^победитель — идея (\d+)$/)
  if (winner) {
    const idea = props.ideas.find((item) => item.id === Number(winner[1]))
    return idea
      ? t('contest.schedule.note.winner', { title: idea.title })
      : t('contest.schedule.note.winnerId', { id: winner[1] })
  }
  return NOTE_PHRASES[part] ? t(`contest.schedule.note.${NOTE_PHRASES[part]}`) : part
}

function describe(note) {
  return note.split('; ').map(describePart).join('; ')
}

const STATUS_TONE = { pending: '', done: 'badge-success', skipped: 'badge-warning', failed: 'badge-danger' }
</script>

<template>
  <section class="card">
    <div class="card-title">
      <Icon name="calendar" />
      <h2>{{ t('contest.schedule.title') }}</h2>
    </div>
    <ul class="jobs">
      <li v-for="job in schedule" :key="job.kind" class="job" :data-kind="job.kind">
        <span class="mark" :class="job.status"><Icon :name="KIND_ICON[job.kind]" :size="16" /></span>
        <div class="body">
          <strong>{{ t(`contest.schedule.kind.${job.kind}`) }}</strong>
          <div class="when">
            <span class="badge" :class="STATUS_TONE[job.status]">{{ t(`contest.schedule.status.${job.status}`) }}</span>
            <span class="faint">{{ formatDateTime(job.finished_at ?? job.run_at) }}</span>
          </div>
          <div v-if="job.status === 'pending' && Date.parse(job.run_at) > now" class="note faint">
            {{ t('contest.schedule.in', { time: formatCountdown(Date.parse(job.run_at) - now) }) }}
          </div>
          <div v-if="job.note" class="note">{{ describe(job.note) }}</div>
        </div>
      </li>
    </ul>
    <RouterLink class="btn btn-soft btn-sm mail-link" :to="{ name: 'journal', query: { contest: contestId } }">
      <Icon name="mail" /> {{ t('contest.schedule.mail') }}
    </RouterLink>
  </section>
</template>

<style scoped>
.jobs {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin: 0 0 16px;
  padding: 0;
  list-style: none;
}

.job {
  display: flex;
  gap: 12px;
}

.mark {
  display: grid;
  place-items: center;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-3);
}

.mark.done {
  background: var(--success-soft);
  color: var(--success);
}

.mark.skipped {
  background: var(--warning-soft);
  color: var(--warning);
}

.mark.failed {
  background: var(--danger-soft);
  color: var(--danger);
}

.body {
  flex: 1;
  min-width: 0;
}

.when {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.note {
  margin-top: 2px;
  color: var(--text-2);
  font-size: var(--text-sm);
}

.badge-danger {
  background: var(--danger-soft);
  color: var(--danger);
}

.mail-link {
  width: 100%;
}
</style>
