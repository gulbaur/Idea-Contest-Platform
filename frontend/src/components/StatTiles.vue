<script setup>
// Статистика экрана организатора (F8): идеи, разные проголосовавшие люди, голоса.
import { computed } from 'vue'

import { plural } from '../lib/format.js'
import Icon from './Icon.vue'

const props = defineProps({ stats: { type: Object, required: true } })

const share = computed(() =>
  props.stats.participants_count ? Math.round((props.stats.voters_count / props.stats.participants_count) * 100) : 0,
)
</script>

<template>
  <div class="tiles">
    <div class="tile">
      <span class="mark"><Icon name="users" /></span>
      <div>
        <div class="value">{{ stats.participants_count }}</div>
        <div class="label">{{ plural(stats.participants_count, ['участник', 'участника', 'участников']) }}</div>
      </div>
    </div>
    <div class="tile">
      <span class="mark"><Icon name="bulb" /></span>
      <div>
        <div class="value" data-test="ideas-count">{{ stats.ideas_count }}</div>
        <div class="label">{{ plural(stats.ideas_count, ['идея подана', 'идеи подано', 'идей подано']) }}</div>
      </div>
    </div>
    <div class="tile wide">
      <span class="mark"><Icon name="vote" /></span>
      <div class="grow">
        <div class="value" data-test="voters-count">
          {{ stats.voters_count }} <span class="of">из {{ stats.participants_count }}</span>
        </div>
        <div class="label">
          <!-- «4 из 5 человек проголосовали»: существительное согласуется с общим числом, глагол — с числом проголосовавших. -->
          {{ plural(stats.participants_count, ['человека', 'человек', 'человек']) }}
          {{ plural(stats.voters_count, ['проголосовал', 'проголосовали', 'проголосовали']) }}
          · {{ stats.votes_count }} {{ plural(stats.votes_count, ['голос', 'голоса', 'голосов']) }}
        </div>
        <div class="bar" role="progressbar" :aria-valuenow="share" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${share}%` }" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tiles {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 2fr);
  gap: 12px;
}

.tile {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.mark {
  display: grid;
  place-items: center;
  flex: none;
  width: 42px;
  height: 42px;
  border-radius: var(--radius-lg);
  background: var(--primary-soft);
  color: var(--primary-text);
}

.value {
  font-size: var(--text-2xl);
  font-weight: 600;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.of {
  color: var(--text-3);
  font-size: var(--text-lg);
  font-weight: 600;
}

.label {
  color: var(--text-2);
  font-size: var(--text-sm);
}

.grow {
  flex: 1;
}

.bar {
  height: 6px;
  margin-top: 8px;
  border-radius: 999px;
  background: var(--surface-2);
  overflow: hidden;
}

.bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary);
  transition: width 0.4s ease;
}

@media (max-width: 860px) {
  .tiles {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .wide {
    grid-column: 1 / -1;
  }
}
</style>
