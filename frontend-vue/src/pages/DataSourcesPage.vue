<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import type { DemoStatusResponse, EvidenceInfo } from '@/api/types';

const status = ref<DemoStatusResponse | null>(null);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

const overallEvidence = computed<EvidenceInfo>(() => {
  const overall = status.value?.overall_status || 'unknown';
  return {
    source: status.value?.data_source || 'data-source-status',
    asOf: status.value?.as_of || null,
    freshnessStatus: overall === 'demo' ? 'demo' : overall === 'live_ready' ? 'live' : overall === 'fallback_ready' ? 'fallback' : 'unknown',
    fallbackLevel: overall === 'live_ready' ? 0 : overall === 'demo' ? 2 : 1,
    degraded: overall !== 'live_ready',
  };
});

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    demo: 'Demo',
    live_ready: 'Live',
    fallback_ready: 'Fallback',
    missing_key: '缺少配置',
    needs_config: '需要配置',
  };
  return labels[value] || value;
}

async function refresh() {
  loading.value = true;
  errorMsg.value = null;
  try {
    status.value = await apiClient.getDataSourceStatus();
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <section class="data-sources-page">
    <header class="hero page-card">
      <div>
        <p class="kicker">SOURCE CONTROL</p>
        <h2>数据源状态</h2>
        <p>查看美股、A 股、港股、LLM、RAG 与访问控制当前是 Live、Fallback、Demo 还是缺少配置。</p>
        <DataSourceBadge class="overall-badge" :evidence="overallEvidence" />
      </div>
      <button class="primary" :disabled="loading" @click="refresh">
        {{ loading ? '检测中...' : '重新检测' }}
      </button>
    </header>

    <p v-if="errorMsg" class="notice danger">{{ errorMsg }}</p>

    <section class="source-grid">
      <article
        v-for="item in status?.components || []"
        :key="item.key"
        class="source-card page-card"
        :class="item.status"
      >
        <div class="source-head">
          <div>
            <p class="kicker">{{ item.key }}</p>
            <h3>{{ item.label }}</h3>
          </div>
          <span>{{ statusLabel(item.status) }}</span>
        </div>
        <p>{{ item.detail }}</p>
        <strong v-if="item.required_action">{{ item.required_action }}</strong>
      </article>
    </section>

    <section class="page-card note-card">
      <p class="kicker">NOTES</p>
      <ul>
        <li v-for="note in status?.notes || []" :key="note">{{ note }}</li>
      </ul>
      <p v-if="status?.missing_services?.length">
        缺失配置：{{ status.missing_services.join(' / ') }}
      </p>
      <p class="fine-print">FinSight 只提供研究复查建议，不提供买入、卖出、持有或收益承诺。</p>
    </section>
  </section>
</template>

<style scoped>
.data-sources-page {
  display: grid;
  gap: 18px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: clamp(24px, 2.6vw, 38px);
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 38%),
    radial-gradient(circle at 90% 12%, var(--fin-accent-soft), transparent 30%),
    var(--fin-card);
}

.hero h2 {
  margin: 0;
  font-size: clamp(34px, 4vw, 58px);
  letter-spacing: -0.06em;
}

.hero p:not(.kicker),
.source-card p,
.note-card,
.fine-print {
  color: var(--fin-text-2);
}

.overall-badge {
  margin-top: 12px;
}

.primary {
  align-self: center;
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.source-card {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.source-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.source-head h3 {
  margin: 0;
}

.source-head span {
  border-radius: 999px;
  padding: 5px 10px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  font-size: 12px;
  font-weight: 900;
}

.source-card.live_ready .source-head span {
  background: var(--fin-success-soft);
  color: var(--fin-success);
}

.source-card.fallback_ready .source-head span,
.source-card.missing_key .source-head span {
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.source-card.demo .source-head span {
  background: var(--fin-info-soft);
  color: var(--fin-info);
}

.source-card strong {
  color: var(--fin-warning);
}

.note-card {
  padding: 20px;
}

.note-card ul {
  margin: 0;
  padding-left: 18px;
}

.notice {
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  padding: 12px 14px;
}

.notice.danger {
  color: var(--fin-danger);
  background: var(--fin-danger-soft);
}

@media (max-width: 1100px) {
  .source-grid {
    grid-template-columns: 1fr;
  }
}
</style>
