<script setup>
// Приглашение нового сотрудника или управление существующим (D-062).
// Права проверяет сервер; здесь — понятные подсказки, почему действие недоступно.
import { computed, reactive, ref } from 'vue'

import { api } from '../lib/api.js'
import { confirmAction } from '../lib/confirm.js'
import { ROLE_LABELS } from '../lib/format.js'
import { t } from '../lib/i18n.js'
import { notify } from '../lib/notify.js'
import { session } from '../lib/session.js'
import Icon from './Icon.vue'
import ModalDialog from './ModalDialog.vue'
import SetupLinkBox from './SetupLinkBox.vue'

const props = defineProps({
  // null — приглашение нового; объект — управление существующим.
  person: { type: Object, default: null },
})
const emit = defineEmits(['close', 'changed'])

const ROLES = ['employee', 'organizer', 'admin']
// Подсказки — computed: пересчитываются при смене языка (D-065).
const ROLE_HINTS = computed(() => Object.fromEntries(ROLES.map((role) => [role, t(`staff.dialog.roleHint.${role}`)])))

const current = ref(props.person)
const form = reactive({
  display_name: props.person?.display_name ?? '',
  login: props.person?.login ?? '',
  email: props.person?.email ?? '',
  role: props.person?.role ?? 'employee',
})
const pending = ref(false)
const error = ref('')
const link = ref(null) // { name, setup } — показать ссылку вместо формы

const isNew = computed(() => !current.value)
const isSelf = computed(() => current.value?.id === session.user?.id)
const roleLocked = computed(() => isSelf.value || Boolean(current.value?.active_contests?.length))
const title = computed(() => (
  link.value ? t('staff.dialog.linkTitle') : isNew.value ? t('staff.dialog.inviteTitle') : current.value.display_name
))

async function run(action) {
  if (pending.value) return
  pending.value = true
  error.value = ''
  try {
    await action()
  } catch (failure) {
    error.value = failure.message
  } finally {
    pending.value = false
  }
}

function submit() {
  return run(async () => {
    if (isNew.value) {
      const created = await api.inviteStaff({ ...form })
      current.value = created.user
      link.value = { name: created.user.display_name, setup: created.setup }
      emit('changed')
      return
    }
    const changes = {}
    for (const field of ['display_name', 'email', 'role']) {
      if (form[field] !== current.value[field]) changes[field] = form[field]
    }
    if (!Object.keys(changes).length) return emit('close')
    if (changes.role) {
      const ok = await confirmAction({
        title: t('staff.dialog.roleConfirmTitle'),
        message: t('staff.dialog.roleConfirmMessage', {
          name: current.value.display_name,
          from: ROLE_LABELS[current.value.role],
          to: ROLE_LABELS[changes.role],
        }),
        confirmText: t('staff.dialog.roleConfirm'),
      })
      if (!ok) return
    }
    current.value = await api.updateStaff(current.value.id, changes)
    notify.success(t('staff.dialog.saved'))
    emit('changed')
    emit('close')
  })
}

function issueLink() {
  return run(async () => {
    const hadPassword = current.value.status === 'active'
    const ok = await confirmAction({
      title: hadPassword ? t('staff.dialog.resetTitle') : t('staff.dialog.reissueTitle'),
      message: hadPassword ? t('staff.dialog.resetMessage') : t('staff.dialog.reissueMessage'),
      confirmText: hadPassword ? t('staff.dialog.resetConfirm') : t('staff.dialog.reissueConfirm'),
      danger: hadPassword,
    })
    if (!ok) return
    const result = await api.issueSetupLink(current.value.id)
    current.value = result.user
    link.value = { name: result.user.display_name, setup: result.setup }
    emit('changed')
  })
}

function toggleAccess() {
  return run(async () => {
    if (current.value.status !== 'disabled') {
      const ok = await confirmAction({
        title: t('staff.dialog.disableTitle'),
        message: t('staff.dialog.disableMessage', { name: current.value.display_name }),
        confirmText: t('staff.dialog.disable'),
        danger: true,
      })
      if (!ok) return
      current.value = await api.disableStaff(current.value.id)
      notify.info(t('staff.dialog.disabledToast', { name: current.value.display_name }))
    } else {
      current.value = await api.enableStaff(current.value.id)
      notify.success(t('staff.dialog.enabledToast', { name: current.value.display_name }))
    }
    emit('changed')
  })
}
</script>

<template>
  <ModalDialog :title="title" wide @close="emit('close')">
    <SetupLinkBox v-if="link" :name="link.name" :setup="link.setup" />
    <div v-if="link" class="actions">
      <button class="btn btn-primary" type="button" @click="emit('close')">{{ t('staff.dialog.done') }}</button>
    </div>

    <form v-else class="stack" novalidate @submit.prevent="submit">
      <p v-if="isNew" class="muted">{{ t('staff.dialog.intro') }}</p>

      <div class="grid">
        <div class="field">
          <label for="staff-name">{{ t('staff.dialog.name') }}</label>
          <input id="staff-name" v-model="form.display_name" class="input" maxlength="128" autocomplete="off" />
        </div>
        <div class="field">
          <label for="staff-login">{{ t('staff.dialog.login') }}</label>
          <input
            id="staff-login"
            v-model="form.login"
            class="input mono"
            maxlength="64"
            autocomplete="off"
            :disabled="!isNew"
          />
          <span class="hint">{{ isNew ? t('staff.dialog.loginHintNew') : t('staff.dialog.loginHintFixed') }}</span>
        </div>
        <div class="field span">
          <label for="staff-email">{{ t('staff.dialog.email') }}</label>
          <input id="staff-email" v-model="form.email" class="input" type="email" maxlength="254" autocomplete="off" />
        </div>
        <div class="field span">
          <label for="staff-role">{{ t('staff.dialog.role') }}</label>
          <select id="staff-role" v-model="form.role" class="select" :disabled="!isNew && roleLocked">
            <option v-for="role in ROLES" :key="role" :value="role">{{ ROLE_LABELS[role] }} — {{ ROLE_HINTS[role] }}</option>
          </select>
          <span v-if="!isNew && isSelf" class="hint">{{ t('staff.dialog.roleSelf') }}</span>
          <span v-else-if="!isNew && roleLocked" class="hint">
            {{ t('staff.dialog.roleLocked') }}
            {{ current.active_contests.map((topic) => t('staff.dialog.quotedTopic', { topic })).join(', ') }}.
          </span>
        </div>
      </div>

      <div v-if="error" class="notice notice-danger" role="alert"><Icon name="alert" class="icon" /> {{ error }}</div>

      <div class="actions">
        <button class="btn" type="button" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn btn-primary" type="submit" :disabled="pending">
          <span v-if="pending" class="spinner" aria-hidden="true" />
          {{ isNew ? t('staff.dialog.submitInvite') : t('common.save') }}
        </button>
      </div>

      <section v-if="!isNew" class="access">
        <h3 class="overline">{{ t('staff.dialog.access') }}</h3>
        <div class="access-row">
          <div>
            <strong>{{ t('staff.dialog.linkHeading') }}</strong>
            <p class="faint">
              {{ current.status === 'active' ? t('staff.dialog.linkResetText') : t('staff.dialog.linkReissueText') }}
            </p>
          </div>
          <button class="btn btn-sm" type="button" :disabled="pending || current.status === 'disabled'" @click="issueLink">
            {{ current.status === 'active' ? t('staff.dialog.resetButton') : t('staff.dialog.reissueButton') }}
          </button>
        </div>
        <div class="access-row">
          <div>
            <strong>{{ current.status === 'disabled' ? t('staff.dialog.accessDisabled') : t('staff.dialog.accessHeading') }}</strong>
            <p class="faint">
              {{
                current.status === 'disabled'
                  ? t('staff.dialog.accessDisabledText')
                  : t('staff.dialog.accessActiveText')
              }}
            </p>
          </div>
          <button
            class="btn btn-sm"
            :class="current.status === 'disabled' ? '' : 'btn-ghost-danger'"
            type="button"
            :disabled="pending || isSelf"
            @click="toggleAccess"
          >
            {{ current.status === 'disabled' ? t('staff.dialog.enable') : t('staff.dialog.disable') }}
          </button>
        </div>
      </section>
    </form>
  </ModalDialog>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.span {
  grid-column: 1 / -1;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}

.access {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.access-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.access-row strong {
  font-weight: 500;
}

.access-row .btn {
  flex: none;
}

@media (max-width: 520px) {
  .grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .access-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
