<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '@/api/client';
import { useIdentityStore } from '@/stores/identity';
import ActionButton from '@/components/ActionButton.vue';
import EvidencePanel from '@/components/EvidencePanel.vue';
import ExecutionTracePanel from '@/components/ExecutionTracePanel.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import type { ChatStreamMessage, ExecutionTraceEvent } from '@/api/types';
import { reportFriendlyError } from '@/utils/error';

const identity = useIdentityStore();
const route = useRoute();
const input = ref('');
const outputMode = ref<'chat' | 'brief' | 'investment_report'>('chat');
const activeSymbol = ref('AAPL');
const sending = ref(false);
const errorMsg = ref<string | null>(null);
const threadEl = ref<HTMLElement | null>(null);
const traceEvents = ref<ExecutionTraceEvent[]>([]);
const hydrating = ref(true);
const openTraceMessageId = ref<string | null>(null);

const suggestions = [
  'AAPL 最近的基本面如何？',
  'AAPL 今天相比上次查看有什么变化？',
  '帮我复查 NVDA 的主要风险证据',
  '生成 TSLA 的深度研究摘要，不要给交易建议',
  '对比 MSFT 和 GOOGL 的证据质量',
];

const welcomeMessage: ChatStreamMessage = {
  id: 'welcome',
  role: 'assistant',
  content: '欢迎使用 FinSight 研究对话。你可以要求本系统生成复查摘要、解释风险变化、整理报告证据。所有输出仅用于研究，不构成投资建议。',
  status: 'done',
};

const messages = ref<ChatStreamMessage[]>([welcomeMessage]);

const modeLabel = computed(() => {
  const mode = String(route.query.mode || '');
  if (mode === 'qa') return '智能问答';
  if (mode === 'financials') return '财报分析';
  if (mode === 'report') return '报告生成';
  return '对话研究';
});

async function scrollToBottom() {
  await nextTick();
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight;
}

function chatStorageKey() {
  return `finsight-chat-history:${identity.sessionId}`;
}

function normalizeHistoryMessage(message: ChatStreamMessage): ChatStreamMessage | null {
  const role = message.role === 'user' || message.role === 'assistant' ? message.role : null;
  const content = String(message.content || '').trim();
  if (!role || !content) return null;
  return {
    ...message,
    id: String(message.id || `${role}-${Date.now()}`),
    role,
    content,
    status: message.status === 'error' ? 'error' : 'done',
  };
}

function applyHistory(history: ChatStreamMessage[]) {
  const normalized = history
    .map((message) => normalizeHistoryMessage(message))
    .filter((message): message is ChatStreamMessage => Boolean(message));
  messages.value = [welcomeMessage, ...normalized];
}

function loadLocalHistory() {
  if (typeof window === 'undefined') return;
  try {
    const raw = window.localStorage.getItem(chatStorageKey());
    if (!raw) return;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return;
    applyHistory(parsed as ChatStreamMessage[]);
  } catch {
    window.localStorage.removeItem(chatStorageKey());
  }
}

function persistLocalHistory() {
  if (typeof window === 'undefined' || hydrating.value) return;
  const history = messages.value
    .filter((message) => message.id !== 'welcome' && message.status !== 'streaming')
    .slice(-100)
    .map((message) => ({ ...message, status: message.status === 'error' ? 'error' : 'done' }));
  try {
    window.localStorage.setItem(chatStorageKey(), JSON.stringify(history));
  } catch {
    // 配额写满 / 隐私模式禁用存储：持久化失败不应打断聊天流（读取侧已有对称兜底）
  }
}

// deep watch 每个流式 token 都会触发，全量序列化 100 条消息会造成主线程抖动；防抖合并
let persistTimer: ReturnType<typeof setTimeout> | null = null;
function schedulePersistLocalHistory() {
  if (persistTimer) clearTimeout(persistTimer);
  persistTimer = setTimeout(persistLocalHistory, 500);
}

async function loadRemoteHistory() {
  try {
    const data = await apiClient.getChatHistory(identity.sessionId, 100);
    if (data.messages.length > 0) applyHistory(data.messages);
  } catch {
    // 后端历史不可用时保留本地缓存，不阻断对话。
  }
}

function seedTrace(query: string) {
  traceEvents.value = [
    {
      id: `prepare-${Date.now()}`,
      type: 'thinking',
      stage: 'prepare_context',
      title: '准备上下文',
      message: `读取会话、标的 ${activeSymbol.value} 与输出模式 ${outputMode.value}`,
      status: 'done',
      timestamp: new Date().toISOString(),
    },
    {
      id: `plan-${Date.now()}`,
      type: 'thinking',
      stage: 'plan_research',
      title: '规划研究路径',
      message: `用户问题已拆解为可复查研究任务，长度 ${query.length} 字。`,
      status: 'running',
      timestamp: new Date().toISOString(),
    },
  ];
}

function appendTrace(event: ExecutionTraceEvent) {
  traceEvents.value = [
    ...traceEvents.value.map((item) => item.status === 'running' ? { ...item, status: 'done' } : item),
    event,
  ].slice(-24);
}

function traceSummary(events?: ExecutionTraceEvent[] | null, running = false) {
  const list = events || [];
  const done = list.filter((event) => event.status === 'done').length;
  const errors = list.filter((event) => event.status === 'error').length;
  return {
    done,
    total: list.length,
    label: errors ? `${errors} 个异常` : running ? '运行中' : '已完成',
  };
}

let streamAbort: AbortController | null = null;

async function send(text?: string): Promise<void> {
  const query = (text || input.value).trim();
  if (!query || sending.value) return;
  errorMsg.value = null;
  sending.value = true;
  streamAbort?.abort();
  streamAbort = new AbortController();
  seedTrace(query);
  const userMessage: ChatStreamMessage = { id: `user-${Date.now()}`, role: 'user', content: query, status: 'done' };
  const assistantMessage: ChatStreamMessage = { id: `assistant-${Date.now()}`, role: 'assistant', content: '', status: 'streaming', traceEvents: traceEvents.value };
  messages.value = [...messages.value, userMessage, assistantMessage];
  openTraceMessageId.value = assistantMessage.id;
  input.value = '';
  await scrollToBottom();
  try {
    await apiClient.streamChat({
      query,
      session_id: identity.sessionId,
      context: { active_symbol: activeSymbol.value },
      options: { output_mode: outputMode.value },
    }, {
      onToken: async (token) => {
        assistantMessage.content += token;
        messages.value = [...messages.value];
        await scrollToBottom();
      },
      onEvent: (event) => {
        appendTrace(event);
        assistantMessage.traceEvents = traceEvents.value;
        messages.value = [...messages.value];
      },
      onDone: (evidence) => {
        assistantMessage.status = 'done';
        assistantMessage.evidence = evidence;
        appendTrace({
          id: `done-${Date.now()}`,
          type: 'done',
          stage: 'render_done',
          title: '形成结论',
          message: '研究输出已完成，证据面板已附加。',
          status: 'done',
          timestamp: new Date().toISOString(),
        });
        assistantMessage.traceEvents = traceEvents.value;
        messages.value = [...messages.value];
      },
      onError: (message) => {
        assistantMessage.status = 'error';
        errorMsg.value = message || 'AI 助手暂时无法完成请求，请稍后重试。';
        appendTrace({
          id: `error-${Date.now()}`,
          type: 'error',
          stage: 'stream_error',
          title: '执行失败',
          message,
          status: 'error',
          timestamp: new Date().toISOString(),
        });
        assistantMessage.traceEvents = traceEvents.value;
        messages.value = [...messages.value];
      },
    }, { signal: streamAbort.signal });
  } catch (error) {
    assistantMessage.status = 'error';
    errorMsg.value = reportFriendlyError(error, 'AI 助手暂时无法完成请求，请稍后重试。');
    assistantMessage.traceEvents = traceEvents.value;
    messages.value = [...messages.value];
  } finally {
    sending.value = false;
    await scrollToBottom();
  }
}

async function clearChat() {
  messages.value = [welcomeMessage];
  traceEvents.value = [];
  errorMsg.value = null;
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(chatStorageKey());
  }
  try {
    await apiClient.clearChatHistory(identity.sessionId);
  } catch {
    // 清空本地体验优先，远端失败不阻断用户继续使用。
  }
}

function exportMarkdown() {
  const body = messages.value
    .filter((message) => message.id !== 'welcome')
    .map((message) => `## ${message.role === 'user' ? '用户问题' : 'FinSight 输出'}\n\n${message.content}`)
    .join('\n\n---\n\n');
  const blob = new Blob([`# FinSight 研究对话\n\n${body || '暂无内容'}\n`], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `finsight-chat-${Date.now()}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

watch(messages, schedulePersistLocalHistory, { deep: true });

onMounted(async () => {
  const prefill = String(route.query.prefill || '').trim();
  const symbol = String(route.query.symbol || '').trim().toUpperCase();
  const mode = String(route.query.mode || '');
  if (symbol) activeSymbol.value = symbol;
  if (mode === 'financials') outputMode.value = 'brief';
  if (mode === 'report') outputMode.value = 'investment_report';
  loadLocalHistory();
  await loadRemoteHistory();
  hydrating.value = false;
  persistLocalHistory();
  if (prefill) {
    input.value = prefill;
    void send(prefill);
  }
});

// 路由离开时中止进行中的流：否则连接不关闭、后端继续生成，
// 回调闭包持续 mutate 已卸载组件的状态
onUnmounted(() => {
  streamAbort?.abort();
  if (persistTimer) clearTimeout(persistTimer);
  persistLocalHistory(); // 防抖挂起时离开页面，把最后一批消息落盘
});
</script>

<template>
  <section class="chat-page">
    <header class="page-card chat-hero">
      <div>
        <p class="kicker">RESEARCH COPILOT</p>
        <h2>对话式研究与报告生成</h2>
        <p>当前模式：{{ modeLabel }}。输出报告、复查风险、解释证据变化；右侧实时展示执行过程。</p>
      </div>
      <div class="controls">
        <label>
          标的
          <input v-model="activeSymbol" placeholder="AAPL">
        </label>
        <label>
          输出模式
          <select v-model="outputMode">
            <option value="chat">对话</option>
            <option value="brief">简报</option>
            <option value="investment_report">深度报告</option>
          </select>
        </label>
        <button @click="exportMarkdown">导出 MD</button>
        <button v-if="messages.length > 1" @click="clearChat">清空</button>
      </div>
    </header>

    <div class="chat-grid">
      <main class="page-card chat-thread">
        <div ref="threadEl" class="thread-scroll">
          <article v-for="item in messages" :key="item.id" class="message" :class="item.role">
            <div class="avatar">{{ item.role === 'user' ? 'YOU' : 'AI' }}</div>
            <div class="message-body">
              <div class="message-meta">
                <strong>{{ item.role === 'user' ? identity.email || '研究员' : 'FinSight' }}</strong>
                <span v-if="item.status === 'streaming'" class="running">
                  <span class="thinking-dots">思考中</span>
                </span>
                <span v-if="item.status === 'error'" class="failed">失败</span>
              </div>
              <pre class="bubble-body">{{ item.content || (item.status === 'streaming' ? '' : '') }}<span v-if="item.status === 'streaming'" class="cursor-blink">|</span></pre>
              <EvidencePanel
                v-if="item.role === 'assistant' && item.status === 'done' && item.evidence"
                v-bind="item.evidence"
                compact
              />
              <div v-if="item.role === 'assistant' && item.traceEvents?.length" class="inline-trace">
                <button
                  class="trace-toggle"
                  type="button"
                  @click="openTraceMessageId = openTraceMessageId === item.id ? null : item.id"
                >
                  <span>执行过程</span>
                  <strong>{{ traceSummary(item.traceEvents, item.status === 'streaming').done }}/{{ traceSummary(item.traceEvents, item.status === 'streaming').total }}</strong>
                  <em :class="{ live: item.status === 'streaming' }">{{ traceSummary(item.traceEvents, item.status === 'streaming').label }}</em>
                </button>
                <ExecutionTracePanel
                  v-if="openTraceMessageId === item.id"
                  :events="item.traceEvents"
                  :running="item.status === 'streaming'"
                  compact
                />
              </div>
            </div>
          </article>
        </div>

        <div v-if="messages.length <= 1" class="suggestions">
          <button v-for="item in suggestions" :key="item" :disabled="sending" @click="send(item)">{{ item }}</button>
        </div>

        <StatusBanner
          v-if="errorMsg"
          variant="error"
          :message="errorMsg"
          dismissible
          @dismiss="errorMsg = null"
        />

        <footer class="composer">
          <textarea
            v-model="input"
            placeholder="问点什么，例如：AAPL 今天相比上次查看有什么变化？"
            @keydown.ctrl.enter.prevent="send()"
            @keydown.meta.enter.prevent="send()"
          />
          <ActionButton :disabled="!input.trim()" :loading="sending" loading-text="执行中..." @click="send()">
            发送研究任务
          </ActionButton>
        </footer>
      </main>

    </div>
  </section>
</template>

<style scoped>
.chat-page {
  width: 100%;
  height: calc(100dvh - 112px);
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 18px;
  overflow: hidden;
}

.chat-hero {
  display: flex;
  justify-content: space-between;
  gap: 22px;
  padding: 26px;
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 38%),
    var(--fin-card);
}

.kicker {
  margin: 0 0 6px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h2,
h3 {
  margin: 0;
  color: var(--fin-text);
}

.chat-hero p,
label {
  color: var(--fin-muted);
}

.controls {
  display: flex;
  align-items: end;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

label {
  display: grid;
  gap: 6px;
  font-size: 13px;
  font-weight: 800;
}

input,
select,
textarea {
  border-radius: 14px;
  padding: 11px 12px;
}

.controls button,
.composer button,
.suggestions button {
  border: 0;
  border-radius: 14px;
  padding: 11px 14px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.chat-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 18px;
  min-height: 0;
  overflow: hidden;
}

.chat-thread {
  padding: 18px;
  min-height: 0;
  display: grid;
  grid-template-rows: 1fr auto auto auto;
  gap: 14px;
  overflow: hidden;
}

.thread-scroll {
  overflow-y: auto;
  min-height: 0;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  display: grid;
  align-content: start;
  gap: 16px;
  padding-right: 6px;
}

.message {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr);
  gap: 12px;
}

.message.user {
  grid-template-columns: minmax(0, 1fr) 42px;
}

.message.user .avatar {
  grid-column: 2;
}

.message.user .message-body {
  grid-row: 1;
}

.avatar {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: var(--fin-primary);
  color: var(--fin-bg);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
}

.message-body {
  border: 1px solid var(--fin-border);
  border-radius: 20px;
  padding: 14px;
  background: var(--fin-card-inset);
  display: grid;
  gap: 10px;
}

.message.user .message-body {
  background: var(--fin-primary-soft);
}

.message-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  color: var(--fin-text-2);
  font-size: 13px;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  color: var(--fin-text);
  font-size: 15px;
  line-height: 1.75;
  font-family: inherit;
}

.running {
  color: var(--fin-success);
}

.thinking-dots {
  display: inline-block;
  font-weight: 600;
}

.thinking-dots::after {
  content: '...';
  animation: thinking 1.4s steps(4, end) infinite;
}

@keyframes thinking {
  0%, 20% { content: ''; }
  40% { content: '.'; }
  60% { content: '..'; }
  80%, 100% { content: '...'; }
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--fin-primary);
  font-weight: bold;
}

@keyframes blink {
  50% { opacity: 0; }
}

.failed {
  color: var(--fin-danger);
}

.inline-trace {
  display: grid;
  gap: 8px;
}

.trace-toggle {
  width: 100%;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  padding: 7px 10px;
  background: var(--fin-card-soft);
  color: var(--fin-text);
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 850;
}

.trace-toggle strong {
  color: var(--fin-primary);
}

.trace-toggle em {
  margin-left: auto;
  color: var(--fin-muted);
  font-style: normal;
  font-size: 12px;
}

.trace-toggle em.live {
  color: var(--fin-success);
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestions button {
  background: var(--fin-card-inset);
  color: var(--fin-text);
  border: 1px solid var(--fin-border);
}

.composer {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 12px;
}

textarea {
  height: 92px;
  min-height: 72px;
  max-height: 150px;
  resize: vertical;
}

@media (max-width: 1080px) {
  .chat-page {
    height: auto;
    min-height: calc(100dvh - 96px);
    overflow: visible;
  }

  .chat-hero,
  .chat-grid {
    grid-template-columns: 1fr;
    display: grid;
    overflow: visible;
  }

  .chat-thread {
    min-height: 560px;
  }

  .thread-scroll {
    max-height: 52dvh;
  }

  .controls {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .chat-page {
    gap: 10px;
    min-height: calc(100dvh - 84px);
  }

  .chat-hero,
  .chat-thread {
    padding: 12px;
  }

  .chat-hero {
    gap: 10px;
  }

  .chat-hero .kicker + h2 + p {
    display: none;
  }

  .chat-thread {
    min-height: 480px;
    gap: 8px;
  }

  .thread-scroll {
    max-height: 42dvh;
  }

  .composer {
    order: 2;
  }

  .composer {
    grid-template-columns: 1fr;
  }

  .suggestions {
    order: 3;
    max-height: 120px;
    overflow-y: auto;
  }

  textarea {
    min-height: 64px;
  }
}
</style>
