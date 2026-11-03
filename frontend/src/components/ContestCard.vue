<script setup>
// Карточка конкурса в списке. Фаза пересчитывается по часам сервера каждую секунду,
// поэтому значок меняется в момент срока без перезагрузки страницы.
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { phaseAt } from '../lib/clock.js'
import { formatCountdown, formatDateTime } from '../lib/format.js'
import Icon from './Icon.vue'
import PhaseBadge from './PhaseBadge.vue'

const props = defineProps({
  contest: { type: Object, required: true },
  now: { type: Number, required: true },
})

const phase = computed(() => phaseAt(props.contest, props.now))
const nextStep = computed(() => {
  if (phase.value === 'submission') {
    return { text: 'до конца приёма идей', left: Date.parse(props.contest.submission_deadline) - props.now }
  }
  if (phase.value === 'voting') {
    return { text: 'до конца голосования', left: Date.parse(props.contest.voting_deadline) - props.now }
  }
  return null
})
</script>

<template>
  <RouterLink :to="{ name: 'contest', params: { id: contest.id } }" class="contest-card" :class="phase">
    <div class="row top">
      <PhaseBadge :phase="phase" />
      <span class="spacer" />
      <span v-if="nextStep" class="left">
        <Icon name="clock" :size="14" /> {{ formatCountdown(nextStep.left) }}
        <span class="faint">{{ nextStep.text }}</span>
      </span>
      <span v-else class="left faint"><Icon name="trophy" :size="14" /> итоги подведены</span>
    </div>
    <h3 class="topic">{{ contest.topic }}</h3>
    <dl class="dates">
      <div>
        <dt>Приём идей до</dt>
        <dd>{{ formatDateTime(contest.submission_deadline, now) }}</dd>
      </div>
      <div>
        <dt>Голосование до</dt>
        <dd>{{ formatDateTime(contest.voting_deadline, now) }}</dd>
      </div>
    </dl>
  </RouterLink>
</template>

<style scoped>
.contest-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--border);
  border-top: 4px solid var(--phase-submission);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  color: var(--text);
  transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
}

.contest-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow);
  text-decoration: none;
}

.contest-card.voting {
  border-top-color: var(--phase-voting);
}

.contest-card.finished {
  border-top-color: var(--phase-finished);
}

.top {
  flex-wrap: nowrap;
}

.left {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.85rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.left .faint {
  font-weight: 500;
}

.topic {
  font-size: 1.08rem;
  overflow-wrap: anywhere;
}

.dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 0;
}

dt {
  color: var(--text-3);
  font-size: 0.78rem;
}

dd {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 600;
}

@media (max-width: 420px) {
  .left .faint {
    display: none;
  }
}
</style>
