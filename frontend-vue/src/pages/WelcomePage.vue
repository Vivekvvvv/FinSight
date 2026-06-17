<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { DailyTask, EvidenceInfo, ResearchQualityIssue, ResearchQualitySummary, TodayWorkspaceResponse, WhatChangedItem } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import WhatChangedCard from '@/components/WhatChangedCard.vue';
import ResearchQualityOverview from '@/components/ResearchQualityOverview.vue';

const identity = useIdentityStore();
const router = useRouter();

const workspace = ref<TodayWorkspaceResponse | null>(null);
const dailyTasks = ref<DailyTask[]>([]);
const whatChanged = ref<WhatChangedItem[]>([]);
const qualitySummary = ref<ResearchQualitySummary>({
  total_reports: 0,
  stale_reports: 0,
  low_quality_reports: 0,
  blocked_reports: 0,
  warn_reports: 0,
  watch_reports: 0,
  reviewed_rate: 0,
  challenged_conclusions: 0,
  health_score: 100,
});
const qualityIssues = ref<ResearchQualityIssue[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

const todayStr = computed(() => new Date().toLocaleDateString('zh-CN', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  weekday: 'long',
}));

const userName = computed(() => identity.email ? identity.email.split('@')[0] : '研究员');

const workspaceEvidence = computed<EvidenceInfo>(() => {
  const rawFreshness = workspace.value?.freshness_status || 'unknown';
  const freshnessStatus = (['live', 'delayed_15min', 'cached', 'stale', 'demo', 'fallback', 'unknown'].includes(rawFreshness)
    ? rawFreshness
    : 'unknown') as EvidenceInfo['freshnessStatus'];
  return {
    source: 'today-workspace',
    asOf: workspace.value?.as_of || null,
    freshnessStatus,
    fallbackLevel: freshnessStatus === 'live' ? 0 : freshnessStatus === 'unknown' ? null : 1,
    degraded: freshnessStatus !== 'live',
  };
});

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function fmtDate(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function riskPercent(position: { unrealized_pnl?: number | null; cost_basis?: number | null }): string {
  if (!position.unrealized_pnl || !position.cost_basis) return '--';
  return `${((position.unrealized_pnl / position.cost_basis) * 100).toFixed(2)}%`;
}

const severityIcons: Record<string, string> = {
  critical: 'CR',
  high: 'HI',
  medium: 'MD',
  low: 'LO',
};

function integratedRoute(path?: string | null): string {
  if (!path) return '/welcome';
  if (path.startsWith('/dashboard/')) return path.replace('/dashboard/', '/dossier/');
  if (path === '/dashboard') return '/dossier/AAPL';
  if (path.startsWith('/timeline/')) return path.replace('/timeline/', '/dossier/');
  if (path === '/watchlist') return '/stocks?tab=watchlist';
  if (path === '/alerts') return '/welcome';
  if (path === '/backtest') return '/portfolio?tool=backtest';
  if (path === '/portfolio/optimize') return '/portfolio?tool=optimize';
  if (path === '/portfolio/risk-lens') return '/portfolio?tool=risk';
  if (path.startsWith('/research/qa')) return '/chat?mode=qa';
  if (path.startsWith('/research/report')) return '/reports?tool=generate';
  if (path.startsWith('/research/financials')) return '/reports?tool=financials';
  return path;
}

async function refresh(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [workspaceData, changesData, qualityData, taskData] = await Promise.all([
      apiClient.getTodayWorkspace(identity.sessionId, identity.userId),
      apiClient.getWhatChanged({ sessionId: identity.sessionId, userId: identity.userId, limit: 5 }),
      apiClient.getResearchQuality({ sessionId: identity.sessionId, userId: identity.userId }),
      apiClient.getDailyTasks(identity.sessionId).catch(() => ({ success: false, session_id: identity.sessionId, tasks: [], count: 0 })),
    ]);
    workspace.value = workspaceData;
    whatChanged.value = changesData.items;
    qualitySummary.value = qualityData.summary;
    qualityIssues.value = qualityData.top_issues;
    dailyTasks.value = taskData.tasks || [];
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
watch(() => identity.sessionId, () => { void refresh(); });
</script>

<template>
  <section class="page">
    <div class="today-hero page-card">
      <div class="hero-copy">
        <p class="kicker">TODAY COMMAND CENTER</p>
        <h2>你好，{{ userName }}</h2>
        <p class="today-date">{{ todayStr }}</p>
        <p v-if="workspace" class="today-summary">{{ workspace.summary }}</p>
      </div>
      <div class="hero-actions">
        <DataSourceBadge :evidence="workspaceEvidence" compact />
        <span class="live-dot">LIVE</span>
        <button class="btn-refresh" :disabled="loading" @click="refresh">
          {{ loading ? '加载中...' : '刷新数据' }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <div v-if="loading && !workspace" class="loading-state">
      <div class="spinner"></div>
      <div>正在加载今日工作台...</div>
    </div>

    <template v-else-if="workspace">
      <div class="panel task-panel" data-testid="daily-tasks-panel">
        <div class="panel-header">
          <div>
            <p class="kicker">TODAY TASKS</p>
            <h2 class="panel-title">今日任务</h2>
          </div>
          <span class="panel-count">{{ dailyTasks.length }}</span>
        </div>
        <div v-if="dailyTasks.length === 0" class="panel-empty">暂无任务。添加持仓或候选标的后，系统会生成研究复查动作。</div>
        <div v-else class="tasks-grid">
          <button
            v-for="task in dailyTasks.slice(0, 6)"
            :key="task.id"
            class="task-card"
            type="button"
            @click="router.push(integratedRoute(task.action_url))"
          >
            <span>{{ task.category || '研究' }}</span>
            <strong>{{ task.title }}</strong>
            <em>{{ task.reason || '进入对应页面复查证据。' }}</em>
            <b>P{{ task.priority ?? '-' }}</b>
          </button>
        </div>
      </div>

      <div v-if="whatChanged.length > 0" class="panel what-changed-panel" data-testid="what-changed-panel">
        <div class="panel-header">
          <div>
            <p class="kicker">WHAT CHANGED</p>
            <h2 class="panel-title">今日重要变化</h2>
          </div>
          <span class="panel-subtitle">最需要关注的 {{ whatChanged.length }} 个变化</span>
        </div>
        <div class="what-changed-grid">
          <WhatChangedCard v-for="item in whatChanged" :key="item.id" :item="item" />
        </div>
      </div>

      <div v-if="qualitySummary.total_reports > 0" class="panel quality-panel">
        <div class="panel-header">
          <div>
            <p class="kicker">RESEARCH QUALITY</p>
            <h2 class="panel-title">研究库健康度</h2>
          </div>
          <button class="panel-link" @click="router.push('/reports')">查看全部</button>
        </div>
        <ResearchQualityOverview :summary="qualitySummary" :top-issues="qualityIssues.slice(0, 3)" />
      </div>

      <div class="panel portfolio-panel">
        <div class="panel-header">
          <div>
            <p class="kicker">PORTFOLIO SNAPSHOT</p>
            <h2 class="panel-title">持仓快照</h2>
          </div>
          <button class="panel-link" @click="router.push('/portfolio')">管理持仓</button>
        </div>

        <template v-if="workspace.portfolio_snapshot.position_count === 0">
          <div class="panel-empty">
            还没有持仓记录
            <button class="link-btn" @click="router.push('/portfolio')">去录入</button>
          </div>
        </template>

        <template v-else>
          <div class="summary-cards">
            <div class="sum-card">
              <div class="sum-label">持仓数量</div>
              <div class="sum-val">{{ workspace.portfolio_snapshot.position_count }}</div>
            </div>
            <div class="sum-card">
              <div class="sum-label">总成本</div>
              <div class="sum-val">${{ fmt(workspace.portfolio_snapshot.total_cost) }}</div>
            </div>
            <div class="sum-card" :class="(workspace.portfolio_snapshot.total_pnl || 0) >= 0 ? 'gain' : 'loss'">
              <div class="sum-label">总盈亏</div>
              <div class="sum-val">
                {{ workspace.portfolio_snapshot.total_pnl == null ? '--' : (workspace.portfolio_snapshot.total_pnl >= 0 ? '+' : '') + '$' + fmt(workspace.portfolio_snapshot.total_pnl) }}
              </div>
            </div>
          </div>

          <div v-if="workspace.portfolio_snapshot.risk_positions.length > 0" class="risk-section">
            <div class="risk-title">持仓风险提示：亏损超过 5% 的标的</div>
            <div
              v-for="position in workspace.portfolio_snapshot.risk_positions.slice(0, 3)"
              :key="position.ticker"
              class="risk-item"
              @click="router.push(`/dossier/${position.ticker}`)"
            >
              <span class="risk-ticker">{{ position.ticker }}</span>
              <span v-if="position.name" class="risk-name">{{ position.name }}</span>
              <span class="risk-pct">{{ riskPercent(position) }}</span>
            </div>
          </div>
        </template>
      </div>

      <div class="main-grid">
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">自选清单</h2>
            <button class="panel-link" @click="router.push('/stocks?tab=watchlist')">管理</button>
          </div>
          <div v-if="workspace.watchlist_movers.length === 0" class="panel-empty">
            还没有自选标的
            <button class="link-btn" @click="router.push('/stocks')">去添加</button>
          </div>
          <div v-else class="simple-list">
            <div
              v-for="item in workspace.watchlist_movers.slice(0, 5)"
              :key="item.ticker"
              class="simple-item"
              @click="router.push(`/dossier/${item.ticker}`)"
            >
              <span class="si-ticker">{{ item.ticker }}</span>
              <span v-if="item.name" class="si-name">{{ item.name }}</span>
              <span class="si-arrow">打开</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">最新提醒</h2>
            <button class="panel-link" @click="router.push('/welcome')">全部</button>
          </div>
          <div v-if="workspace.alert_feed.length === 0" class="panel-empty">暂无触发提醒</div>
          <div v-for="event in workspace.alert_feed.slice(0, 4)" :key="event.id" class="alert-item">
            <span class="alert-ticker">{{ event.ticker }}</span>
            <div class="alert-body">
              <div class="alert-title">{{ event.title }}</div>
              <div class="alert-time">{{ fmtDate(event.triggered_at) }}</div>
            </div>
            <span class="alert-sev" :class="`sev-${event.severity}`">{{ event.severity }}</span>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">待复查报告</h2>
            <button class="panel-link" @click="router.push('/reports')">报告库</button>
          </div>
          <div v-if="workspace.reports_to_review.length === 0" class="panel-empty">暂无需要复查的报告</div>
          <div v-else class="report-list">
            <div
              v-for="report in workspace.reports_to_review.slice(0, 4)"
              :key="report.report_id"
              class="report-item"
              @click="router.push(`/reports?highlight=${report.report_id}`)"
            >
              <span class="rep-ticker">{{ report.ticker || '--' }}</span>
              <div class="rep-body">
                <div class="rep-title">{{ report.title || `${report.report_id.slice(0, 20)}...` }}</div>
                <div class="rep-meta">
                  <span v-if="report.as_of">{{ fmtDate(report.as_of) }}</span>
                  <span v-if="report.review_status" class="rep-status">{{ report.review_status }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel full-width">
        <div class="panel-header">
          <div>
            <p class="kicker">NEXT ACTIONS</p>
            <h2 class="panel-title">建议操作</h2>
          </div>
          <span class="panel-count">{{ workspace.next_actions.length }}</span>
        </div>
        <div v-if="workspace.next_actions.length === 0" class="panel-empty">暂无操作建议</div>
        <div v-else class="actions-grid">
          <div
            v-for="action in workspace.next_actions.slice(0, 6)"
            :key="action.id"
            class="action-card"
            :class="`sev-${action.severity}`"
            @click="router.push(integratedRoute(action.target_route))"
          >
            <div class="ac-icon">{{ severityIcons[action.severity] || 'GO' }}</div>
            <div class="ac-body">
              <div class="ac-title">{{ action.title }}</div>
              <div class="ac-reason">{{ action.reason }}</div>
            </div>
            <span class="ac-arrow">复查</span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.page {
  width: 100%;
  max-width: none;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.today-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: clamp(26px, 3vw, 42px);
  overflow: hidden;
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 40%),
    radial-gradient(circle at 92% 10%, var(--fin-accent-soft), transparent 32%),
    var(--fin-card);
}

.kicker {
  margin: 0 0 8px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.today-hero h2 {
  margin: 0;
  color: var(--fin-text);
  font-size: clamp(34px, 4.4vw, 64px);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.today-date {
  margin: 12px 0 0;
  color: var(--fin-text-2);
}

.today-summary {
  max-width: 900px;
  margin: 12px 0 0;
  color: var(--fin-text);
  font-size: 17px;
}

.hero-actions {
  display: grid;
  justify-items: end;
  gap: 12px;
  flex-shrink: 0;
}

.live-dot {
  border: 1px solid var(--fin-border-strong);
  border-radius: 999px;
  padding: 6px 10px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 11px;
  font-weight: 900;
  background: var(--fin-primary-soft);
}

.btn-refresh,
.panel-link,
.link-btn {
  border: 0;
  border-radius: 14px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.btn-refresh {
  padding: 12px 22px;
}

.panel-link,
.link-btn {
  padding: 8px 12px;
}

.error-banner,
.loading-state,
.panel {
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-lg);
  background: var(--fin-card);
}

.error-banner {
  padding: 14px 18px;
  color: var(--fin-danger);
  background: var(--fin-danger-soft);
}

.loading-state {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 260px;
  color: var(--fin-muted);
}

.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--fin-border);
  border-top-color: var(--fin-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.panel {
  padding: 22px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.08);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.panel-title {
  margin: 0;
  color: var(--fin-text);
  font-size: 20px;
}

.panel-subtitle,
.panel-empty,
.sum-label,
.si-name,
.alert-time,
.rep-meta,
.ac-reason {
  color: var(--fin-muted);
}

.what-changed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.tasks-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
}

.task-card {
  position: relative;
  min-height: 132px;
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  padding: 16px 48px 16px 16px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  text-align: left;
  cursor: pointer;
}

.task-card:hover {
  border-color: var(--fin-border-strong);
  background: var(--fin-card-soft);
}

.task-card span,
.task-card em {
  display: block;
  color: var(--fin-muted);
  font-size: 13px;
  font-style: normal;
}

.task-card strong {
  display: block;
  margin: 8px 0;
  font-size: 16px;
}

.task-card b {
  position: absolute;
  top: 14px;
  right: 14px;
  border-radius: 999px;
  padding: 3px 8px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-size: 11px;
}

.summary-cards,
.main-grid {
  display: grid;
  gap: 14px;
}

.summary-cards {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.main-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.sum-card,
.simple-item,
.report-item,
.action-card,
.risk-section {
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-inset);
}

.sum-card {
  padding: 16px;
}

.sum-val {
  color: var(--fin-text);
  font-size: 24px;
  font-weight: 900;
}

.sum-card.gain .sum-val {
  color: var(--fin-success);
}

.sum-card.loss .sum-val {
  color: var(--fin-danger);
}

.risk-section {
  margin-top: 14px;
  padding: 14px;
  background: var(--fin-warning-soft);
}

.risk-title {
  margin-bottom: 10px;
  color: var(--fin-warning);
  font-weight: 900;
}

.risk-item,
.simple-item,
.report-item,
.alert-item,
.action-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.risk-item {
  padding: 8px 10px;
  cursor: pointer;
}

.risk-ticker,
.si-ticker,
.rep-ticker,
.alert-ticker {
  min-width: 58px;
  color: var(--fin-primary);
  font-weight: 900;
}

.risk-name,
.alert-body,
.rep-body,
.ac-body {
  flex: 1;
  min-width: 0;
}

.risk-pct {
  color: var(--fin-danger);
  font-weight: 900;
}

.panel-empty {
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
}

.simple-list,
.report-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.simple-item,
.report-item {
  padding: 12px 14px;
  cursor: pointer;
}

.si-name,
.rep-title,
.alert-title,
.ac-reason {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alert-item {
  padding: 11px 0;
  border-bottom: 1px solid var(--fin-border);
}

.alert-item:last-child {
  border-bottom: 0;
}

.alert-sev,
.rep-status,
.panel-count {
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
}

.sev-high,
.sev-critical {
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

.sev-medium {
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.sev-low {
  background: var(--fin-success-soft);
  color: var(--fin-success);
}

.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.action-card {
  padding: 16px;
  cursor: pointer;
}

.action-card:hover,
.simple-item:hover,
.report-item:hover,
.risk-item:hover {
  border-color: var(--fin-border-strong);
  background: var(--fin-card-soft);
}

.ac-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 14px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
}

.ac-title {
  color: var(--fin-text);
  font-weight: 900;
}

.ac-arrow {
  color: var(--fin-primary);
  font-weight: 900;
}

@media (max-width: 1100px) {
  .main-grid,
  .summary-cards,
  .actions-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .today-hero,
  .panel-header {
    display: grid;
    justify-items: start;
  }

  .hero-actions {
    justify-items: start;
  }
}
</style>
