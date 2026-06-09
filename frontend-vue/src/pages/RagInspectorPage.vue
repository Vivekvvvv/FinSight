<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import type { RagRunSummary, RagStatusResponse } from '@/api/types';

const loading = ref(false);
const errorMsg = ref<string | null>(null);
const status = ref<RagStatusResponse['data'] | null>(null);
const runs = ref<RagRunSummary[]>([]);
const query = ref('');
const fallbackOnly = ref(false);

async function refresh(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [statusResp, runsResp] = await Promise.all([
      apiClient.getRagStatus(),
      apiClient.listRagRuns({ q: query.value.trim() || undefined, fallbackOnly: fallbackOnly.value, limit: 20 }),
    ]);
    status.value = statusResp.data || null;
    runs.value = runsResp.data?.items || [];
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <section class="page">
    <div class="hero">
      <div>
        <h1 class="page-title">
          RAG Inspector
        </h1>
        <p class="page-sub">
          直连 Python FastAPI 的只读诊断视图。该页默认有 plan gate。
        </p>
      </div>
      <div class="filters">
        <input
          v-model="query"
          class="input"
          placeholder="过滤 query"
          @keyup.enter="refresh"
        >
        <label class="toggle"><input
          v-model="fallbackOnly"
          type="checkbox"
        > 仅 fallback</label>
        <button
          class="btn"
          :disabled="loading"
          @click="refresh"
        >
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>
    </div>

    <div
      v-if="errorMsg"
      class="error"
    >
      {{ errorMsg }}
    </div>

    <article class="panel">
      <div class="panel-title">
        状态摘要
      </div>
      <div
        v-if="!status"
        class="empty"
      >
        暂无状态数据
      </div>
      <div
        v-else
        class="summary"
      >
        <div
          v-for="[key, value] in Object.entries(status)"
          :key="key"
          class="summary-row"
        >
          <span>{{ key }}</span>
          <strong>{{ typeof value === 'object' ? JSON.stringify(value) : value }}</strong>
        </div>
      </div>
    </article>

    <article class="panel">
      <div class="panel-title">
        最近查询
      </div>
      <div
        v-if="runs.length === 0"
        class="empty"
      >
        暂无运行记录
      </div>
      <div
        v-for="(run, index) in runs"
        :key="run.id || index"
        class="run"
      >
        <div class="run-title">
          {{ run.query_text || run.id || `run-${index + 1}` }}
        </div>
        <div class="run-meta">
          {{ run.status || 'unknown' }}
          <span v-if="run.collection"> · {{ run.collection }}</span>
          <span v-if="run.started_at"> · {{ run.started_at }}</span>
          <span v-if="run.fallback_used"> · fallback</span>
        </div>
      </div>
    </article>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: linear-gradient(135deg, #fffaf5 0%, #fff3ec 100%);
}
.page-title { margin: 0; font-size: 28px; font-weight: 700; }
.page-sub { margin: 8px 0 0; color: var(--fin-muted); font-size: 13px; }
.filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.input {
  min-width: 180px;
  padding: 10px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
}
.toggle { font-size: 12px; color: var(--fin-muted); display: inline-flex; align-items: center; gap: 4px; }
.btn {
  padding: 10px 16px;
  border: none;
  border-radius: 12px;
  background: var(--fin-primary);
  color: #fff;
  font-weight: 700;
  cursor: pointer;
}
.panel {
  padding: 16px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card);
}
.panel-title { font-size: 14px; font-weight: 700; margin-bottom: 12px; }
.summary-row,
.run {
  padding: 12px;
  border-radius: 14px;
  background: #fffaf5;
  border: 1px solid var(--fin-border);
  margin-bottom: 10px;
}
.summary-row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; }
.run-title { font-size: 13px; font-weight: 700; color: var(--fin-text); }
.run-meta { margin-top: 4px; font-size: 12px; color: var(--fin-muted); }
.error, .empty {
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 13px;
}
.error { background: #fff1ea; color: var(--fin-danger); border: 1px solid #f2c9b3; }
.empty { background: #fbf7f1; color: var(--fin-muted); border: 1px dashed var(--fin-border); }
@media (max-width: 900px) {
  .hero { flex-direction: column; }
}
</style>
