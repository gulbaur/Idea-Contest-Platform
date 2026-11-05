<script setup>
// Три этапа конкурса со сроками и обратным отсчётом до конца текущего.
// Отсчёт идёт по часам сервера (lib/clock.js), а не по часам компьютера.
import { computed } from 'vue'

import { phaseAt } from '../lib/clock.js'
import { formatCountdown, formatDateTime } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import Icon from './Icon.vue'

const props = defineProps({
  contest: { type: Object, required: true },
  now: { type: Number, required: true },
})

const ORDER = ['submission', 'voting', 'finished']

const steps = computed(() => {
  const current = phaseAt(props.contest, props.now)
  const currentIndex = ORDER.indexOf(current)
  const submissionEnd = Date.parse(props.contest.submission_deadline)
  const votingEnd = Date.parse(props.contest.voting_deadline)
  return [
    {
      key: 'submission',
      title: t('contest.timeline.submission'),
      icon: 'bulb',
      when: t('contest.timeline.until', { date: formatDateTime(props.contest.submission_deadline, props.now) }),
      left: submissionEnd - props.now,
    },
    {
      key: 'voting',
      title: t('contest.timeline.voting'),
      icon: 'vote',
      when: t('contest.timeline.until', { date: formatDateTime(props.contest.voting_deadline, props.now) }),
      left: votingEnd - props.now,
    },
    {
      key: 'finished',
      title: t('contest.timeline.finished'),
      icon: 'trophy',
      when: formatDateTime(props.contest.voting_deadline, props.now),
      left: null,
    },
  ].map((step, index) => ({
    ...step,
    state: index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'upcoming',
  }))
})
</script>

<template>
  <ol class="timeline" :aria-label="t('contest.timeline.label')">
    <li v-for="step in steps" :key="step.key" class="step" :class="[step.state, step.key]">
      <span class="mark" aria-hidden="true">
        <Icon :name="step.state === 'done' ? 'check' : step.icon" :size="18" />
      </span>
      <div class="body">
        <div class="title">
          {{ step.title }}
          <span v-if="step.state === 'current' && step.key !== 'finished'" class="now">{{ t('contest.timeline.now') }}</span>
        </div>
        <div class="when">{{ step.when }}</div>
        <div v-if="step.state === 'current' && step.left !== null" class="left" aria-live="off">
          <Icon name="clock" :size="14" /> {{ t('contest.timeline.left') }} <strong>{{ formatCountdown(step.left) }}</strong>
        </div>
      </div>
    </li>
  </ol>
</template>

<style scoped>
.timeline {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.step {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.mark {
  display: grid;
  place-items: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-3);
}

.title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.when {
  color: var(--text-2);
  font-size: var(--text-sm);
}

.left {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.now {
  padding: 1px 8px;
  border-radius: 999px;
  background: currentColor;
  font-size: var(--text-xs);
  font-weight: 600;
}

.step.done {
  background: var(--surface-2);
}

.step.done .mark {
  background: var(--success-soft);
  color: var(--success);
}

.step.done .when {
  color: var(--text-3);
}

.step.current.submission {
  border-color: var(--phase-submission);
  box-shadow: 0 0 0 3px var(--phase-submission-soft);
}

.step.current.submission .mark,
.step.current.submission .title {
  color: var(--phase-submission);
}

.step.current.submission .mark {
  background: var(--phase-submission-soft);
}

.step.current.voting {
  border-color: var(--phase-voting);
  box-shadow: 0 0 0 3px var(--phase-voting-soft);
}

.step.current.voting .mark,
.step.current.voting .title {
  color: var(--phase-voting);
}

.step.current.voting .mark {
  background: var(--phase-voting-soft);
}

.step.current.finished {
  border-color: var(--phase-finished);
  box-shadow: 0 0 0 3px var(--phase-finished-soft);
}

.step.current.finished .mark {
  background: var(--phase-finished-soft);
  color: var(--phase-finished);
}

.now {
  color: inherit;
  background: transparent;
  border: 1px solid currentColor;
}

@media (max-width: 720px) {
  .timeline {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
