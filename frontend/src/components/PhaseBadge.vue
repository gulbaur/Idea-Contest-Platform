<script setup>
import { PHASE_LABELS } from '../lib/format.js'

defineProps({ phase: { type: String, required: true } })
</script>

<template>
  <span class="phase-badge" :class="phase">
    <span class="dot" aria-hidden="true" />
    {{ PHASE_LABELS[phase] }}
  </span>
</template>

<style scoped>
.phase-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 11px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  white-space: nowrap;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.submission {
  background: var(--phase-submission-soft);
  color: var(--phase-submission);
}

.voting {
  background: var(--phase-voting-soft);
  color: var(--phase-voting);
}

.voting .dot {
  animation: blink 1.6s ease-in-out infinite;
}

.finished {
  background: var(--phase-finished-soft);
  color: var(--phase-finished);
}

@keyframes blink {
  50% {
    opacity: 0.35;
  }
}
</style>
