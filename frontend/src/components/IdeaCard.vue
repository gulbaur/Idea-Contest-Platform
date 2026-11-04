<script setup>
// Карточка идеи для участника. Какие кнопки показать, решает страница по фазе и роли;
// сервер всё равно проверяет каждое действие (D-050).
import { computed } from 'vue'

import { formatDateTime } from '../lib/format.js'
import Icon from './Icon.vue'

const props = defineProps({
  idea: { type: Object, required: true },
  canEdit: { type: Boolean, default: false },
  canDelete: { type: Boolean, default: false },
  canVote: { type: Boolean, default: false },
  pending: { type: String, default: null }, // 'vote' | 'delete' | null
})
const emit = defineEmits(['edit', 'delete', 'vote', 'revoke'])

// У чужих идей время правки сервер не отдаёт (null), поэтому «изменена» — только у своих.
const edited = computed(() => Boolean(props.idea.updated_at) && props.idea.updated_at !== props.idea.submitted_at)
</script>

<template>
  <article class="idea" :class="{ mine: idea.is_mine, voted: idea.voted_by_me }" :data-idea-id="idea.id">
    <div class="top">
      <h3 class="title">{{ idea.title }}</h3>
      <div class="badges">
        <span v-if="idea.is_mine" class="badge badge-primary"><Icon name="user" :size="13" /> Ваша идея</span>
        <span v-if="idea.voted_by_me && !canVote" class="badge badge-success">
          <Icon name="check" :size="13" /> Ваш голос
        </span>
      </div>
    </div>

    <p class="description">{{ idea.description }}</p>

    <div class="footer">
      <span class="faint">
        Подана {{ formatDateTime(idea.submitted_at) }}<template v-if="edited"> · изменена</template>
      </span>
      <!-- Кнопки — одной группой: на узком экране переносятся вместе и остаются справа. -->
      <div class="actions">
      <template v-if="canVote">
        <template v-if="idea.voted_by_me">
          <span class="badge badge-success voted-mark"><Icon name="check" :size="13" /> Вы проголосовали</span>
          <button
            class="btn btn-ghost btn-sm revoke-button"
            type="button"
            :disabled="pending === 'vote'"
            @click="emit('revoke', idea)"
          >
            <span v-if="pending === 'vote'" class="spinner" aria-hidden="true" />
            Отозвать
          </button>
        </template>
        <button
          v-else
          class="btn btn-soft btn-sm vote-button"
          type="button"
          :disabled="pending === 'vote'"
          @click="emit('vote', idea)"
        >
          <span v-if="pending === 'vote'" class="spinner" aria-hidden="true" />
          <Icon v-else name="vote" />
          Голосовать
        </button>
      </template>

      <button v-if="canEdit" class="btn btn-ghost btn-sm" type="button" :disabled="!!pending" @click="emit('edit', idea)">
        <Icon name="edit" /> Изменить
      </button>
      <button
        v-if="canDelete"
        class="btn btn-ghost-danger btn-sm"
        type="button"
        :disabled="!!pending"
        @click="emit('delete', idea)"
      >
        <span v-if="pending === 'delete'" class="spinner" aria-hidden="true" />
        <Icon v-else name="trash" />
        Удалить
      </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.idea {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.idea.voted {
  border-color: var(--success);
  box-shadow: 0 0 0 3px var(--success-soft);
}

/* Своя идея — полоса слева (фон, обрезанный по скруглению карточки). */
.idea.mine {
  background:
    linear-gradient(var(--primary), var(--primary)) left / 4px 100% no-repeat,
    var(--surface);
}

.top {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.title {
  font-size: 1.05rem;
  overflow-wrap: anywhere;
}

.badges {
  display: flex;
  gap: 6px;
}

.description {
  color: var(--text-2);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
}

.voted-mark {
  padding: 6px 10px;
}
</style>
