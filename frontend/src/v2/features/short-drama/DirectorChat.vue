<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { shortDramaApi } from '@/api/modules'
import GlassPanel from '@/v2/components/GlassPanel.vue'
import StatusBadge from '@/v2/components/StatusBadge.vue'
import V2Button from '@/v2/components/V2Button.vue'
import { subscribeDirector, unsubscribeDirector } from '@/ws/client'

const props = defineProps<{ projectId: number }>()
const emit = defineEmits<{ (e: 'edit-prompt', code: string, title: string): void }>()

interface ChatMessage {
  id: number
  role: string
  content: string
  revision_hash: string
  created_at: string
}

const conversations = ref<any[]>([])
const activeConvId = ref<number | null>(null)
const messages = ref<ChatMessage[]>([])
const proposals = ref<any[]>([])
const input = ref('')
const sending = ref(false)
const generatingProposals = ref(false)
const error = ref('')
const messagesEl = ref<HTMLElement | null>(null)

async function loadConversations() {
  try {
    conversations.value = await shortDramaApi.directorConversations(props.projectId)
    if (conversations.value.length && !activeConvId.value) {
      await openConversation(conversations.value[0].id)
    }
  } catch { conversations.value = [] }
}

async function openConversation(id: number) {
  activeConvId.value = id
  try {
    const detail = await shortDramaApi.directorConversationDetail(props.projectId, id)
    messages.value = detail.messages || []
    scrollBottom()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '加载会话失败'
  }
  void loadProposals()
}

async function createConversation() {
  try {
    const conv = await shortDramaApi.directorCreateConversation(props.projectId, { title: '新对话' })
    await loadConversations()
    await openConversation(conv.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建会话失败'
  }
}

async function send() {
  const content = input.value.trim()
  if (!content || sending.value) return
  if (!activeConvId.value) {
    await createConversation()
    if (!activeConvId.value) return
  }
  sending.value = true; error.value = ''
  const optimistic: ChatMessage = {
    id: Date.now(), role: 'user', content,
    revision_hash: '', created_at: new Date().toISOString(),
  }
  messages.value.push(optimistic)
  input.value = ''
  scrollBottom()
  try {
    const reply = await shortDramaApi.directorSendChat(props.projectId, activeConvId.value, { content })
    messages.value = messages.value.filter(m => m.id !== optimistic.id)
    messages.value.push({
      id: reply.id, role: 'assistant', content: reply.content,
      revision_hash: reply.revision_hash, created_at: new Date().toISOString(),
    })
    // 用户消息也追加显示
    messages.value.unshift() // noop 保留顺序
    scrollBottom()
  } catch (e: any) {
    messages.value = messages.value.filter(m => m.id !== optimistic.id)
    input.value = content // 恢复输入
    error.value = e?.response?.data?.detail || '发送失败'
  } finally { sending.value = false }
}

async function loadProposals() {
  try {
    proposals.value = await shortDramaApi.directorProposals(props.projectId, 'pending')
  } catch { proposals.value = [] }
}

async function generateProposals() {
  generatingProposals.value = true; error.value = ''
  try {
    await shortDramaApi.directorGenerateProposals(props.projectId)
    await loadProposals()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '生成提案失败'
  } finally { generatingProposals.value = false }
}

async function applyProposal(p: any) {
  error.value = ''
  try {
    await shortDramaApi.directorApplyProposal(props.projectId, p.id)
    await loadProposals()
  } catch (e: any) {
    const detail = e?.response?.data?.detail || ''
    error.value = detail.startsWith('EXPIRED:') ? detail.replace('EXPIRED:', '') + '（请重新生成提案）' : (detail || '应用失败')
    await loadProposals()
  }
}

async function dismissProposal(p: any) {
  const reason = prompt('忽略原因（可选）') || ''
  error.value = ''
  try {
    await shortDramaApi.directorDismissProposal(props.projectId, p.id, { reason })
    await loadProposals()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '忽略失败'
  }
}

function scrollBottom() {
  void nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

onMounted(() => {
  subscribeDirector(props.projectId)
  void loadConversations()
  void loadProposals()
})
watch(() => props.projectId, (id) => {
  activeConvId.value = null
  messages.value = []
  subscribeDirector(id)
  void loadConversations()
  void loadProposals()
})
</script>

<template>
  <GlassPanel
    title="导演对话"
    description="与 AI 导演助理对话。所有数据修改必须通过候选提案确认，无一键执行。"
  >
    <template #actions>
      <V2Button variant="ghost" size="sm" @click="createConversation">+ 新对话</V2Button>
    </template>

    <div v-if="error" class="dc-error">{{ error }}</div>

    <div v-if="conversations.length" class="conv-tabs">
      <button v-for="c in conversations" :key="c.id" class="conv-tab"
        :class="{ active: activeConvId === c.id }" @click="openConversation(c.id)">
        {{ c.title }}
      </button>
    </div>

    <!-- 消息区 -->
    <div ref="messagesEl" class="messages">
      <div v-if="!messages.length" class="empty-tip">
        {{ activeConvId ? '发送第一条消息开始对话。' : '创建或选择一个对话。' }}
      </div>
      <div v-for="m in messages" :key="m.id" class="msg" :class="'msg-' + m.role">
        <div class="msg-bubble">
          <p>{{ m.content }}</p>
          <small v-if="m.role === 'assistant' && m.revision_hash" class="msg-rev">
            来源版本 {{ m.revision_hash.slice(0, 10) }}…
          </small>
        </div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-row">
      <input
        v-model="input"
        class="chat-input"
        placeholder="向 AI 导演提问…"
        :disabled="sending"
        @keyup.enter="send"
      />
      <V2Button variant="primary" size="sm" :disabled="sending || !input.trim()" @click="send">
        {{ sending ? '回复中…' : '发送' }}
      </V2Button>
    </div>

    <!-- 候选提案 -->
    <div class="proposals-section">
      <div class="proposals-head">
        <h4 class="section-title">候选操作（{{ proposals.length }}）</h4>
        <div class="dc-prompt-actions">
          <V2Button variant="ghost" size="sm" :disabled="generatingProposals" @click="generateProposals">
            {{ generatingProposals ? '生成中…' : 'AI 生成提案' }}
          </V2Button>
          <V2Button variant="ghost" size="sm" @click="emit('edit-prompt', 'proposal', 'AI 提案生成')">📝</V2Button>
        </div>
      </div>
      <div v-if="!proposals.length" class="empty-tip">暂无待确认提案。</div>
      <div v-else class="proposal-list">
        <div v-for="p in proposals" :key="p.id" class="proposal-card">
          <header>
            <b>{{ p.title || p.action_desc }}</b>
            <StatusBadge v-if="!p.revision_current" tone="warning">版本过期</StatusBadge>
          </header>
          <small class="proposal-target">{{ p.target_type }}:{{ p.target_ref }} · {{ p.action_desc }}</small>
          <div class="diff-list">
            <div v-for="(c, ci) in p.changes" :key="ci" class="diff-row">
              <code>{{ c.field }}</code>
              <span class="diff-before">{{ c.before || '（空）' }}</span>
              <span class="diff-arrow">→</span>
              <span class="diff-after">{{ c.after || '（空）' }}</span>
            </div>
          </div>
          <small v-if="p.rationale" class="proposal-rationale">{{ p.rationale }}</small>
          <small v-if="p.impact_refs?.length" class="proposal-impact">影响：{{ p.impact_refs.join('、') }}</small>
          <div class="proposal-actions">
            <V2Button variant="primary" size="sm" :disabled="!p.revision_current" @click="applyProposal(p)">应用</V2Button>
            <V2Button variant="ghost" size="sm" @click="dismissProposal(p)">忽略</V2Button>
          </div>
        </div>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.dc-error{padding:10px;color:#ffdce1;background:rgba(255,127,145,.1);border-radius:10px;font-size:12px;margin-bottom:8px}
.empty-tip{color:var(--v2-text-subtle);font-size:12px;padding:12px 0}
.conv-tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.conv-tab{padding:6px 12px;color:var(--v2-text-muted);background:transparent;border:1px solid var(--v2-border);border-radius:9px;cursor:pointer;font-size:12px}
.conv-tab.active{color:var(--v2-text);background:rgba(130,149,255,.1);border-color:rgba(130,149,255,.35)}
.messages{max-height:260px;overflow-y:auto;display:grid;gap:8px;padding:8px;background:rgba(0,0,0,.15);border-radius:10px;margin-bottom:10px}
.msg{display:flex}
.msg-user{justify-content:flex-end}
.msg-assistant{justify-content:flex-start}
.msg-bubble{max-width:80%;padding:9px 12px;border-radius:12px;display:grid;gap:4px}
.msg-user .msg-bubble{background:rgba(130,149,255,.18);border:1px solid rgba(130,149,255,.25)}
.msg-assistant .msg-bubble{background:var(--v2-surface-soft);border:1px solid var(--v2-border)}
.msg-bubble p{margin:0;font-size:12px;color:var(--v2-text);line-height:1.6;white-space:pre-wrap}
.msg-rev{color:var(--v2-text-subtle);font-size:9px}
.input-row{display:flex;gap:8px}
.chat-input{flex:1;min-height:36px;padding:8px 12px;color:var(--v2-text);background:rgba(3,8,17,.72);border:1px solid var(--v2-border);border-radius:10px;font-size:12px}
.proposals-section{margin-top:14px;border-top:1px solid var(--v2-border);padding-top:12px}
.proposals-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.dc-prompt-actions{display:flex;gap:6px;align-items:center}
.section-title{margin:0;font-size:13px;color:#e8edff}
.proposal-list{display:grid;gap:8px}
.proposal-card{padding:12px;background:var(--v2-surface-soft);border:1px solid var(--v2-border);border-radius:10px;display:grid;gap:8px}
.proposal-card header{display:flex;align-items:center;gap:8px;justify-content:space-between;flex-wrap:wrap}
.proposal-card header b{font-size:12px;color:var(--v2-text)}
.proposal-target{color:var(--v2-text-subtle);font-size:10px}
.diff-list{display:grid;gap:4px}
.diff-row{display:flex;align-items:center;gap:8px;font-size:11px;flex-wrap:wrap}
.diff-row code{color:var(--v2-primary);font-size:10px}
.diff-before{color:var(--v2-danger);text-decoration:line-through;opacity:.7;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.diff-arrow{color:var(--v2-text-subtle)}
.diff-after{color:var(--v2-success);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.proposal-rationale{color:var(--v2-text-muted);font-size:11px;line-height:1.5}
.proposal-impact{color:var(--v2-text-subtle);font-size:10px}
.proposal-actions{display:flex;gap:8px}
</style>