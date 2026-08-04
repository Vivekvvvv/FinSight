<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import { useIdentityStore } from '@/stores/identity';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import WhatChangedCard from '@/components/WhatChangedCard.vue';
import EvidenceTimeline from '@/components/EvidenceTimeline.vue';
import KlinePanel from '@/components/KlinePanel.vue';
import LoadingState from '@/components/LoadingState.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import type {
  EvidenceInfo,
  ReportIndexItem,
  ResearchNote,
  ResearchQualityIssue,
  ResearchQualitySummary,
  TimelineEvent,
  WhatChangedItem,
} from '@/api/types';

type LoadState = 'idle' | 'loading' | 'ready' | 'error';
type ConflictReviewItem = {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  reason: string;
  sourceLabel: string;
  targetRoute: string;
};
type QuoteView = {
  name: string;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  volume: number | null;
  marketCap: number | null;
  freshnessStatus: string;
};

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();

const symbolInput = ref(String(route.params.symbol || 'AAPL').toUpperCase());
const loadState = ref<LoadState>('idle');
const errorMsg = ref<string | null>(null);
const quoteLoading = ref(false);
const quoteError = ref<string | null>(null);
let loadSeq = 0;

const whatChanged = ref<WhatChangedItem[]>([]);
const quote = ref<unknown>(null);
const timelineEvents = ref<TimelineEvent[]>([]);
const reports = ref<ReportIndexItem[]>([]);
const notes = ref<ResearchNote[]>([]);
const qualitySummary = ref<ResearchQualitySummary | null>(null);
const qualityIssues = ref<ResearchQualityIssue[]>([]);

const symbol = computed(() => String(route.params.symbol || symbolInput.value || 'AAPL').toUpperCase());
const sessionId = computed(() => identity.sessionId || 'default_session');
const userId = computed(() => identity.userId || 'default_user');

const latestReport = computed(() => reports.value[0] || null);
const latestNote = computed(() => notes.value[0] || null);
const criticalChanges = computed(() => whatChanged.value.filter((item) => ['high', 'critical'].includes(item.severity)).length);
const criticalTimeline = computed(() => timelineEvents.value.filter((item) => ['high', 'critical'].includes(item.severity)).length);
const healthScore = computed(() => qualitySummary.value?.health_score ?? 100);
const quoteView = computed<QuoteView>(() => {
  const payload = quote.value as { ticker?: string; data?: Record<string, unknown> } | null;
  const raw = payload?.data || {};
  const price = raw.currentPrice ?? raw.price;
  const change = raw.regularMarketChange ?? raw.change;
  const changePercent = raw.regularMarketChangePercent ?? raw.change_percent;
  const volume = raw.regularMarketVolume ?? raw.volume;
  const marketCap = raw.marketCap ?? raw.market_cap;
  return {
    name: String(raw.shortName || raw.longName || raw.name || payload?.ticker || symbol.value),
    price: typeof price === 'number' ? price : null,
    change: typeof change === 'number' ? change : null,
    changePercent: typeof changePercent === 'number' ? changePercent : null,
    volume: typeof volume === 'number' ? volume : null,
    marketCap: typeof marketCap === 'number' ? marketCap : null,
    freshnessStatus: String(raw.freshness_status || raw.freshnessStatus || 'unknown'),
  };
});
const dossierEvidence = computed<EvidenceInfo>(() => {
  const source = latestReport.value?.source_type || 'dossier-aggregate';
  const rawFreshness = latestReport.value?.freshness_status || (timelineEvents.value.length ? 'live' : 'unknown');
  const freshnessStatus = (['live', 'delayed_15min', 'cached', 'stale', 'demo', 'fallback', 'unknown'].includes(rawFreshness)
    ? rawFreshness
    : 'unknown') as EvidenceInfo['freshnessStatus'];
  return {
    source,
    asOf: latestReport.value?.as_of || latestReport.value?.generated_at || timelineEvents.value[0]?.occurred_at || null,
    freshnessStatus,
    fallbackLevel: freshnessStatus && freshnessStatus !== 'live' ? 1 : 0,
    degraded: Boolean(freshnessStatus && freshnessStatus !== 'live'),
  };
});
const conflictReviews = computed<ConflictReviewItem[]>(() => {
  const items: ConflictReviewItem[] = [];

  for (const issue of qualityIssues.value) {
    if (issue.issue_type !== 'challenged_conclusion') continue;
    items.push({
      id: `quality:${issue.id}`,
      severity: issue.severity,
      title: issue.title,
      reason: issue.reason,
      sourceLabel: 'Research Quality',
      targetRoute: issue.target_route,
    });
  }

  for (const report of reports.value) {
    if (report.freshness_status && report.freshness_status !== 'live') {
      items.push({
        id: `stale:${report.report_id}`,
        severity: report.freshness_status === 'stale' ? 'high' : 'medium',
        title: `${report.ticker || symbol.value} 旧报告需要刷新`,
        reason: `报告数据状态为 ${report.freshness_status}，新判断前应先刷新证据。`,
        sourceLabel: 'Reports',
        targetRoute: `/reports?highlight=${report.report_id}`,
      });
    }

    if (report.quality_state && ['warn', 'block'].includes(report.quality_state)) {
      items.push({
        id: `quality-state:${report.report_id}`,
        severity: report.quality_state === 'block' ? 'critical' : 'high',
        title: `${report.ticker || symbol.value} 报告质量需要复查`,
        reason: `质量状态为 ${report.quality_state}，结论使用前应复核引用和假设。`,
        sourceLabel: 'Reports',
        targetRoute: `/reports?highlight=${report.report_id}`,
      });
    }
  }

  for (const event of timelineEvents.value) {
    if (!['high', 'critical'].includes(event.severity)) continue;
    const eventTime = new Date(event.occurred_at).getTime();
    const olderReport = reports.value.find((report) => {
      const reportTime = new Date(report.generated_at || '').getTime();
      return Number.isFinite(reportTime) && Number.isFinite(eventTime) && reportTime < eventTime;
    });
    if (!olderReport) continue;
    items.push({
      id: `timeline:${event.id}`,
      severity: event.severity,
      title: `${symbol.value} 新证据可能挑战旧结论`,
      reason: `${fmtDate(event.occurred_at)} 出现 ${severityLabel(event.severity)} 事件「${event.title}」，晚于报告「${olderReport.title || olderReport.report_id}」。`,
      sourceLabel: 'Evidence Timeline',
      targetRoute: event.target_route || `/timeline/${symbol.value}`,
    });
  }

  const order = { critical: 0, high: 1, medium: 2, low: 3 };
  const unique = new Map<string, ConflictReviewItem>();
  for (const item of items) {
    const key = `${item.title}:${item.targetRoute}`;
    const existing = unique.get(key);
    if (!existing || order[item.severity] < order[existing.severity]) {
      unique.set(key, item);
    }
  }
  return [...unique.values()].sort((a, b) => order[a.severity] - order[b.severity]).slice(0, 5);
});

function fmtDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function compactNumber(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  if (Math.abs(value) >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}T`;
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function severityLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低',
  };
  return value ? labels[value] || value : '-';
}

function routeTo(path: string): void {
  if (path.startsWith('/dashboard/')) {
    void router.push(path.replace('/dashboard/', '/dossier/'));
    return;
  }
  if (path.startsWith('/timeline/')) {
    void router.push(path.replace('/timeline/', '/dossier/'));
    return;
  }
  void router.push(path);
}

function submitSymbol(): void {
  const next = symbolInput.value.trim().toUpperCase();
  if (!next) return;
  void router.push(`/dossier/${encodeURIComponent(next)}`);
}

async function loadDossier(): Promise<void> {
  if (!symbol.value) return;
  const currentSeq = ++loadSeq;
  const currentSymbol = symbol.value;
  loadState.value = 'loading';
  errorMsg.value = null;
  quote.value = null;
  quoteError.value = null;
  quoteLoading.value = true;

  void apiClient.getQuote(currentSymbol)
    .then((value) => {
      if (currentSeq === loadSeq) quote.value = value;
    })
    .catch(() => {
      if (currentSeq === loadSeq) quoteError.value = 'Quote source is slow. Other dossier data is shown first.';
    })
    .finally(() => {
      if (currentSeq === loadSeq) quoteLoading.value = false;
    });

  const [changes, timeline, reportList, noteList, quality] = await Promise.allSettled([
    apiClient.getWhatChanged({ sessionId: sessionId.value, userId: userId.value, symbol: currentSymbol, limit: 5 }),
    apiClient.getTimeline({ symbol: currentSymbol, sessionId: sessionId.value, userId: userId.value, limit: 8 }),
    apiClient.listReports({ sessionId: sessionId.value, ticker: currentSymbol, sortBy: 'generated_at_desc', limit: 5 }),
    apiClient.listNotes(sessionId.value, userId.value, currentSymbol, undefined, 5),
    apiClient.getResearchQuality({ sessionId: sessionId.value, userId: userId.value, symbol: currentSymbol }),
  ]);

  if (currentSeq !== loadSeq) return;

  if (changes.status === 'fulfilled') whatChanged.value = changes.value.items || [];
  else whatChanged.value = [];

  if (timeline.status === 'fulfilled') timelineEvents.value = timeline.value.events || [];
  else timelineEvents.value = [];

  if (reportList.status === 'fulfilled') reports.value = reportList.value.items || [];
  else reports.value = [];

  if (noteList.status === 'fulfilled') notes.value = noteList.value.notes || [];
  else notes.value = [];

  if (quality.status === 'fulfilled') {
    qualitySummary.value = quality.value.summary;
    qualityIssues.value = quality.value.top_issues || [];
  } else {
    qualitySummary.value = null;
    qualityIssues.value = [];
  }

  const failed = [changes, timeline, reportList, noteList, quality].filter((item) => item.status === 'rejected').length;
  errorMsg.value = failed ? `${failed} 个数据模块暂时不可用，已展示其余研究材料。` : null;
  loadState.value = 'ready';
}

onMounted(() => {
  void loadDossier();
});

watch(() => route.params.symbol, () => {
  symbolInput.value = symbol.value;
  void loadDossier();
});
</script>

<template>
  <section class="dossier-page">
    <header class="dossier-hero">
      <div>
        <p class="eyebrow">
          Symbol Research Dossier
        </p>
        <h1>{{ symbol }} 标的研究档案</h1>
        <p class="subtitle">
          把今日变化、证据时间线、研究报告、笔记和研究质量收束到一个复查视图。这里只给研究动作建议，不构成投资建议。
        </p>
      </div>
      <DataSourceBadge
        class="dossier-source"
        :evidence="dossierEvidence"
      />
      <form
        class="symbol-search"
        @submit.prevent="submitSymbol"
      >
        <input
          v-model="symbolInput"
          aria-label="输入股票代码"
          placeholder="AAPL / NVDA / MSFT"
        >
        <button type="submit">
          打开档案
        </button>
      </form>
    </header>

    <StatusBanner
      v-if="errorMsg"
      variant="warning"
      :message="errorMsg"
    />

    <section class="metric-grid">
      <article class="metric-card market-metric">
        <span>行情概览</span>
        <strong>{{ quoteView.price == null ? '--' : quoteView.price.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }}</strong>
        <em :class="Number(quoteView.changePercent || 0) >= 0 ? 'gain-text' : 'loss-text'">
          {{ quoteView.name }} · {{ quoteView.changePercent == null ? '涨跌幅 --' : `${quoteView.changePercent >= 0 ? '+' : ''}${quoteView.changePercent.toFixed(2)}%` }}
        </em>
      </article>
      <article class="metric-card">
        <span>重要变化</span>
        <strong>{{ whatChanged.length }}</strong>
        <em>{{ criticalChanges }} 条高优先级</em>
      </article>
      <article class="metric-card">
        <span>证据事件</span>
        <strong>{{ timelineEvents.length }}</strong>
        <em>{{ criticalTimeline }} 条高风险事件</em>
      </article>
      <article class="metric-card">
        <span>报告资产</span>
        <strong>{{ reports.length }}</strong>
        <em>{{ latestReport ? fmtDate(latestReport.generated_at) : '暂无报告' }}</em>
      </article>
      <article class="metric-card">
        <span>研究健康度</span>
        <strong>{{ healthScore }}</strong>
        <em>{{ qualityIssues.length }} 个复查点</em>
      </article>
      <article class="metric-card">
        <span>结论冲突</span>
        <strong>{{ conflictReviews.length }}</strong>
        <em>需人工复查</em>
      </article>
    </section>

    <section class="action-strip">
      <button
        type="button"
        @click="routeTo(`/dossier/${symbol}`)"
      >
        行情与证据
      </button>
      <button
        type="button"
        @click="routeTo(`/reports?ticker=${symbol}`)"
      >
        相关报告
      </button>
      <button
        type="button"
        @click="routeTo(`/notes?ticker=${symbol}`)"
      >
        研究笔记
      </button>
      <button
        type="button"
        @click="routeTo(`/chat?symbol=${symbol}&mode=qa`)"
      >
        打开问答
      </button>
    </section>

    <section
      class="panel market-panel"
      data-testid="market-overview"
    >
      <div class="panel-head">
        <div>
          <p class="eyebrow">
            Market
          </p>
          <h2>行情概览</h2>
        </div>
        <span class="freshness-pill">{{ quoteLoading ? 'loading' : quoteView.freshnessStatus }}</span>
      </div>
      <p
        v-if="quoteLoading || quoteError"
        class="market-hint"
      >
        {{ quoteLoading ? 'Quote loading in background. Research data is available first.' : quoteError }}
      </p>
      <div class="market-grid">
        <article>
          <span>最新价</span>
          <strong>{{ quoteView.price == null ? '--' : quoteView.price.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }}</strong>
        </article>
        <article>
          <span>涨跌额</span>
          <strong :class="Number(quoteView.change || 0) >= 0 ? 'gain-text' : 'loss-text'">
            {{ quoteView.change == null ? '--' : `${quoteView.change >= 0 ? '+' : ''}${quoteView.change.toFixed(2)}` }}
          </strong>
        </article>
        <article>
          <span>成交量</span>
          <strong>{{ compactNumber(quoteView.volume) }}</strong>
        </article>
        <article>
          <span>市值</span>
          <strong>{{ compactNumber(quoteView.marketCap) }}</strong>
        </article>
      </div>
    </section>

    <KlinePanel :symbol="symbol" />

    <LoadingState
      v-if="loadState === 'loading'"
      :label="`正在汇总 ${symbol} 的研究档案...`"
    />

    <div
      v-else
      class="dossier-grid"
    >
      <section class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="eyebrow">
              What Changed
            </p>
            <h2>优先复查变化</h2>
          </div>
          <button
            type="button"
            @click="loadDossier"
          >
            刷新
          </button>
        </div>
        <div
          v-if="whatChanged.length"
          class="changes-grid"
        >
          <WhatChangedCard
            v-for="item in whatChanged"
            :key="item.id"
            :item="item"
          />
        </div>
        <div
          v-else
          class="empty-state"
        >
          暂无需要优先复查的变化。
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">
              Conflict Review
            </p>
            <h2>证据冲突与旧结论复查</h2>
          </div>
        </div>
        <div
          v-if="conflictReviews.length"
          class="conflict-list"
        >
          <button
            v-for="item in conflictReviews"
            :key="item.id"
            class="conflict-card"
            type="button"
            @click="routeTo(item.targetRoute)"
          >
            <span :class="['severity-dot', item.severity]" />
            <div>
              <strong>{{ item.title }}</strong>
              <p>{{ item.reason }}</p>
              <em>{{ item.sourceLabel }} · {{ severityLabel(item.severity) }}</em>
            </div>
          </button>
        </div>
        <div
          v-else
          class="empty-state"
        >
          暂未发现新证据挑战旧结论。继续观察，不输出买卖建议。
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">
              Research Quality
            </p>
            <h2>质量复查</h2>
          </div>
        </div>
        <div
          v-if="qualityIssues.length"
          class="issue-list"
        >
          <button
            v-for="issue in qualityIssues.slice(0, 5)"
            :key="issue.id"
            class="issue-card"
            type="button"
            @click="routeTo(issue.target_route)"
          >
            <span :class="['severity-dot', issue.severity]" />
            <strong>{{ issue.title }}</strong>
            <em>{{ severityLabel(issue.severity) }} · {{ issue.reason }}</em>
          </button>
        </div>
        <div
          v-else
          class="empty-state"
        >
          暂无质量阻断项。
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <p class="eyebrow">
              Latest Assets
            </p>
            <h2>最新报告与笔记</h2>
          </div>
        </div>
        <article
          v-if="latestReport"
          class="asset-card"
          @click="routeTo(`/reports?highlight=${latestReport.report_id}`)"
        >
          <span>报告</span>
          <strong>{{ latestReport.title || `${symbol} 研究报告` }}</strong>
          <em>{{ fmtDate(latestReport.generated_at) }} · 置信度 {{ latestReport.confidence_score ?? '-' }}</em>
        </article>
        <article
          v-if="latestNote"
          class="asset-card"
          @click="routeTo(`/notes?ticker=${symbol}`)"
        >
          <span>笔记</span>
          <strong>{{ latestNote.title }}</strong>
          <em>{{ fmtDate(latestNote.updated_at) }} · {{ latestNote.tags.join(', ') || '未标记' }}</em>
        </article>
        <div
          v-if="!latestReport && !latestNote"
          class="empty-state"
        >
          还没有沉淀报告或笔记。
        </div>
      </section>

      <section class="panel panel-wide">
        <div class="panel-head">
          <div>
            <p class="eyebrow">
              Evidence Timeline
            </p>
            <h2>最近证据事件</h2>
          </div>
        </div>
        <EvidenceTimeline
          :events="timelineEvents"
          :loading="false"
        />
      </section>
    </div>
  </section>
</template>

<style scoped>
.dossier-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dossier-hero,
.panel,
.metric-card,
.loading-card,
.status-banner {
  border: 1px solid var(--fin-border);
  background: var(--fin-surface);
  box-shadow: var(--fin-shadow);
}

.dossier-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  padding: 34px;
  border-radius: 30px;
  background:
    radial-gradient(circle at 12% 0%, var(--fin-primary-soft), transparent 34%),
    linear-gradient(135deg, var(--fin-surface), var(--fin-surface-2));
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
  color: var(--fin-text);
}

h1 {
  font-size: clamp(34px, 4vw, 58px);
  letter-spacing: -0.04em;
}

h2 {
  font-size: 22px;
}

.subtitle {
  max-width: 760px;
  margin: 12px 0 0;
  color: var(--fin-muted);
  font-size: 16px;
  line-height: 1.8;
}

.symbol-search {
  min-width: 330px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}

.symbol-search input {
  min-width: 0;
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  padding: 14px 16px;
  background: var(--fin-surface-2);
  color: var(--fin-text);
  font-size: 16px;
  font-weight: 800;
  text-transform: uppercase;
}

.symbol-search button,
.action-strip button,
.panel-head button {
  border: 0;
  border-radius: 16px;
  padding: 13px 18px;
  background: var(--fin-primary);
  color: var(--fin-primary-contrast);
  font-weight: 900;
  cursor: pointer;
}

.status-banner {
  padding: 14px 18px;
  border-radius: 18px;
  color: var(--fin-warning);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.metric-card {
  border-radius: 22px;
  padding: 20px;
}

.metric-card span,
.asset-card span {
  display: block;
  color: var(--fin-muted);
  font-size: 13px;
  font-weight: 800;
}

.metric-card strong {
  display: block;
  margin-top: 10px;
  color: var(--fin-text);
  font-size: 34px;
  line-height: 1;
}

.metric-card em,
.asset-card em,
.issue-card em {
  display: block;
  margin-top: 8px;
  color: var(--fin-muted);
  font-size: 13px;
  font-style: normal;
}

.gain-text {
  color: var(--fin-success) !important;
}

.loss-text {
  color: var(--fin-danger) !important;
}

.action-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.action-strip button {
  background: var(--fin-surface-2);
  color: var(--fin-text);
  border: 1px solid var(--fin-border);
}

.market-panel {
  display: grid;
  gap: 14px;
}

.freshness-pill {
  border-radius: 999px;
  padding: 5px 10px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-size: 12px;
  font-weight: 900;
  text-transform: uppercase;
}

.market-hint {
  margin: 0;
  color: var(--fin-muted);
  font-size: 13px;
  line-height: 1.5;
}

.market-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.market-grid article {
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  padding: 14px;
  background: var(--fin-surface-2);
}

.market-grid span {
  display: block;
  color: var(--fin-muted);
  font-size: 12px;
  font-weight: 800;
}

.market-grid strong {
  display: block;
  margin-top: 6px;
  color: var(--fin-text);
  font-size: 20px;
}

.dossier-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.7fr);
  gap: 18px;
}

.panel {
  min-width: 0;
  border-radius: 26px;
  padding: 22px;
}

.panel-wide {
  grid-column: span 1;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.changes-grid,
.issue-list,
.conflict-list {
  display: grid;
  gap: 12px;
}

.issue-card,
.conflict-card,
.asset-card {
  width: 100%;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  padding: 16px;
  background: var(--fin-surface-2);
  color: var(--fin-text);
  text-align: left;
  cursor: pointer;
}

.issue-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 10px;
}

.conflict-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
}

.conflict-card p {
  margin: 6px 0 0;
  color: var(--fin-muted);
  font-size: 14px;
  line-height: 1.6;
}

.issue-card em {
  grid-column: 2;
}

.severity-dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--fin-muted);
}

.severity-dot.critical,
.severity-dot.high {
  background: var(--fin-danger);
}

.severity-dot.medium {
  background: var(--fin-warning);
}

.severity-dot.low {
  background: var(--fin-success);
}

.asset-card + .asset-card {
  margin-top: 12px;
}

.empty-state,
.loading-card {
  padding: 28px;
  border-radius: 20px;
  color: var(--fin-muted);
  text-align: center;
}

@media (max-width: 1100px) {
  .dossier-hero,
  .dossier-grid {
    grid-template-columns: 1fr;
  }

  .dossier-hero {
    display: grid;
    align-items: stretch;
  }

  .metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .market-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .symbol-search {
    min-width: 0;
  }
}

@media (max-width: 640px) {
  .metric-grid {
    grid-template-columns: 1fr;
  }

  .market-grid {
    grid-template-columns: 1fr;
  }

  .symbol-search {
    grid-template-columns: 1fr;
  }
}
</style>
