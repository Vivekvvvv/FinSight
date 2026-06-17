<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { http } from '@/api/client';
import { useIdentityStore } from '@/stores/identity';
import type { AlertEvent, DailyTask, PortfolioSummary, ReportIndexItem, WatchlistItem } from '@/api/types';

const identity = useIdentityStore();
const router = useRouter();
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const portfolio = ref<PortfolioSummary | null>(null);
const reports = ref<ReportIndexItem[]>([]);
const tasks = ref<DailyTask[]>([]);
const alerts = ref<AlertEvent[]>([]);
const watchlist = ref<WatchlistItem[]>([]);
const rebalanceStyle = ref('balanced');
const maxPosition = ref(25);
const minCash = ref(8);
const useAiEnhance = ref(true);
const WORKBENCH_TIMEOUT_MS = 6000;

const today = computed(() => new Date().toLocaleDateString('zh-CN', { weekday: 'long', month: 'long', day: 'numeric' }));
const positions = computed(() => portfolio.value?.positions || []);
const riskPositions = computed(() => positions.value.filter((item) => {
  if (item.avg_cost == null || item.live_price == null || item.avg_cost === 0) return false;
  return ((item.live_price - item.avg_cost) / item.avg_cost) < -0.05;
}));
const largestPosition = computed(() => {
  const sorted = [...positions.value].sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0));
  return sorted[0] || null;
});
const timelineItems = computed(() => [
  ...reports.value.map((item) => ({
    id: `report-${item.report_id}`,
    type: '报告',
    symbol: item.ticker || 'GLOBAL',
    title: item.title || '未命名报告',
    time: item.generated_at || item.updated_at || '',
    confidence: item.confidence_score,
    route: `/reports?highlight=${item.report_id}`,
  })),
  ...alerts.value.map((item) => ({
    id: `alert-${item.id}`,
    type: '提醒',
    symbol: item.ticker,
    title: item.title,
    time: item.triggered_at,
    confidence: item.severity === 'high' ? 0.86 : 0.64,
    route: '/alerts',
  })),
].sort((a, b) => new Date(b.time).getTime() - new Date(a.time).getTime()));

function fmt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '--';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function fmtTime(value?: string | null): string {
  if (!value) return '未知时间';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

async function refresh() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const results = await Promise.allSettled([
      http.get<PortfolioSummary>('/api/portfolio/summary', {
        params: { session_id: identity.sessionId },
        timeout: WORKBENCH_TIMEOUT_MS,
        headers: { 'X-Skip-Global-Loading': '1' },
      }).then((resp) => resp.data),
      http.get<{ success: boolean; items: ReportIndexItem[]; count: number }>('/api/reports/index', {
        params: { session_id: identity.sessionId, sort_by: 'generated_at_desc', limit: 10 },
        timeout: WORKBENCH_TIMEOUT_MS,
        headers: { 'X-Skip-Global-Loading': '1' },
      }).then((resp) => resp.data),
      http.get<{ success: boolean; tasks: DailyTask[]; count: number }>('/api/tasks/daily', {
        params: { session_id: identity.sessionId },
        timeout: WORKBENCH_TIMEOUT_MS,
        headers: { 'X-Skip-Global-Loading': '1' },
      }).then((resp) => resp.data),
      identity.email
        ? http.get<{ success: boolean; events: AlertEvent[]; count: number }>('/api/alerts/feed', {
          params: { email: identity.email, limit: 10 },
          timeout: WORKBENCH_TIMEOUT_MS,
          headers: { 'X-Skip-Global-Loading': '1' },
        }).then((resp) => resp.data)
        : Promise.resolve({ events: [] }),
      http.get<{ success: boolean; items: WatchlistItem[]; count: number }>('/api/user/watchlist', {
        params: { user_id: identity.userId },
        timeout: WORKBENCH_TIMEOUT_MS,
        headers: { 'X-Skip-Global-Loading': '1' },
      }).then((resp) => resp.data),
    ]);
    if (results[0].status === 'fulfilled') portfolio.value = results[0].value;
    if (results[1].status === 'fulfilled') reports.value = results[1].value.items || [];
    if (results[2].status === 'fulfilled') tasks.value = results[2].value.tasks || [];
    if (results[3].status === 'fulfilled') alerts.value = results[3].value.events || [];
    if (results[4].status === 'fulfilled') watchlist.value = results[4].value.items || [];

    const failedCount = results.filter((item) => item.status === 'rejected').length;
    if (failedCount > 0) {
      errorMsg.value = `${failedCount} 个工作台数据源暂时不可用，已先展示可用数据。`;
    }
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function generateRebalancePrompt() {
  const prompt = [
    '请基于当前持仓生成一份研究复查清单，不要给买入或卖出建议。',
    `风险偏好：${rebalanceStyle.value}`,
    `单一标的上限：${maxPosition.value}%`,
    `最低现金比例：${minCash.value}%`,
    `AI 证据增强：${useAiEnhance.value ? '开启' : '关闭'}`,
  ].join('\n');
  router.push({ path: '/chat', query: { prefill: prompt, symbol: largestPosition.value?.ticker || 'AAPL' } });
}

onMounted(refresh);
watch(() => identity.sessionId, () => { void refresh(); });
</script>

<template>
  <section class="workbench-page">
    <header class="page-card workbench-hero">
      <div>
        <p class="kicker">DAILY RESEARCH LAB</p>
        <h2>{{ today }} / 30 秒知道今天该复查什么</h2>
        <p>整合持仓、任务、报告、告警和自选标的，把研究动作排成优先级。</p>
      </div>
      <button :disabled="loading" @click="refresh">{{ loading ? '刷新中...' : '刷新工作台' }}</button>
    </header>

    <p v-if="errorMsg" class="error-banner">{{ errorMsg }}</p>

    <section class="summary-strip">
      <h3 class="strip-title">持仓概览</h3>
      <article class="page-card">
        <span>持仓数量</span>
        <strong>{{ portfolio?.count || 0 }}</strong>
      </article>
      <article class="page-card">
        <span>总市值</span>
        <strong>${{ fmt(portfolio?.total_value) }}</strong>
      </article>
      <article class="page-card">
        <span>总盈亏</span>
        <strong :class="Number(portfolio?.total_pnl || 0) >= 0 ? 'gain' : 'loss'">
          {{ Number(portfolio?.total_pnl || 0) >= 0 ? '+' : '' }}${{ fmt(portfolio?.total_pnl) }}
        </strong>
      </article>
      <article class="page-card">
        <span>最大持仓</span>
        <strong>{{ largestPosition?.ticker || '--' }}</strong>
      </article>
    </section>

    <div class="workbench-grid">
      <main class="left-stack">
        <section class="page-card task-panel">
          <div class="section-head">
            <div>
              <p class="kicker">TODAY TASKS</p>
              <h3>今日任务</h3>
            </div>
            <span>{{ tasks.length }} 项</span>
          </div>
          <article v-for="task in tasks.slice(0, 6)" :key="task.id" class="task-row" @click="task.action_url && router.push(task.action_url)">
            <strong>{{ task.title }}</strong>
            <p>{{ task.reason || '建议进入对应页面复查证据。' }}</p>
            <span>P{{ task.priority ?? '-' }}</span>
          </article>
          <p v-if="tasks.length === 0" class="empty">暂无任务。添加持仓或自选后，系统会生成研究动作。</p>
        </section>

        <section class="page-card rebalance-panel">
          <div class="section-head">
            <div>
              <p class="kicker">SMART REBALANCE</p>
              <h3>智能调仓复查入口</h3>
            </div>
            <span>研究建议模式</span>
          </div>

          <div class="risk-style">
            <button :class="{ active: rebalanceStyle === 'conservative' }" @click="rebalanceStyle = 'conservative'">稳健</button>
            <button :class="{ active: rebalanceStyle === 'balanced' }" @click="rebalanceStyle = 'balanced'">均衡</button>
            <button :class="{ active: rebalanceStyle === 'aggressive' }" @click="rebalanceStyle = 'aggressive'">进取</button>
          </div>

          <div class="constraint-grid">
            <label>
              单一标的上限
              <input v-model.number="maxPosition" type="range" min="5" max="60">
              <strong>{{ maxPosition }}%</strong>
            </label>
            <label>
              最低现金比例
              <input v-model.number="minCash" type="range" min="0" max="30">
              <strong>{{ minCash }}%</strong>
            </label>
          </div>

          <label class="check-row">
            <input v-model="useAiEnhance" type="checkbox">
            <span>启用 AI 证据增强：附带报告、提醒、笔记与时间线证据。</span>
          </label>

          <button class="primary" @click="generateRebalancePrompt">生成调仓复查清单</button>
          <p class="fine-print">该入口只生成研究清单和风险复查点，不输出买入/卖出建议。</p>
        </section>

        <section v-if="riskPositions.length" class="page-card risk-panel">
          <p class="kicker">RISK POSITIONS</p>
          <h3>持仓风险提示：需要优先复查的持仓</h3>
          <article v-for="item in riskPositions" :key="item.ticker" class="risk-row" @click="router.push(`/dashboard/${item.ticker}`)">
            <strong class="risk-ticker">{{ item.ticker }}</strong>
            <span>{{ item.name || '持仓标的' }}</span>
            <em>{{ (((Number(item.live_price) - Number(item.avg_cost)) / Number(item.avg_cost)) * 100).toFixed(2) }}%</em>
          </article>
        </section>
      </main>

      <aside class="right-stack">
        <section class="page-card timeline-panel">
          <div class="section-head">
            <div>
              <p class="kicker">RESEARCH TIMELINE</p>
              <h3>近期研究报告 / 研究时间线</h3>
            </div>
            <button @click="router.push(`/timeline/${largestPosition?.ticker || 'AAPL'}`)">打开时间线</button>
          </div>
          <article v-for="item in timelineItems.slice(0, 8)" :key="item.id" class="timeline-row" @click="router.push(item.route)">
            <span>{{ item.type }}</span>
            <strong>{{ item.title }}</strong>
            <p>{{ item.symbol }} / {{ fmtTime(item.time) }} / 置信度 {{ item.confidence == null ? '--' : Math.round(item.confidence * 100) + '%' }}</p>
          </article>
          <p v-if="timelineItems.length === 0" class="empty">暂无报告或告警时间线。</p>
        </section>

        <section class="page-card watch-panel">
          <p class="kicker">WATCHLIST PRIORITY</p>
          <h3>高优先级关注</h3>
          <button v-for="item in watchlist.slice(0, 6)" :key="item.ticker" @click="router.push(`/dashboard/${item.ticker}`)">
            <strong>{{ item.ticker }}</strong>
            <span>{{ item.watch_reason || item.name || '研究关注' }}</span>
          </button>
        </section>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.workbench-page {
  width: 100%;
  display: grid;
  gap: 18px;
}

.workbench-hero,
.section-head,
.task-row,
.risk-row,
.timeline-row {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.workbench-hero {
  padding: 28px;
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 38%),
    radial-gradient(circle at 88% 16%, var(--fin-accent-soft), transparent 30%),
    var(--fin-card);
}

.workbench-hero button,
.section-head button,
.primary,
.risk-style button,
.watch-panel button {
  border: 0;
  border-radius: 16px;
  padding: 11px 14px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  font-weight: 900;
  cursor: pointer;
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

.workbench-hero p,
.task-row p,
.timeline-row p,
.fine-print,
.empty,
.summary-strip span,
.watch-panel span,
label {
  color: var(--fin-muted);
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.strip-title {
  grid-column: 1 / -1;
  margin: 0;
}

.summary-strip article,
.task-panel,
.rebalance-panel,
.risk-panel,
.timeline-panel,
.watch-panel {
  padding: 20px;
}

.summary-strip strong {
  display: block;
  margin-top: 6px;
  color: var(--fin-text);
  font-size: 30px;
  letter-spacing: -0.05em;
}

.workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 440px);
  gap: 18px;
}

.left-stack,
.right-stack {
  display: grid;
  align-content: start;
  gap: 18px;
}

.task-row,
.timeline-row,
.risk-row {
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  padding: 14px;
  margin-top: 12px;
  background: var(--fin-card-inset);
  cursor: pointer;
}

.task-row:hover,
.timeline-row:hover,
.risk-row:hover {
  border-color: var(--fin-border-strong);
  background: var(--fin-card-soft);
}

.task-row strong,
.timeline-row strong,
.risk-row strong {
  color: var(--fin-text);
}

.task-row span,
.section-head > span,
.timeline-row span {
  border-radius: 999px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  padding: 4px 9px;
  font-size: 13px;
  font-weight: 900;
}

.risk-style {
  display: flex;
  gap: 10px;
  margin: 18px 0;
}

.risk-style button {
  background: var(--fin-card-inset);
  color: var(--fin-text);
  border: 1px solid var(--fin-border);
}

.risk-style button.active {
  background: var(--fin-primary);
  color: var(--fin-bg);
}

.constraint-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

label {
  display: grid;
  gap: 8px;
  font-weight: 800;
}

input[type="range"] {
  accent-color: var(--fin-primary);
}

.check-row {
  grid-template-columns: auto 1fr;
  align-items: center;
  margin: 18px 0;
  font-weight: 500;
}

.risk-row em {
  color: var(--fin-danger);
  font-style: normal;
  font-weight: 900;
}

.timeline-row {
  display: block;
}

.timeline-row span {
  display: inline-flex;
  margin-bottom: 6px;
}

.watch-panel button {
  width: 100%;
  display: block;
  text-align: left;
  margin-top: 10px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  border: 1px solid var(--fin-border);
}

.watch-panel span {
  display: block;
  font-weight: 500;
  font-size: 14px;
}

.error-banner {
  border-radius: 18px;
  padding: 12px 16px;
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

@media (max-width: 1100px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .workbench-hero,
  .section-head,
  .task-row,
  .risk-row {
    display: grid;
  }

  .summary-strip,
  .constraint-grid {
    grid-template-columns: 1fr;
  }
}
</style>
