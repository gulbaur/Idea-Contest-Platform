<script setup>
// Одно письмо целиком: вид, тема, кому, когда, конкурс, текст.
import { RouterLink } from 'vue-router'

import { formatDateTime } from '../lib/format.js'
import { kindOf } from '../lib/mail.js'

defineProps({
  letter: { type: Object, required: true },
  now: { type: Number, required: true },
})
</script>

<template>
  <div class="letter-view">
    <span class="badge" :class="kindOf(letter.kind).tone">{{ kindOf(letter.kind).label }}</span>
    <h2 class="subject-big">{{ letter.subject }}</h2>
    <dl class="headers">
      <div>
        <dt>Кому</dt>
        <dd>{{ letter.recipient.display_name }} &lt;{{ letter.to_address }}&gt;</dd>
      </div>
      <div>
        <dt>Когда</dt>
        <dd>{{ formatDateTime(letter.created_at, now) }}</dd>
      </div>
      <div>
        <dt>Конкурс</dt>
        <dd>
          <RouterLink :to="{ name: 'contest', params: { id: letter.contest_id } }">{{ letter.contest_topic }}</RouterLink>
        </dd>
      </div>
    </dl>
    <pre class="body">{{ letter.body }}</pre>
  </div>
</template>

<style scoped>
.subject-big {
  margin: 10px 0 14px;
  font-size: var(--text-xl);
  overflow-wrap: anywhere;
}

.headers {
  display: grid;
  gap: 6px;
  margin: 0 0 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border);
}

.headers div {
  display: grid;
  grid-template-columns: 80px minmax(0, 1fr);
  gap: 8px;
}

dt {
  color: var(--text-3);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.body {
  margin: 0;
  font-family: inherit;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.6;
}
</style>
