<script setup>
// Результаты: идеи в порядке, который вернул сервер (голоса → раньше подана → меньший номер,
// D-008). Сервер же решает, видны ли счёт и авторы; компонент только показывает.
import { computed } from 'vue'

import { formatDateTime, formatPrecise } from '../lib/format.js'
import { t, tn } from '../lib/i18n.js'
import Icon from './Icon.vue'

const props = defineProps({
  ideas: { type: Array, required: true },
  winnerId: { type: Number, default: null },
  final: { type: Boolean, default: false }, // итоги (true) или текущие результаты (false)
})

const maxVotes = computed(() => Math.max(1, ...props.ideas.map((idea) => idea.votes_count ?? 0)))

// Ничья за первое место: показать, почему победила (лидирует) более ранняя идея.
const tie = computed(() => {
  const [first, second] = props.ideas
  if (!first || !second || first.votes_count !== second.votes_count) return null
  const tied = props.ideas.filter((idea) => idea.votes_count === first.votes_count)
  return { leader: first, others: tied.slice(1), votes: first.votes_count }
})

</script>

<template>
  <div class="results">
    <div v-if="tie" class="notice notice-warning tie" data-test="tie-note">
      <Icon name="info" class="icon" />
      <span v-if="tie.votes === 0 && final">
        {{ t('contest.results.noVotes', { title: tie.leader.title, time: formatPrecise(tie.leader.submitted_at) }) }}
      </span>
      <span v-else>
        {{ t('contest.results.tie', { count: tie.others.length + 1, votes: tn('common.votes', tie.votes) }) }}
        {{ t(final ? 'contest.results.tieWon' : 'contest.results.tieLeads', { title: tie.leader.title }) }}
        ({{ formatPrecise(tie.leader.submitted_at) }}<template v-for="other in tie.others" :key="other.id">{{
          t('contest.results.tieOther', { title: other.title, time: formatPrecise(other.submitted_at) })
        }}</template
        >).
      </span>
    </div>

    <ol class="list">
      <li
        v-for="(idea, index) in ideas"
        :key="idea.id"
        class="item"
        :class="{ winner: final && idea.id === winnerId, leader: !final && index === 0 }"
        :data-idea-id="idea.id"
      >
        <span class="place" :class="`place-${index + 1}`">
          <Icon v-if="final && idea.id === winnerId" name="trophy" :size="18" />
          <template v-else>{{ index + 1 }}</template>
        </span>

        <div class="main">
          <div class="head">
            <h3 class="title">{{ idea.title }}</h3>
            <span v-if="final && idea.id === winnerId" class="badge badge-gold">{{ t('contest.results.winner') }}</span>
            <span v-if="idea.is_mine" class="badge badge-primary">{{ t('contest.idea.yours') }}</span>
            <span v-if="idea.voted_by_me" class="badge badge-success"><Icon name="check" :size="13" /> {{ t('contest.idea.yourVote') }}</span>
          </div>
          <p class="description">{{ idea.description }}</p>
          <div class="meta">
            <span v-if="idea.author" class="author" data-test="author">
              <Icon name="user" :size="14" /> {{ idea.author.display_name }}
            </span>
            <span v-else class="faint"><Icon name="eye-off" :size="14" /> {{ t('contest.results.authorHidden') }}</span>
            <span class="faint">{{ t('contest.results.submittedAt', { date: formatDateTime(idea.submitted_at) }) }}</span>
          </div>
        </div>

        <div class="score">
          <div class="votes" data-test="votes">{{ idea.votes_count }}</div>
          <div class="faint">{{ tn('contest.results.votesWord', idea.votes_count) }}</div>
          <div class="bar" aria-hidden="true">
            <span :style="{ width: `${Math.round((idea.votes_count / maxVotes) * 100)}%` }" />
          </div>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.results {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) 120px;
  gap: 16px;
  align-items: center;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.item.winner {
  border-color: var(--gold);
  background: var(--gold-soft);
}

.item.leader {
  border-color: var(--phase-voting);
}

.place {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--surface-2);
  color: var(--text-2);
  font-weight: 600;
}

.winner .place {
  background: var(--gold);
  color: #1f1500;
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.title {
  overflow-wrap: anywhere;
}

.description {
  margin-top: 4px;
  color: var(--text-2);
  font-size: var(--text-md);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
}

.author {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
  font-size: var(--text-md);
}

.meta .faint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.score {
  text-align: right;
}

.votes {
  font-size: var(--text-2xl);
  font-weight: 600;
  line-height: 1;
  font-variant-numeric: tabular-nums;
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
  background: var(--phase-voting);
  transition: width 0.4s ease;
}

.winner .bar span {
  background: var(--gold);
}

@media (max-width: 640px) {
  .item {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .score {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: 10px;
    text-align: left;
  }

  .score .bar {
    flex: 1;
    margin-top: 0;
  }
}
</style>
