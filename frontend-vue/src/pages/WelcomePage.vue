<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { TodayWorkspaceResponse, WhatChangedItem, ResearchQualitySummary, ResearchQualityIssue } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import WhatChangedCard from '@/components/WhatChangedCard.vue';
import ResearchQualityOverview from '@/components/ResearchQualityOverview.vue';

const identity = useIdentityStore();
const router = useRouter();

const workspace = ref<TodayWorkspaceResponse | null>(null);
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

const todayStr = computed(() => {
  return new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
});

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function fmtDate(v?: string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const SEVERITY_ICONS: Record<string, string> = {
  critical: '🔴',
  high: '🟠',
  medium: '🟡',
  low: '🟢',
};

async function refresh(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const [workspaceData, changesData, qualityData] = await Promise.all([
      apiClient.getTodayWorkspace(identity.sessionId, identity.userId),
      apiClient.getWhatChanged({
        sessionId: identity.sessionId,
        userId: identity.userId,
        limit: 5,
      }),
      apiClient.getResearchQuality({
        sessionId: identity.sessionId,
        userId: identity.userId,
      }),
    ]);
    workspace.value = workspaceData;
    whatChanged.value = changesData.items;
    qualitySummary.value = qualityData.summary;
    qualityIssues.value = qualityData.top_issues;
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
watch(() => identity.sessionId, () => { void refresh(); });
</script>

<template>
  <section class="page">
    <!-- Today 头部 -->
    <div class="today-hero">
      <div class="today-left">
        <div class="today-greeting">
          {{ identity.email ? `你好，${identity.email.split('@')[0]}` : '欢迎回来' }}
        </div>
        <div class="today-date">{{ todayStr }}</div>
        <div v-if="workspace" class="today-summary">{{ workspace.summary }}</div>
      </div>
      <button class="btn-refresh" :disabled="loading" @click="refresh">
        <span :class="{ spinning: loading }">↻</span>
        {{ loading ? '加载中…' : '刷新数据' }}
      </button>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 加载态 -->
    <div v-if="loading && !workspace" class="loading-state">
      <div class="spinner">↻</div>
      <div>加载今日工作台...</div>
    </div>

    <!-- 主内容 -->
    <template v-else-if="workspace">

      <!-- What Changed 模块 -->
      <div v-if="whatChanged.length > 0" class="panel what-changed-panel" data-testid="what-changed-panel">
        <div class="panel-header">
          <h2 class="panel-title">🔍 今日重要变化</h2>
          <span class="panel-subtitle">最需要关注的 {{ whatChanged.length }} 个变化</span>
        </div>
        <div class="what-changed-grid">
          <WhatChangedCard v-for="item in whatChanged" :key="item.id" :item="item" />
        </div>
      </div>

      <!-- Research Quality 模块 (Phase 4.5) -->
      <div v-if="qualitySummary.total_reports > 0" class="panel quality-panel">
        <div class="panel-header">
          <h2 class="panel-title">📊 研究库健康度</h2>
          <button class="panel-link" @click="router.push('/reports')">查看全部 →</button>
        </div>
        <ResearchQualityOverview
          :summary="qualitySummary"
          :top-issues="qualityIssues.slice(0, 3)"
        />
      </div>

      <!-- 持仓风险快照 -->
      <div class="panel">
        <div class="panel-header">
          <h2 class="panel-title">💼 持仓快照</h2>
          <button class="panel-link" @click="router.push('/portfolio')">管理持仓 →</button>
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
              <div class="sum-val">¥{{ fmt(workspace.portfolio_snapshot.total_cost) }}</div>
            </div>
            <div class="sum-card" :class="(workspace.portfolio_snapshot.total_pnl || 0) > 0 ? 'gain' : (workspace.portfolio_snapshot.total_pnl || 0) < 0 ? 'loss' : ''">
              <div class="sum-label">总盈亏</div>
              <div class="sum-val">
                {{ workspace.portfolio_snapshot.total_pnl == null ? '—' : (workspace.portfolio_snapshot.total_pnl >= 0 ? '+' : '') + '¥' + fmt(workspace.portfolio_snapshot.total_pnl) }}
              </div>
            </div>
          </div>

          <!-- 风险仓位 -->
          <div v-if="workspace.portfolio_snapshot.risk_positions.length > 0" class="risk-section">
            <div class="risk-title">⚠ 持仓风险提示（亏损 &gt;5%）</div>
            <div v-for="p in workspace.portfolio_snapshot.risk_positions.slice(0, 3)" :key="p.ticker" class="risk-item" @click="router.push(`/dashboard/${p.ticker}`)">
              <span class="risk-ticker">{{ p.ticker }}</span>
              <span v-if="p.name" class="risk-name">{{ p.name }}</span>
              <span class="risk-pct">
                {{ p.avg_cost && p.unrealized_pnl && p.cost_basis ? (((p.unrealized_pnl) / p.cost_basis) * 100).toFixed(2) + '%' : '—' }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- 网格布局：自选 + 提醒 + 待复查 -->
      <div class="main-grid">

        <!-- 自选动态 -->
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">⭐ 自选清单</h2>
            <button class="panel-link" @click="router.push('/watchlist')">管理 →</button>
          </div>
          <div v-if="workspace.watchlist_movers.length === 0" class="panel-empty">
            还没有自选标的
            <button class="link-btn" @click="router.push('/watchlist')">去添加</button>
          </div>
          <div v-else class="simple-list">
            <div v-for="item in workspace.watchlist_movers.slice(0, 5)" :key="item.ticker" class="simple-item" @click="router.push(`/dashboard/${item.ticker}`)">
              <span class="si-ticker">{{ item.ticker }}</span>
              <span v-if="item.name" class="si-name">{{ item.name }}</span>
              <span class="si-arrow">→</span>
            </div>
          </div>
        </div>

        <!-- 最新提醒 -->
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">🔔 最新提醒</h2>
            <button class="panel-link" @click="router.push('/alerts')">全部 →</button>
          </div>
          <div v-if="workspace.alert_feed.length === 0" class="panel-empty">暂无触发提醒</div>
          <div v-for="ev in workspace.alert_feed.slice(0, 4)" :key="ev.id" class="alert-item">
            <span class="alert-ticker">{{ ev.ticker }}</span>
            <div class="alert-body">
              <div class="alert-title">{{ ev.title }}</div>
              <div class="alert-time">{{ fmtDate(ev.triggered_at) }}</div>
            </div>
            <span class="alert-sev" :class="`sev-${ev.severity}`">{{ ev.severity }}</span>
          </div>
        </div>

        <!-- 待复查报告 -->
        <div class="panel">
          <div class="panel-header">
            <h2 class="panel-title">📋 待复查报告</h2>
            <button class="panel-link" @click="router.push('/reports')">报告库 →</button>
          </div>
          <div v-if="workspace.reports_to_review.length === 0" class="panel-empty">
            暂无需要复查的报告
          </div>
          <div v-else class="report-list">
            <div v-for="r in workspace.reports_to_review.slice(0, 4)" :key="r.report_id" class="report-item" @click="router.push(`/reports?highlight=${r.report_id}`)">
              <span class="rep-ticker">{{ r.ticker || '—' }}</span>
              <div class="rep-body">
                <div class="rep-title">{{ r.title || r.report_id.slice(0, 20) + '...' }}</div>
                <div class="rep-meta">
                  <span v-if="r.as_of">{{ fmtDate(r.as_of) }}</span>
                  <span v-if="r.review_status" class="rep-status">{{ r.review_status }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /main-grid -->

      <!-- 下一步操作建议 -->
      <div class="panel full-width">
        <div class="panel-header">
          <h2 class="panel-title">✨ 建议操作</h2>
          <span class="panel-count">{{ workspace.next_actions.length }}</span>
        </div>
        <div v-if="workspace.next_actions.length === 0" class="panel-empty">暂无操作建议</div>
        <div v-else class="actions-grid">
          <div
            v-for="action in workspace.next_actions.slice(0, 6)"
            :key="action.id"
            class="action-card"
            :class="`sev-${action.severity}`"
            @click="router.push(action.target_route)"
          >
            <div class="ac-icon">{{ SEVERITY_ICONS[action.severity] || '💡' }}</div>
            <div class="ac-body">
              <div class="ac-title">{{ action.title }}</div>
              <div class="ac-reason">{{ action.reason }}</div>
            </div>
            <span class="ac-arrow">→</span>
          </div>
        </div>
      </div>

    </template>

  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; max-width: 1200px; }

/* Today 头部 */
.today-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 28px 32px;
  background: linear-gradient(135deg, #cc785c 0%, #d88a6f 100%);
  border-radius: 20px;
  color: #fff;
}

.today-greeting { font-size: 26px; font-weight: 700; margin-bottom: 6px; }
.today-date { font-size: 14px; color: rgba(255,255,255,0.75); margin-bottom: 8px; }
.today-summary { font-size: 14px; color: rgba(255,255,255,0.9); font-weight: 500; max-width: 600px; line-height: 1.5; }

.btn-refresh {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 22px;
  border: 2px solid rgba(255,255,255,0.3);
  border-radius: 12px;
  background: rgba(255,255,255,0.15);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.btn-refresh:hover:not(:disabled) { background: rgba(255,255,255,0.25); }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-banner { padding: 14px 18px; background: #fff1f0; border: 1.5px solid #ffccc7; border-radius: 12px; color: #cf1322; font-size: 14px; }

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 20px;
  color: var(--fin-muted);
  font-size: 14px;
}
.spinner { font-size: 32px; animation: spin 1s linear infinite; }

/* 面板 */
.panel {
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 16px;
  padding: 20px 22px;
}
.panel.full-width { grid-column: 1 / -1; }

/* What Changed 面板 */
.what-changed-panel { margin-bottom: 20px; }
.panel-subtitle { font-size: 13px; color: var(--fin-muted); font-weight: 500; }
.what-changed-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

@media (max-width: 900px) {
  .what-changed-grid {
    grid-template-columns: 1fr;
  }
}

.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.panel-title { font-size: 16px; font-weight: 700; margin: 0; color: var(--fin-text); }
.panel-count { font-size: 12px; font-weight: 600; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 10px; border-radius: 20px; }
.panel-link { border: none; background: transparent; font-size: 13px; color: var(--fin-primary); cursor: pointer; font-weight: 600; transition: opacity 0.15s; }
.panel-link:hover { opacity: 0.75; }
.panel-empty { font-size: 14px; color: var(--fin-muted); padding: 20px 0; text-align: center; display: flex; align-items: center; justify-content: center; gap: 8px; flex-wrap: wrap; }
.link-btn { border: none; background: transparent; color: var(--fin-primary); cursor: pointer; font-size: 14px; font-weight: 600; text-decoration: underline; }

/* 持仓快照 */
.summary-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 14px; }
.sum-card { padding: 12px 14px; background: var(--fin-bg); border-radius: 10px; }
.sum-card.gain { background: #f0faf4; }
.sum-card.loss { background: #fff4f4; }
.sum-label { font-size: 12px; color: var(--fin-muted); margin-bottom: 6px; font-weight: 600; }
.sum-val { font-size: 18px; font-weight: 700; color: var(--fin-text); }
.sum-card.gain .sum-val { color: #27ae60; }
.sum-card.loss .sum-val { color: #e74c3c; }

.risk-section { padding: 12px 14px; background: #fff8e6; border: 1.5px solid #f9c74f; border-radius: 10px; }
.risk-title { font-size: 13px; font-weight: 700; color: #856404; margin-bottom: 8px; }
.risk-item { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--fin-text); padding: 6px 8px; border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.risk-item:hover { background: rgba(249, 199, 79, 0.2); }
.risk-ticker { font-weight: 700; min-width: 56px; }
.risk-name { flex: 1; color: var(--fin-muted); }
.risk-pct { color: #e74c3c; font-weight: 700; font-size: 14px; }

/* 主网格 */
.main-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

/* 简单列表（自选） */
.simple-list { display: flex; flex-direction: column; gap: 4px; }
.simple-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: var(--fin-bg); border-radius: 8px; cursor: pointer; transition: background 0.15s; }
.simple-item:hover { background: var(--fin-primary-soft); }
.si-ticker { font-size: 14px; font-weight: 700; color: var(--fin-primary); min-width: 56px; }
.si-name { font-size: 13px; color: var(--fin-muted); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.si-arrow { color: var(--fin-muted); font-size: 14px; }

/* 提醒 */
.alert-item { display: flex; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--fin-border); }
.alert-item:last-child { border-bottom: none; }
.alert-ticker { font-size: 12px; font-weight: 700; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 8px; border-radius: 6px; flex-shrink: 0; }
.alert-body { flex: 1; min-width: 0; }
.alert-title { font-size: 13px; color: var(--fin-text); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alert-time { font-size: 11px; color: var(--fin-muted); margin-top: 2px; }
.alert-sev { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; text-transform: uppercase; }
.sev-high { background: #fce4e4; color: #c44545; }
.sev-medium { background: #fef3cd; color: #856404; }
.sev-low { background: #e6f4ec; color: #2d7d46; }

/* 报告列表 */
.report-list { display: flex; flex-direction: column; gap: 6px; }
.report-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: var(--fin-bg); border-radius: 8px; cursor: pointer; transition: background 0.15s; }
.report-item:hover { background: var(--fin-primary-soft); }
.rep-ticker { font-size: 12px; font-weight: 700; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 8px; border-radius: 6px; flex-shrink: 0; min-width: 56px; text-align: center; }
.rep-body { flex: 1; min-width: 0; }
.rep-title { font-size: 13px; font-weight: 600; color: var(--fin-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rep-meta { font-size: 11px; color: var(--fin-muted); margin-top: 3px; display: flex; gap: 8px; }
.rep-status { padding: 1px 6px; background: var(--fin-primary-soft); color: var(--fin-primary); border-radius: 4px; font-weight: 600; }

/* 操作建议网格 */
.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.action-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--fin-bg);
  border: 1.5px solid var(--fin-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.action-card:hover { border-color: var(--fin-primary); transform: translateY(-2px); box-shadow: 0 4px 12px rgba(204,120,92,0.12); }

.ac-icon { font-size: 22px; flex-shrink: 0; }
.ac-body { flex: 1; min-width: 0; }
.ac-title { font-size: 14px; font-weight: 600; color: var(--fin-text); margin-bottom: 3px; }
.ac-reason { font-size: 12px; color: var(--fin-muted); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ac-arrow { color: var(--fin-muted); font-size: 16px; flex-shrink: 0; }

@media (max-width: 1100px) {
  .main-grid { grid-template-columns: 1fr; }
  .actions-grid { grid-template-columns: 1fr; }
}

@media (max-width: 700px) {
  .summary-cards { grid-template-columns: 1fr; }
  .today-hero { padding: 20px 24px; }
  .today-greeting { font-size: 22px; }
}
</style>
