<script setup>
// Страница конкурса. Что показать, решает сервер: снимок содержит только то, что этому
// пользователю видно в текущей фазе (D-028). Страница выбирает раскладку по роли и фазе
// и отправляет действия; каждое действие проверяет сервер (D-050).
import { computed, reactive, ref, toRef, watch } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '../components/EmptyState.vue'
import Icon from '../components/Icon.vue'
import IdeaCard from '../components/IdeaCard.vue'
import IdeaForm from '../components/IdeaForm.vue'
import ParticipantsPanel from '../components/ParticipantsPanel.vue'
import PhaseBadge from '../components/PhaseBadge.vue'
import PhaseTimeline from '../components/PhaseTimeline.vue'
import ResultsList from '../components/ResultsList.vue'
import SchedulePanel from '../components/SchedulePanel.vue'
import StatTiles from '../components/StatTiles.vue'
import { useContest } from '../composables/useContest.js'
import { useServerNow } from '../composables/useServerNow.js'
import { api } from '../lib/api.js'
import { confirmAction } from '../lib/confirm.js'
import { formatDateTime } from '../lib/format.js'
import { t, tn } from '../lib/i18n.js'
import { notify } from '../lib/notify.js'
import { newRequestId } from '../lib/requestId.js'
import { isOrganizer } from '../lib/session.js'

const props = defineProps({ id: { type: String, required: true } })

const { snapshot, error, refreshFailed, reload } = useContest(toRef(props, 'id'))
const now = useServerNow()

const organizer = computed(isOrganizer)
const contest = computed(() => snapshot.value?.contest)
const phase = computed(() => contest.value?.phase)
const ideas = computed(() => snapshot.value?.ideas ?? [])
const myIdeas = computed(() => ideas.value.filter((idea) => idea.is_mine))
const othersIdeas = computed(() => ideas.value.filter((idea) => !idea.is_mine))
const myVotes = computed(() => ideas.value.filter((idea) => idea.voted_by_me).length)
const winner = computed(() => ideas.value.find((idea) => idea.id === snapshot.value?.winner_idea_id) ?? null)

watch(contest, (value) => {
  if (value) document.title = t('contest.documentTitle', { topic: value.topic })
})

// --- действия участника -------------------------------------------------------

const pendingIdea = reactive({}) // id идеи → 'vote' | 'delete': кнопки неактивны, пока ждём ответ
const submitPending = ref(false)
const ideaForm = ref(null)
// Идентификатор формы подачи: тот же при повторе после сбоя, новый — после успеха (D-050).
let submitRequestId = newRequestId()

// Правка: форма работает с версией идеи на момент нажатия «Изменить» (editBase), а не с живыми
// данными. Иначе обновление по сигналу подменило бы текст в открытой форме и версию для
// сохранения — и защита от перезаписи чужой правки (409) не сработала бы.
const editingId = ref(null)
const editBase = ref(null) // { version, title, description }
const editPending = ref(false)
const editConflict = ref(false) // сервер ответил 409: в форме уже актуальный текст
const editedElsewhere = computed(() => {
  const live = ideas.value.find((idea) => idea.id === editingId.value)
  return Boolean(live && editBase.value && live.version !== editBase.value.version && !editConflict.value)
})

function failed(failure) {
  notify.error(failure.message)
  reload() // отказ сервера — повод показать актуальное состояние (REVIEW Г1)
}

async function submitIdea(payload) {
  if (submitPending.value) return
  submitPending.value = true
  try {
    await api.submitIdea(contest.value.id, { ...payload, client_request_id: submitRequestId })
    submitRequestId = newRequestId()
    ideaForm.value?.reset()
    notify.success(t('contest.submission.submitted'))
    reload()
  } catch (failure) {
    if (failure.detail?.code === 'request_id_reused') {
      // Первая отправка формы уже принята (ответ потерялся), а текст с тех пор изменился.
      // Новый идентификатор: следующее нажатие подаст новый текст отдельной идеей (D-053).
      submitRequestId = newRequestId()
      notify.error(t('contest.submission.reused'))
      reload()
    } else {
      failed(failure)
    }
  } finally {
    submitPending.value = false
  }
}

function startEdit(idea) {
  editConflict.value = false
  editBase.value = { version: idea.version, title: idea.title, description: idea.description }
  editingId.value = idea.id
}

function cancelEdit() {
  editingId.value = null
  editBase.value = null
  editConflict.value = false
}

// Переход к другому конкурсу без пересоздания страницы: форма и её идентификатор — новые,
// иначе отправка в другой конкурс пришла бы с прежним client_request_id (D-053).
watch(
  () => props.id,
  () => {
    submitRequestId = newRequestId()
    ideaForm.value?.reset()
    cancelEdit()
  },
)

async function saveEdit(idea, payload) {
  if (editPending.value) return
  editPending.value = true
  try {
    await api.updateIdea(idea.id, { ...payload, version: editBase.value.version })
    cancelEdit()
    notify.success(t('contest.submission.saved'))
    reload()
  } catch (failure) {
    if (failure.status === 409 && failure.detail?.current) {
      // Идею изменили в другой вкладке: показываем актуальный текст, правку можно повторить.
      const current = failure.detail.current
      editBase.value = { version: current.version, title: current.title, description: current.description }
      editConflict.value = true
      reload()
    } else {
      failed(failure)
    }
  } finally {
    editPending.value = false
  }
}

async function deleteIdea(idea) {
  const duringVoting = phase.value === 'voting'
  const confirmed = await confirmAction({
    title: t('contest.remove.title'),
    message: duringVoting
      ? t('contest.remove.duringVoting', { title: idea.title })
      : t('contest.remove.beforeVoting', { title: idea.title }),
    confirmText: t('contest.remove.confirm'),
    danger: true,
  })
  if (!confirmed || pendingIdea[idea.id]) return
  pendingIdea[idea.id] = 'delete'
  try {
    await api.deleteIdea(idea.id)
    notify.success(t('contest.remove.done'))
  } catch (failure) {
    // 404 — идея уже удалена (например, во второй вкладке): цель достигнута (REVIEW Г3).
    if (failure.status === 404) notify.success(t('contest.remove.already'))
    else notify.error(failure.message)
  } finally {
    delete pendingIdea[idea.id]
    if (editingId.value === idea.id) cancelEdit()
    reload()
  }
}

async function castVote(idea, revoke = false) {
  if (pendingIdea[idea.id]) return // повторное нажатие, пока ждём ответ, — без второго запроса
  pendingIdea[idea.id] = 'vote'
  try {
    await (revoke ? api.revokeVote(idea.id) : api.vote(idea.id))
  } catch (failure) {
    notify.error(failure.message)
  } finally {
    delete pendingIdea[idea.id]
    reload()
  }
}
</script>

<template>
  <div class="container page">
    <RouterLink class="back" :to="{ name: 'contests' }"><Icon name="arrow-left" /> {{ t('contest.back') }}</RouterLink>

    <EmptyState
      v-if="error?.status === 404"
      icon="eye-off"
      :title="t('contest.notFound.title')"
      :text="t('contest.notFound.text')"
    >
      <RouterLink class="btn" :to="{ name: 'contests' }">{{ t('contest.notFound.toList') }}</RouterLink>
    </EmptyState>
    <EmptyState
      v-else-if="error"
      tone="error"
      icon="alert"
      :title="t('contest.loadFailed')"
      :text="error.message"
    >
      <button class="btn" type="button" @click="reload"><Icon name="refresh" /> {{ t('common.retry') }}</button>
    </EmptyState>

    <div v-else-if="!snapshot" class="stack" aria-busy="true">
      <div class="skeleton" style="height: 40px; width: 60%" />
      <div class="skeleton" style="height: 86px" />
      <div class="skeleton" style="height: 220px" />
    </div>

    <template v-else>
      <header class="contest-header">
        <div class="row">
          <PhaseBadge :phase="phase" />
          <span class="faint">{{ t('contest.meta', { id: contest.id, date: formatDateTime(contest.created_at, now) }) }}</span>
        </div>
        <h1 class="topic">{{ contest.topic }}</h1>
      </header>

      <div v-if="refreshFailed" class="notice notice-warning refresh" role="status">
        <Icon name="wifi" class="icon" />
        <span>{{ t('contest.refreshFailed') }}</span>
        <button class="btn btn-sm" type="button" @click="reload">{{ t('contest.refresh') }}</button>
      </div>

      <PhaseTimeline :contest="contest" :now="now" />

      <div class="layout">
        <main class="main stack">
          <!-- ===================== Организатор ===================== -->
          <template v-if="organizer">
            <StatTiles :stats="snapshot.stats" />

            <section v-if="phase === 'submission'" class="card hidden-ideas">
              <Icon name="eye-off" :size="22" />
              <div>
                <h2>{{ t('contest.organizer.hiddenTitle') }}</h2>
                <p class="muted">
                  {{
                    t('contest.organizer.hiddenText', {
                      ideas: tn('common.ideas', snapshot.stats.ideas_count),
                      date: formatDateTime(contest.submission_deadline, now),
                    })
                  }}
                </p>
              </div>
            </section>

            <section v-else-if="phase === 'voting'">
              <div class="section-title">
                <Icon name="chart" />
                <h2>{{ t('contest.organizer.liveTitle') }}</h2>
                <span class="live"><span class="pulse" /> {{ t('contest.organizer.live') }}</span>
              </div>
              <ResultsList v-if="ideas.length" :ideas="ideas" :final="false" />
              <EmptyState
                v-else
                icon="inbox"
                :title="t('contest.noIdeas')"
                :text="t('contest.organizer.nothingToVote')"
              />
              <p class="faint note">{{ t('contest.organizer.authorsHidden') }}</p>
            </section>

            <section v-else>
              <div class="section-title">
                <Icon name="trophy" />
                <h2>{{ t('contest.resultsTitle') }}</h2>
              </div>
              <ResultsList v-if="ideas.length" :ideas="ideas" :winner-id="snapshot.winner_idea_id" final />
              <EmptyState v-else icon="inbox" :title="t('contest.noIdeas')" :text="t('contest.noWinner')" />
            </section>
          </template>

          <!-- ===================== Участник: приём идей ===================== -->
          <template v-else-if="phase === 'submission'">
            <section class="card">
              <div class="card-title">
                <Icon name="bulb" />
                <h2>{{ t('contest.submission.newIdea') }}</h2>
              </div>
              <IdeaForm
                ref="ideaForm"
                id-prefix="new-idea"
                :submit-label="t('contest.submission.submit')"
                :pending="submitPending"
                @submit="submitIdea"
              />
            </section>

            <section>
              <div class="section-title">
                <h2>{{ t('contest.submission.myIdeas') }}</h2>
                <span class="count">{{ myIdeas.length }}</span>
              </div>
              <div v-if="myIdeas.length" class="stack">
                <template v-for="idea in myIdeas" :key="idea.id">
                  <section v-if="editingId === idea.id" class="card editing">
                    <div class="card-title"><Icon name="edit" /><h3>{{ t('contest.submission.editTitle') }}</h3></div>
                    <div v-if="editConflict" class="notice notice-warning conflict" role="status">
                      <Icon name="alert" class="icon" />
                      <span>{{ t('contest.submission.conflict') }}</span>
                    </div>
                    <div v-else-if="editedElsewhere" class="notice notice-warning conflict" role="status">
                      <Icon name="alert" class="icon" />
                      <span>{{ t('contest.submission.editedElsewhere') }}</span>
                    </div>
                    <IdeaForm
                      :id-prefix="`edit-${idea.id}`"
                      :initial-title="editBase.title"
                      :initial-description="editBase.description"
                      :submit-label="t('common.save')"
                      cancelable
                      :pending="editPending"
                      @submit="(payload) => saveEdit(idea, payload)"
                      @cancel="cancelEdit"
                    />
                  </section>
                  <IdeaCard
                    v-else
                    :idea="idea"
                    can-edit
                    can-delete
                    :pending="pendingIdea[idea.id] ?? null"
                    @edit="startEdit"
                    @delete="deleteIdea"
                  />
                </template>
              </div>
              <p v-else class="muted">{{ t('contest.submission.noMine') }}</p>
            </section>

            <div class="notice">
              <Icon name="eye-off" class="icon" />
              <span>
                {{ t('contest.submission.hiddenNotice', { date: formatDateTime(contest.submission_deadline, now) }) }}
              </span>
            </div>
          </template>

          <!-- ===================== Участник: голосование ===================== -->
          <template v-else-if="phase === 'voting'">
            <div class="notice notice-info">
              <Icon name="vote" class="icon" />
              <span>
                {{ t('contest.voting.notice', { date: formatDateTime(contest.voting_deadline, now) }) }}
              </span>
            </div>

            <section>
              <div class="section-title">
                <h2>{{ t('contest.voting.ideas') }}</h2>
                <span class="count">{{ ideas.length }}</span>
                <span class="spacer" />
                <span class="badge badge-success" data-test="my-votes">
                  {{ t('contest.voting.myVotes', { votes: myVotes, total: othersIdeas.length }) }}
                </span>
              </div>
              <div v-if="ideas.length" class="stack">
                <IdeaCard
                  v-for="idea in ideas"
                  :key="idea.id"
                  :idea="idea"
                  :can-vote="!idea.is_mine"
                  :can-delete="idea.is_mine"
                  :pending="pendingIdea[idea.id] ?? null"
                  @vote="(target) => castVote(target)"
                  @revoke="(target) => castVote(target, true)"
                  @delete="deleteIdea"
                />
              </div>
              <EmptyState v-else icon="inbox" :title="t('contest.noIdeas')" :text="t('contest.voting.nothingToVote')" />
            </section>
          </template>

          <!-- ===================== Участник: итоги ===================== -->
          <template v-else>
            <div v-if="winner?.is_mine" class="celebrate" role="status">
              <Icon name="trophy" :size="28" />
              <div>
                <h2>{{ t('contest.finished.won') }}</h2>
                <p>{{ t('contest.finished.wonText', { title: winner.title, votes: tn('common.votes', winner.votes_count) }) }}</p>
              </div>
            </div>
            <section>
              <div class="section-title">
                <Icon name="trophy" />
                <h2>{{ t('contest.resultsTitle') }}</h2>
              </div>
              <ResultsList v-if="ideas.length" :ideas="ideas" :winner-id="snapshot.winner_idea_id" final />
              <EmptyState v-else icon="inbox" :title="t('contest.noIdeas')" :text="t('contest.noWinner')" />
            </section>
          </template>
        </main>

        <aside class="aside stack">
          <section class="card rule">
            <div class="card-title"><Icon name="trophy" /><h2>{{ t('contest.rule.title') }}</h2></div>
            <ol class="rule-list">
              <li>{{ t('contest.rule.votes') }}</li>
              <li>
                {{ t('contest.rule.tieBefore') }} <strong>{{ t('contest.rule.tieStrong') }}</strong
                >{{ t('contest.rule.tieAfter') }}
              </li>
              <li>{{ t('contest.rule.none') }}</li>
            </ol>
          </section>

          <template v-if="organizer">
            <SchedulePanel :schedule="snapshot.schedule" :contest-id="contest.id" :now="now" :ideas="ideas" />
            <ParticipantsPanel :contest-id="contest.id" />
          </template>
          <section v-else class="card">
            <div class="card-title"><Icon name="user" /><h2>{{ t('contest.mine.title') }}</h2></div>
            <ul class="facts">
              <li><span>{{ t('contest.mine.ideas') }}</span><strong>{{ myIdeas.length }}</strong></li>
              <li v-if="phase !== 'submission'"><span>{{ t('contest.mine.votes') }}</span><strong>{{ myVotes }}</strong></li>
            </ul>
            <RouterLink class="btn btn-soft btn-sm mail-link" :to="{ name: 'mail', query: { contest: contest.id } }">
              <Icon name="mail" /> {{ t('contest.mine.mail') }}
            </RouterLink>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  color: var(--text-2);
  font-weight: 600;
  font-size: var(--text-md);
}

.contest-header {
  margin-bottom: 18px;
}

.topic {
  margin-top: 10px;
  overflow-wrap: anywhere;
}

.refresh {
  align-items: center;
  margin-bottom: 14px;
}

.refresh span {
  flex: 1;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 24px;
  align-items: start;
  margin-top: 24px;
}

.aside {
  position: sticky;
  top: var(--sticky-top);
}

.count {
  color: var(--text-3);
  font-weight: 600;
}

.hidden-ideas {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  color: var(--text-2);
}

.hidden-ideas h2 {
  margin-bottom: 4px;
  color: var(--text);
}

.live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  color: var(--phase-voting);
  font-size: var(--text-sm);
  font-weight: 600;
}

.pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.25;
  }
}

.note {
  margin-top: 10px;
}

.editing {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-soft);
}

.conflict {
  margin-bottom: 14px;
}

.celebrate {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  border-radius: var(--radius-lg);
  background: var(--gold-soft);
  border: 1px solid var(--gold);
  color: var(--warning);
}

.celebrate h2 {
  color: var(--text);
}

.celebrate p {
  color: var(--text-2);
}

.rule-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-2);
  font-size: var(--text-md);
}

.rule-list li + li {
  margin-top: 6px;
}

.facts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}

.facts li {
  display: flex;
  justify-content: space-between;
  color: var(--text-2);
}

.facts strong {
  color: var(--text);
}

.mail-link {
  width: 100%;
}

@media (max-width: 980px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .aside {
    position: static;
  }
}
</style>
