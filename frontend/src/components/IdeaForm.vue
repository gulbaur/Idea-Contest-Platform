<script setup>
// Форма идеи: подача новой или правка своей. Ограничения те же, что на сервере (D-032):
// название 1–200 символов, описание 1–5000, пробелы по краям не считаются.
import { computed, ref, watch } from 'vue'

import { t } from '../lib/i18n.js'
import Icon from './Icon.vue'

const TITLE_MAX = 200
const DESCRIPTION_MAX = 5000

const props = defineProps({
  initialTitle: { type: String, default: '' },
  initialDescription: { type: String, default: '' },
  submitLabel: { type: String, default: '' }, // пусто — «Отправить» на языке интерфейса
  pending: { type: Boolean, default: false },
  cancelable: { type: Boolean, default: false },
  idPrefix: { type: String, default: 'idea' },
})
const emit = defineEmits(['submit', 'cancel'])

const title = ref(props.initialTitle)
const description = ref(props.initialDescription)
const touched = ref(false)

// Родитель может подменить значения (например, при конфликте правки из другой вкладки).
watch(
  () => [props.initialTitle, props.initialDescription],
  ([newTitle, newDescription]) => {
    title.value = newTitle
    description.value = newDescription
  },
)

const titleError = computed(() => {
  const value = title.value.trim()
  if (!value) return t('contest.form.titleEmpty')
  if (value.length > TITLE_MAX) return t('contest.form.tooLong', { max: TITLE_MAX })
  return ''
})
const descriptionError = computed(() => {
  const value = description.value.trim()
  if (!value) return t('contest.form.descriptionEmpty')
  if (value.length > DESCRIPTION_MAX) return t('contest.form.tooLong', { max: DESCRIPTION_MAX })
  return ''
})

function submit() {
  touched.value = true
  if (titleError.value || descriptionError.value || props.pending) return
  emit('submit', { title: title.value.trim(), description: description.value.trim() })
}

function reset() {
  title.value = ''
  description.value = ''
  touched.value = false
}

defineExpose({ reset })
</script>

<template>
  <form class="idea-form stack" novalidate @submit.prevent="submit">
    <div class="field">
      <div class="row">
        <label :for="`${idPrefix}-title`">{{ t('contest.form.title') }}</label>
        <span class="counter" :class="{ over: title.trim().length > TITLE_MAX }">
          {{ title.trim().length }}/{{ TITLE_MAX }}
        </span>
      </div>
      <input
        :id="`${idPrefix}-title`"
        v-model="title"
        class="input"
        type="text"
        maxlength="400"
        :placeholder="t('contest.form.titlePlaceholder')"
        :aria-invalid="touched && !!titleError"
        :disabled="pending"
      />
      <span v-if="touched && titleError" class="field-error">{{ titleError }}</span>
    </div>

    <div class="field">
      <div class="row">
        <label :for="`${idPrefix}-description`">{{ t('contest.form.description') }}</label>
        <span class="counter" :class="{ over: description.trim().length > DESCRIPTION_MAX }">
          {{ description.trim().length }}/{{ DESCRIPTION_MAX }}
        </span>
      </div>
      <textarea
        :id="`${idPrefix}-description`"
        v-model="description"
        class="textarea"
        rows="4"
        :placeholder="t('contest.form.descriptionPlaceholder')"
        :aria-invalid="touched && !!descriptionError"
        :disabled="pending"
      />
      <span v-if="touched && descriptionError" class="field-error">{{ descriptionError }}</span>
    </div>

    <div class="row actions">
      <button class="btn btn-primary" type="submit" :disabled="pending">
        <span v-if="pending" class="spinner" aria-hidden="true" />
        <Icon v-else name="send" />
        {{ submitLabel || t('contest.form.submit') }}
      </button>
      <button v-if="cancelable" class="btn btn-ghost" type="button" :disabled="pending" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </button>
    </div>
  </form>
</template>

<style scoped>
.actions {
  justify-content: flex-start;
}
</style>
