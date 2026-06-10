<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '@/api/client';
import { useIdentityStore } from '@/stores/identity';
import EvidencePanel from '@/components/EvidencePanel.vue';
import ExecutionTracePanel from '@/components/ExecutionTracePanel.vue';
import type { ChatStreamMessage, ExecutionTraceEvent } from '@/api/types';

const identity = useIdentityStore();
const route = useRoute();
const input = ref('');
const outputMode = ref<'chat' | 'brief' | 'investment_report'>('chat');
const activeSymbol = ref('AAPL');
const sending = ref(false);
const errorMsg = ref<string | null>(null);
const threadEl = ref<HTMLElement | null>(null);
const traceEvents = ref<ExecutionTraceEvent[]>([]);

const suggestions = [
  'AAPL 最近的基本面如何？',
  'AAPL 今天相比上次查看有什么变化？',
  '帮我复查 NVDA 的主要风险证据',
  '生成 TSLA 的深度研究摘要，不要给交易建议',
  '对比 MSFT 和 GOOGL 的证据质量',
];

const messages = ref<ChatStreamMessage[]>([
  {
    id: 'welcome',
    role: 'assistant',
    content: '欢迎使用 FinSight 研究对话。你可以要求本系统生成复查摘要、解释风险变化、整理报告证据。所有输出仅用于研究，不构成投资建议。',
    status: 'done',
  },
]);

const canSend = computed(() => input.value.trim().length > 0 && !sending.value);
const lastAssistant = computed(() => [...messages.value].reverse().find((message) => message.role === 'assistant' && message.id !== 'welcome'));

async function scrollToBottom() {
  await nextTick();
  if (threadEl.value) threadEl.value.scrollTop = threadEl.value.scrollHeight;
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

async function send(text?: string): Promise<void> {
  const query = (text || input.value).trim();
  if (!query || sending.value) return;
  errorMsg.value = null;
  sending.value = true;
  seedTrace(query);
  const userMessage: ChatStreamMessage = { id: `user-${Date.now()}`, role: 'user', content: query, status: 'done' };
  const assistantMessage: ChatStreamMessage = { id: `assistant-${Date.now()}`, role: 'assistant', content: '', status: 'streaming' };
  messages.value = [...messages.value, userMessage, assistantMessage];
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
      onEvent: (event) => appendTrace(event),
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
        messages.value = [...messages.value];
      },
      onError: (message) => {
        assistantMessage.status = 'error';
        errorMsg.value = message;
        appendTrace({
          id: `error-${Date.now()}`,
          type: 'error',
          stage: 'stream_error',
          title: '执行失败',
          message,
          status: 'error',
          timestamp: new Date().toISOString(),
        });
        messages.value = [...messages.value];
      },
    });
  } catch (error) {
    assistantMessage.status = 'error';
    errorMsg.value = error instanceof Error ? error.message : String(error);
    messages.value = [...messages.value];
  } finally {
    sending.value = false;
    await scrollToBottom();
  }
}

function clearChat() {
  messages.value = messages.value.slice(0, 1);
  traceEvents.value = [];
  errorMsg.value = null;
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

onMounted(() => {
  const prefill = String(route.query.prefill || '').trim();
  const symbol = String(route.query.symbol || '').trim().toUpperCase();
  if (symbol) activeSymbol.value = symbol;
  if (prefill) {
    input.value = prefill;
    void send(prefill);
  }
});
</script>

<template>
  <section class="chat-page">
    <header class="page-card chat-hero">
      <div>
        <p class="kicker">RESEARCH COPILOT</p>
        <h2>对话式研究与报告生成</h2>
        <p>输出报告、复查风险、解释证据变化；右侧实时展示执行过程。</p>
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
                <span v-if="item.status === 'streaming'" class="running">生成中</span>
                <span v-if="item.status === 'error'" class="failed">失败</span>
              </div>
              <pre class="bubble-body">{{ item.content || (item.status === 'streaming' ? '正在组织证据...' : '') }}</pre>
              <EvidencePanel
                v-if="item.role === 'assistant' && item.status === 'done' && item.evidence"
                v-bind="item.evidence"
                compact
              />
            </div>
          </article>
        </div>

        <div v-if="messages.length <= 1" class="suggestions">
          <button v-for="item in suggestions" :key="item" @click="send(item)">{{ item }}</button>
        </div>

        <p v-if="errorMsg" class="error-banner">{{ errorMsg }}</p>

        <footer class="composer">
          <textarea
            v-model="input"
            placeholder="问点什么，例如：AAPL 今天相比上次查看有什么变化？"
            @keydown.ctrl.enter.prevent="send()"
            @keydown.meta.enter.prevent="send()"
          />
          <button :disabled="!canSend" @click="send()">{{ sending ? '执行中...' : '发送研究任务' }}</button>
        </footer>
      </main>

      <aside class="side-stack">
        <ExecutionTracePanel :events="traceEvents" :running="sending" />
        <section class="page-card report-card">
          <p class="kicker">LAST OUTPUT</p>
          <h3>{{ lastAssistant?.status === 'done' ? '可导出报告片段' : '等待研究输出' }}</h3>
          <p>{{ lastAssistant?.content?.slice(0, 160) || '生成完成后，这里会显示最新报告摘要。' }}</p>
        </section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.chat-page {
  width: 100%;
  display: grid;
  gap: 18px;
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
.report-card p,
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
  grid-template-columns: minmax(0, 1fr) minmax(340px, 420px);
  gap: 18px;
}

.chat-thread {
  padding: 18px;
  min-height: 660px;
  display: grid;
  grid-template-rows: 1fr auto auto auto;
  gap: 14px;
}

.thread-scroll {
  overflow-y: auto;
  max-height: 62vh;
  display: grid;
  align-content: start;
  gap: 16px;
  padding-right: 4px;
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

.failed,
.error-banner {
  color: var(--fin-danger);
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
  min-height: 92px;
  resize: vertical;
}

.side-stack {
  display: grid;
  align-content: start;
  gap: 18px;
}

.report-card {
  padding: 18px;
}

.error-banner {
  border-radius: 14px;
  padding: 10px 12px;
  background: var(--fin-danger-soft);
}

@media (max-width: 1080px) {
  .chat-hero,
  .chat-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .controls {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .composer {
    grid-template-columns: 1fr;
  }
}
</style>
