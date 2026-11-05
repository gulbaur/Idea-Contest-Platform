<script setup>
// Приглашение нового сотрудника или управление существующим (D-062).
// Права проверяет сервер; здесь — понятные подсказки, почему действие недоступно.
import { computed, reactive, ref } from 'vue'

import { api } from '../lib/api.js'
import { confirmAction } from '../lib/confirm.js'
import { ROLE_LABELS } from '../lib/format.js'
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
const ROLE_HINTS = {
  employee: 'участвует в конкурсах',
  organizer: 'создаёт и ведёт конкурсы',
  admin: 'управляет сотрудниками и доступом',
}

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
const title = computed(() => (link.value ? 'Ссылка для входа' : isNew.value ? 'Пригласить сотрудника' : current.value.display_name))

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
        title: 'Сменить роль?',
        message: `${current.value.display_name}: ${ROLE_LABELS[current.value.role]} → ${ROLE_LABELS[changes.role]}. Все вкладки сотрудника выйдут — войти нужно будет заново.`,
        confirmText: 'Сменить роль',
      })
      if (!ok) return
    }
    current.value = await api.updateStaff(current.value.id, changes)
    notify.success('Изменения сохранены')
    emit('changed')
    emit('close')
  })
}

function issueLink() {
  return run(async () => {
    const hadPassword = current.value.status === 'active'
    const ok = await confirmAction({
      title: hadPassword ? 'Сбросить пароль?' : 'Выдать новую ссылку?',
      message: hadPassword
        ? 'Текущий пароль перестанет действовать, все вкладки сотрудника выйдут. Новый пароль сотрудник задаст сам по ссылке.'
        : 'Прежняя ссылка перестанет действовать.',
      confirmText: hadPassword ? 'Сбросить пароль' : 'Выдать ссылку',
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
        title: 'Отключить доступ?',
        message: `${current.value.display_name} не сможет войти, открытые вкладки выйдут сразу, письма приходить перестанут. Идеи, голоса и история сохранятся; доступ можно включить снова.`,
        confirmText: 'Отключить доступ',
        danger: true,
      })
      if (!ok) return
      current.value = await api.disableStaff(current.value.id)
      notify.info(`Доступ отключён: ${current.value.display_name}`)
    } else {
      current.value = await api.enableStaff(current.value.id)
      notify.success(`Доступ включён: ${current.value.display_name}`)
    }
    emit('changed')
  })
}
</script>

<template>
  <ModalDialog :title="title" wide @close="emit('close')">
    <SetupLinkBox v-if="link" :name="link.name" :setup="link.setup" />
    <div v-if="link" class="actions">
      <button class="btn btn-primary" type="button" @click="emit('close')">Готово</button>
    </div>

    <form v-else class="stack" novalidate @submit.prevent="submit">
      <p v-if="isNew" class="muted">
        Открытой регистрации нет: учётную запись создаёт администратор. Сотрудник получит одноразовую ссылку и сам задаст
        пароль — администратор его не знает.
      </p>

      <div class="grid">
        <div class="field">
          <label for="staff-name">Имя и фамилия</label>
          <input id="staff-name" v-model="form.display_name" class="input" maxlength="128" autocomplete="off" />
        </div>
        <div class="field">
          <label for="staff-login">Логин</label>
          <input
            id="staff-login"
            v-model="form.login"
            class="input mono"
            maxlength="64"
            autocomplete="off"
            :disabled="!isNew"
          />
          <span class="hint">{{ isNew ? 'латиница, цифры, точка, дефис' : 'логин не меняется' }}</span>
        </div>
        <div class="field span">
          <label for="staff-email">Рабочая почта</label>
          <input id="staff-email" v-model="form.email" class="input" type="email" maxlength="254" autocomplete="off" />
        </div>
        <div class="field span">
          <label for="staff-role">Роль</label>
          <select id="staff-role" v-model="form.role" class="select" :disabled="!isNew && roleLocked">
            <option v-for="role in ROLES" :key="role" :value="role">{{ ROLE_LABELS[role] }} — {{ ROLE_HINTS[role] }}</option>
          </select>
          <span v-if="!isNew && isSelf" class="hint">Свою роль изменить нельзя — попросите другого администратора.</span>
          <span v-else-if="!isNew && roleLocked" class="hint">
            Роль можно сменить после завершения конкурсов, где сотрудник участвует:
            {{ current.active_contests.map((topic) => `«${topic}»`).join(', ') }}.
          </span>
        </div>
      </div>

      <div v-if="error" class="notice notice-danger" role="alert"><Icon name="alert" class="icon" /> {{ error }}</div>

      <div class="actions">
        <button class="btn" type="button" @click="emit('close')">Отмена</button>
        <button class="btn btn-primary" type="submit" :disabled="pending">
          <span v-if="pending" class="spinner" aria-hidden="true" />
          {{ isNew ? 'Пригласить' : 'Сохранить' }}
        </button>
      </div>

      <section v-if="!isNew" class="access">
        <h3 class="overline">Доступ</h3>
        <div class="access-row">
          <div>
            <strong>Ссылка для входа</strong>
            <p class="faint">
              {{ current.status === 'active' ? 'Сбросить пароль: сотрудник задаст новый по ссылке.' : 'Выдать новую ссылку взамен прежней.' }}
            </p>
          </div>
          <button class="btn btn-sm" type="button" :disabled="pending || current.status === 'disabled'" @click="issueLink">
            {{ current.status === 'active' ? 'Сбросить пароль' : 'Новая ссылка' }}
          </button>
        </div>
        <div class="access-row">
          <div>
            <strong>{{ current.status === 'disabled' ? 'Доступ отключён' : 'Доступ к сервису' }}</strong>
            <p class="faint">
              {{
                current.status === 'disabled'
                  ? 'Сотрудник не может войти и не получает писем.'
                  : 'Отключение сразу закрывает все вкладки сотрудника; история сохраняется.'
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
            {{ current.status === 'disabled' ? 'Включить доступ' : 'Отключить доступ' }}
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
