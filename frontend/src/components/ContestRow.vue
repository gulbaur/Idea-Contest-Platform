<script setup>
// Строка списка конкурсов (D-061): тема, этап со шкалой времени, ближайший срок, участие.
// Фаза пересчитывается по часам сервера каждую секунду — значок меняется в момент срока.
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { participation, timeline } from '../lib/contestList.js'
import { formatCountdown, formatDateTime } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import Icon from './Icon.vue'
import PhaseBadge from './PhaseBadge.vue'

const props = defineProps({
  contest: { type: Object, required: true },
  phase: { type: String, required: true },
  now: { type: Number, required: true },
  organizer: { type: Boolean, default: false },
})

const deadline = computed(() => {
  if (props.phase === 'submission') {
    return { label: t('contests.row.submissionUntil'), at: props.contest.submission_deadline }
  }
  if (props.phase === 'voting') return { label: t('contests.row.votingUntil'), at: props.contest.voting_deadline }
  return { label: t('contests.row.results'), at: props.contest.voting_deadline }
})
const left = computed(() => (props.phase === 'finished' ? null : Date.parse(deadline.value.at) - props.now))
const bar = computed(() => timeline(props.contest, props.now))
const state = computed(() => participation(props.contest, props.phase, props.organizer))
</script>

<template>
  <RouterLink :to="{ name: 'contest', params: { id: contest.id } }" class="contest-row" :class="phase">
    <span class="topic-cell">
      <h3 class="topic">{{ contest.topic }}</h3>
      <span class="faint">{{ t('contests.row.meta', { id: contest.id, date: formatDateTime(contest.created_at, now) }) }}</span>
    </span>

    <span class="phase-cell">
      <PhaseBadge :phase="phase" />
      <span class="bar" aria-hidden="true">
        <span class="part submission" :style="{ width: `${bar.split * 100}%` }" />
        <span class="part voting" :style="{ width: `${(1 - bar.split) * 100}%` }" />
        <span class="fill" :style="{ width: `${bar.progress * 100}%` }" />
      </span>
    </span>

    <span class="deadline-cell">
      <span class="faint">{{ deadline.label }}</span>
      <span class="when">{{ formatDateTime(deadline.at, now) }}</span>
      <span v-if="left !== null" class="left tabular"><Icon name="clock" :size="13" /> {{ t('contests.row.left', { time: formatCountdown(left) }) }}</span>
    </span>

    <span class="state-cell">
      <span class="state" :class="state.tone">
        <Icon v-if="state.tone === 'action'" name="alert" :size="14" />
        <Icon v-else-if="state.tone === 'done'" name="check" :size="14" />
        {{ state.text }}
      </span>
      <span v-if="state.detail" class="faint">{{ state.detail }}</span>
    </span>

    <Icon name="chevron-right" class="go" :size="18" />
  </RouterLink>
</template>

<style scoped>
.contest-row {
  display: grid;
  grid-template-columns: var(--contest-columns);
  align-items: center;
  gap: 20px;
  padding: 14px 16px 14px 20px;
  border-top: 1px solid var(--border);
  color: var(--text);
  position: relative;
}

/* Цвет фазы — полоска у левого края строки. */
.contest-row::before {
  content: '';
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: 0;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--phase-submission);
}

.contest-row.voting::before {
  background: var(--phase-voting);
}

.contest-row.finished::before {
  background: var(--border-strong);
}

.contest-row:hover {
  background: var(--surface-hover);
  text-decoration: none;
}

.topic-cell,
.deadline-cell,
.state-cell,
.phase-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.topic {
  font-size: var(--text-md);
  font-weight: 600;
  overflow-wrap: anywhere;
}

.phase-cell {
  align-items: flex-start;
  gap: 8px;
}

.bar {
  position: relative;
  display: flex;
  width: 100%;
  max-width: 140px;
  height: 4px;
  overflow: hidden;
  border-radius: 2px;
  background: var(--surface-hover);
}

.part {
  height: 100%;
  opacity: 0.25;
}

.part.submission {
  background: var(--phase-submission);
}

.part.voting {
  background: var(--phase-voting);
}

.fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: var(--text-3);
  opacity: 0.55;
}

.when {
  font-weight: 500;
}

.left {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-2);
  font-size: var(--text-sm);
}

.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.state.action {
  color: var(--warning);
}

.state.done {
  color: var(--success);
}

.state.muted {
  color: var(--text-2);
}

.go {
  color: var(--text-3);
}

/* Узкий экран: строка складывается в компактный блок — тема, этап и срок, участие. */
@media (max-width: 760px) {
  .contest-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 10px 12px;
    padding: 14px 12px 14px 16px;
  }

  .topic-cell,
  .phase-cell,
  .deadline-cell,
  .state-cell {
    grid-column: 1;
  }

  .phase-cell {
    flex-direction: row;
    align-items: center;
  }

  .deadline-cell {
    flex-flow: row wrap;
    column-gap: 8px;
  }

  .go {
    grid-row: 1;
    grid-column: 2;
  }
}
</style>
