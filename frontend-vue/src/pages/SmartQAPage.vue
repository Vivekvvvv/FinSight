<script setup lang="ts">
import { ref } from 'vue';
import { http } from '@/api/client';
import { marked } from 'marked';

interface QAResult {
  question: string;
  ticker?: string;
  answer: string;
  context_used: string[];
}

const question = ref('');
const ticker = ref('');
const useCnData = ref(true);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const result = ref<QAResult | null>(null);
const history = ref<QAResult[]>([]);

const examples = [
  { q: '为什么贵州茅台今天下跌？', t: '600519.SS' },
  { q: '北向资金今日流向如何？对A股有什么影响？', t: '' },
  { q: '融资余额变化说明了什么？', t: '600519.SS' },
  { q: '龙虎榜上的机构席位有什么意义？', t: '' },
];

async function ask(): Promise<void> {
  if (!question.value.trim()) return;
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await http.post('/api/research/qa', {
      question: question.value.trim(),
      ticker: ticker.value.trim().toUpperCase() || null,
      use_cn_data: useCnData.value,
    });
    result.value = resp.data;
    history.value.unshift(resp.data);
    if (history.value.length > 10) history.value.pop();
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '问答失败';
  } finally {
    loading.value = false;
  }
}

function useExample(ex: { q: string; t: string }): void {
  question.value = ex.q;
  ticker.value = ex.t;
}

function renderMd(text: string): string {
  return marked(text) as string;
}
</script>

<template>
  <div class="smart-qa-page">
    <header class="page-header">
      <h2>智能股票问答</h2>
      <p class="muted">基于实时行情、新闻、龙虎榜、北向资金多维数据的AI问答</p>
    </header>

    <section class="qa-form">
      <div class="question-row">
        <textarea
          v-model="question"
          placeholder="请输入您的问题，例如：为什么贵州茅台今天大跌？"
          :disabled="loading"
          rows="3"
          @keydown.ctrl.enter.prevent="ask"
        />
        <button class="btn-ask" :disabled="loading || !question.trim()" @click="ask">
          {{ loading ? '思考中...' : '提问' }}
        </button>
      </div>

      <div class="options-row">
        <div class="input-group-inline">
          <label>关联股票（选填）</label>
          <input v-model="ticker" type="text" placeholder="600519.SS" :disabled="loading" />
        </div>
        <label class="toggle-label">
          <input v-model="useCnData" type="checkbox" :disabled="loading" />
          注入A股数据（龙虎榜/北向/融资）
        </label>
        <span class="hint">Ctrl+Enter 提交</span>
      </div>

      <div class="examples">
        <span class="examples-label">示例问题：</span>
        <button
          v-for="ex in examples"
          :key="ex.q"
          class="example-chip"
          @click="useExample(ex)"
        >
          {{ ex.q }}
        </button>
      </div>
    </section>

    <section v-if="loading" class="loading-state">
      <div class="thinking-dots">
        <span />
        <span />
        <span />
      </div>
      <p>正在收集市场数据并分析...</p>
    </section>

    <section v-if="errorMsg" class="error-banner">{{ errorMsg }}</section>

    <section v-if="result && !loading" class="answer-card">
      <header class="answer-header">
        <p class="question-text">Q: {{ result.question }}</p>
        <div v-if="result.context_used?.length" class="context-tags">
          <span v-for="c in result.context_used" :key="c" class="context-tag">{{ c }}</span>
        </div>
      </header>
      <div class="answer-body markdown-body" v-html="renderMd(result.answer)" />
    </section>

    <section v-if="history.length > 1" class="history-section">
      <h3>历史问答</h3>
      <details
        v-for="(h, i) in history.slice(1)"
        :key="i"
        class="history-item"
      >
        <summary>{{ h.question }}</summary>
        <div class="history-answer markdown-body" v-html="renderMd(h.answer)" />
      </details>
    </section>
  </div>
</template>

<style scoped>
.smart-qa-page {
  max-width: 900px;
  margin: 0 auto;
  display: grid;
  gap: 24px;
}
.page-header h2 { margin: 0; font-size: 28px; }
.page-header .muted { margin: 6px 0 0; color: var(--fin-muted); font-size: 14px; }

.qa-form {
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  display: grid;
  gap: 14px;
}
.question-row { display: flex; gap: 12px; align-items: flex-end; }
.question-row textarea {
  flex: 1;
  padding: 12px 14px;
  border: 1px solid var(--fin-border);
  border-radius: 14px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 15px;
  resize: vertical;
  font-family: inherit;
}
.btn-ask {
  padding: 12px 24px;
  border: 0;
  border-radius: 14px;
  background: var(--fin-primary);
  color: white;
  font-weight: 700;
  font-size: 15px;
  cursor: pointer;
  white-space: nowrap;
}
.btn-ask:disabled { opacity: 0.5; cursor: not-allowed; }

.options-row {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}
.input-group-inline {
  display: flex;
  align-items: center;
  gap: 8px;
}
.input-group-inline label { font-size: 13px; color: var(--fin-muted); white-space: nowrap; }
.input-group-inline input {
  padding: 6px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
  width: 130px;
}
.toggle-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--fin-text-2);
  cursor: pointer;
}
.hint { font-size: 12px; color: var(--fin-muted); margin-left: auto; }

.examples { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.examples-label { font-size: 12px; color: var(--fin-muted); white-space: nowrap; }
.example-chip {
  padding: 5px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card);
  color: var(--fin-text-2);
  font-size: 12px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.example-chip:hover { border-color: var(--fin-primary); color: var(--fin-primary); }

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 40px;
  color: var(--fin-muted);
}
.thinking-dots { display: flex; gap: 6px; }
.thinking-dots span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fin-primary);
  animation: bounce 1.2s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1.2); opacity: 1; }
}

.error-banner {
  padding: 16px;
  border: 1px solid var(--fin-error);
  border-radius: 12px;
  background: color-mix(in srgb, var(--fin-error) 10%, transparent);
  color: var(--fin-error);
}

.answer-card {
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  overflow: hidden;
}
.answer-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--fin-border);
  background: var(--fin-card);
  display: grid;
  gap: 10px;
}
.question-text {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--fin-text);
}
.context-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.context-tag {
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--fin-primary) 15%, transparent);
  color: var(--fin-primary);
  font-size: 11px;
  font-weight: 600;
}
.answer-body { padding: 20px 24px; line-height: 1.8; }

.history-section { display: grid; gap: 10px; }
.history-section h3 { margin: 0; font-size: 16px; color: var(--fin-text-2); }
.history-item {
  border: 1px solid var(--fin-border);
  border-radius: 14px;
  background: var(--fin-card-soft);
  overflow: hidden;
}
.history-item summary {
  padding: 14px 16px;
  cursor: pointer;
  font-size: 14px;
  color: var(--fin-text-2);
}
.history-answer { padding: 12px 20px 16px; }

.markdown-body { font-size: 14px; color: var(--fin-text); }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) {
  margin: 16px 0 8px;
  color: var(--fin-text);
}
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 20px; margin: 8px 0; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(strong) { color: var(--fin-text); }
.markdown-body :deep(code) {
  padding: 1px 5px;
  background: var(--fin-card-inset);
  border-radius: 4px;
  font-family: var(--fin-mono);
  font-size: 12px;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--fin-muted);
  padding-left: 12px;
  margin: 8px 0;
  color: var(--fin-muted);
  font-style: italic;
}
</style>
