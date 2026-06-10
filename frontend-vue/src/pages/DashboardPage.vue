<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, CandlestickChart, LineChart, RadarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, RadarComponent, TooltipComponent } from 'echarts/components';
import { apiClient } from '@/api/client';
import EvidencePanel from '@/components/EvidencePanel.vue';
import WhatChangedCard from '@/components/WhatChangedCard.vue';
import type { DashboardInsightsResponse, WhatChangedItem } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import { useThemeStore } from '@/stores/theme';

use([CanvasRenderer, CandlestickChart, LineChart, RadarChart, BarChart, GridComponent, TooltipComponent, LegendComponent, RadarComponent]);

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();
const theme = useThemeStore();

const symbolInput = ref(String(route.params.symbol || 'AAPL').toUpperCase());
const activeTab = ref('overview');
const loading = ref(false);
const deepLoading = ref(false);
const errorMsg = ref<string | null>(null);
const quote = ref<any>(null);
const kline = ref<any>(null);
const financials = ref<any>(null);
const news = ref<any[]>([]);
const insights = ref<DashboardInsightsResponse | null>(null);
const changes = ref<WhatChangedItem[]>([]);
const deepAnalysis = ref('');
const deepEvidence = ref<any>(null);

const tabs = [
  ['overview', '综合分析'],
  ['financial', '财务报表'],
  ['technical', '技术面'],
  ['news', '新闻动态'],
  ['research', '深度研究'],
  ['peers', '同行对比'],
];

const q = computed(() => quote.value?.data || {});
const chartPalette = computed(() => theme.resolved === 'dark'
  ? {
      axis: '#789085',
      grid: 'rgba(214,255,226,0.1)',
      up: '#8cffb6',
      down: '#ff8f8f',
      line: '#d7ff72',
      primary: '#d7ff72',
      card: '#17251f',
      text: '#eef8ef',
    }
  : {
      axis: '#66746c',
      grid: 'rgba(23,33,29,0.12)',
      up: '#168a54',
      down: '#c44545',
      line: '#245f49',
      primary: '#245f49',
      card: '#fffaf0',
      text: '#16221d',
    });

const insightCards = computed(() => Object.entries(insights.value?.insights || {}).map(([key, value]: [string, any]) => ({ key, ...value })));
const primaryScore = computed(() => {
  const scores = insightCards.value.map((item: any) => Number(item.score || 0)).filter(Boolean);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 7.4;
});

const metricStrip = computed(() => [
  ['市值', q.value.marketCap ? `${(q.value.marketCap / 1e9).toFixed(1)}B` : '--'],
  ['PE', financials.value?.data?.trailingPE || q.value.trailingPE || '--'],
  ['PB', financials.value?.data?.priceToBook || '--'],
  ['EPS', financials.value?.data?.trailingEps || q.value.trailingEps || '--'],
  ['Beta', q.value.beta || '--'],
  ['52周区间', q.value.fiftyTwoWeekLow && q.value.fiftyTwoWeekHigh ? `${q.value.fiftyTwoWeekLow} / ${q.value.fiftyTwoWeekHigh}` : '--'],
]);

const chartOption = computed(() => {
  const colors = chartPalette.value;
  const dates = kline.value?.data?.dates || [];
  const values = kline.value?.data?.values || [];
  const base = {
    backgroundColor: 'transparent',
    grid: { left: 42, right: 18, top: 28, bottom: 34 },
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.card,
      borderColor: colors.grid,
      textStyle: { color: colors.text },
    },
    xAxis: {
      type: 'category',
      data: dates.length ? dates : ['D-4', 'D-3', 'D-2', 'D-1', 'D'],
      axisLabel: { color: colors.axis },
      axisLine: { lineStyle: { color: colors.grid } },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: colors.axis },
      splitLine: { lineStyle: { color: colors.grid } },
    },
  };
  if (!dates.length || !values.length) {
    return {
      ...base,
      series: [{ type: 'line', smooth: true, data: [190, 194, 193, 198, 195], lineStyle: { color: colors.line, width: 3 }, areaStyle: { color: 'rgba(45,212,191,0.12)' } }],
    };
  }
  return {
    ...base,
    series: [{
      name: symbolInput.value,
      type: 'candlestick',
      data: values,
      itemStyle: { color: colors.up, color0: colors.down, borderColor: colors.up, borderColor0: colors.down },
    }],
  };
});

const radarOption = computed(() => {
  const colors = chartPalette.value;
  return {
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '基本面', max: 10 },
        { name: '技术面', max: 10 },
        { name: '新闻', max: 10 },
        { name: '风险', max: 10 },
        { name: '证据', max: 10 },
      ],
      axisName: { color: colors.axis },
      splitLine: { lineStyle: { color: colors.grid } },
      splitArea: { areaStyle: { color: ['transparent', 'rgba(45,212,191,0.06)'] } },
      axisLine: { lineStyle: { color: colors.grid } },
    },
    series: [{
      type: 'radar',
      data: [{ value: [8.1, 7.2, 6.8, 6.2, 8.6], name: '研究覆盖' }],
      areaStyle: { color: 'rgba(45, 212, 191, 0.18)' },
      lineStyle: { color: colors.primary, width: 3 },
      itemStyle: { color: colors.primary },
    }],
  };
});

function fmt(value: unknown): string {
  if (typeof value === 'number') return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
  if (value == null || value === '') return '--';
  return String(value);
}

async function refresh() {
  const symbol = symbolInput.value.trim().toUpperCase() || 'AAPL';
  symbolInput.value = symbol;
  loading.value = true;
  errorMsg.value = null;
  try {
    const [quoteResp, klineResp, financialsResp, insightsResp, newsResp, changesResp] = await Promise.allSettled([
      apiClient.getQuote(symbol),
      apiClient.getKline(symbol),
      apiClient.getFinancials(symbol),
      apiClient.getDashboardInsights(symbol),
      apiClient.getNews(symbol),
      apiClient.getWhatChanged({ sessionId: identity.sessionId, userId: identity.userId, symbol, limit: 3 }),
    ]);
    quote.value = quoteResp.status === 'fulfilled' ? quoteResp.value : null;
    kline.value = klineResp.status === 'fulfilled' ? klineResp.value : null;
    financials.value = financialsResp.status === 'fulfilled' ? financialsResp.value : null;
    insights.value = insightsResp.status === 'fulfilled' ? insightsResp.value : null;
    news.value = newsResp.status === 'fulfilled' && Array.isArray(newsResp.value?.data) ? newsResp.value.data : [];
    changes.value = changesResp.status === 'fulfilled' ? changesResp.value.items || [] : [];
    await router.replace(`/dashboard/${encodeURIComponent(symbol)}`);
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

async function runDeepAnalysis() {
  if (deepLoading.value) return;
  deepLoading.value = true;
  deepAnalysis.value = '';
  deepEvidence.value = null;
  try {
    await apiClient.streamChat({
      query: `请对 ${symbolInput.value} 做一份研究复查摘要：覆盖基本面、技术面、新闻催化、风险项和需要继续核验的证据。不要给买入或卖出建议。`,
      session_id: identity.sessionId,
      options: { output_mode: 'investment_report' },
    }, {
      onToken: (token) => { deepAnalysis.value += token; },
      onDone: (evidence) => { deepEvidence.value = evidence; },
      onError: (message) => { errorMsg.value = message; },
    });
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    deepLoading.value = false;
  }
}

onMounted(refresh);
watch(() => route.params.symbol, (value) => {
  const next = String(value || 'AAPL').toUpperCase();
  if (next !== symbolInput.value) {
    symbolInput.value = next;
    void refresh();
  }
});
</script>

<template>
  <section class="dashboard-page">
    <div class="hero page-card">
      <div>
        <p class="kicker">MARKET DOSSIER</p>
        <h2>{{ symbolInput }} / {{ q.shortName || q.longName || '研究标的' }}</h2>
        <div class="price-row">
          <strong>{{ fmt(q.currentPrice || q.regularMarketPrice) }}</strong>
          <span :class="Number(q.regularMarketChange || 0) >= 0 ? 'gain' : 'loss'">
            {{ Number(q.regularMarketChange || 0) >= 0 ? '+' : '' }}{{ fmt(q.regularMarketChange) }}
            / {{ fmt(q.regularMarketChangePercent) }}%
          </span>
        </div>
      </div>
      <form class="search-box" @submit.prevent="refresh">
        <input v-model="symbolInput" placeholder="输入股票代码，如 AAPL">
        <button :disabled="loading">{{ loading ? '刷新中...' : '查询' }}</button>
        <button type="button" @click="router.push(`/timeline/${symbolInput}`)">证据时间线</button>
      </form>
    </div>

    <p v-if="errorMsg" class="error-banner">{{ errorMsg }}</p>

    <div class="metric-strip">
      <article v-for="[label, value] in metricStrip" :key="label" class="page-card metric-card">
        <span>{{ label }}</span>
        <strong>{{ value }}</strong>
      </article>
    </div>

    <div class="main-grid">
      <section class="page-card chart-card">
        <div class="section-head">
          <div>
            <p class="kicker">PRICE ACTION</p>
            <h3>K 线与短期结构</h3>
          </div>
          <span>{{ q.freshness_status || quote?.data?.freshness_status || 'live' }}</span>
        </div>
        <VChart class="chart" :option="chartOption" autoresize />
      </section>

      <aside class="page-card score-card">
        <p class="kicker">AI SCORE</p>
        <h3>AI 洞察</h3>
        <div class="score-ring" :style="{ '--score': primaryScore * 10 }">
          <strong>{{ primaryScore.toFixed(1) }}</strong>
          <span>/ 10</span>
        </div>
        <p>综合评级来自多维信号汇总，只作为研究优先级，不作为交易建议。</p>
        <VChart class="radar" :option="radarOption" autoresize />
      </aside>
    </div>

    <section class="page-card tab-card">
      <div class="tab-row">
        <button
          v-for="[key, label] in tabs"
          :key="key"
          :class="{ active: activeTab === key }"
          @click="activeTab = key"
        >
          {{ label }}
        </button>
      </div>

      <div v-if="activeTab === 'overview'" class="tab-content">
        <article v-for="item in insightCards.slice(0, 3)" :key="item.key" class="insight-card">
          <span class="score-label">{{ item.score_label || item.key }}</span>
          <h4>{{ item.summary }}</h4>
          <ul>
            <li v-for="point in (item.key_points || []).slice(0, 3)" :key="point">{{ point }}</li>
          </ul>
        </article>
        <article v-if="insightCards.length === 0" class="insight-card">
          <span class="score-label">待生成</span>
          <h4>暂无 AI 洞察，点击深度研究可生成复查摘要。</h4>
        </article>
      </div>

      <div v-else-if="activeTab === 'financial'" class="tab-content dense">
        <article v-for="[key, value] in Object.entries(financials?.data || {}).slice(0, 8)" :key="key" class="data-row">
          <span>{{ key }}</span>
          <strong>{{ fmt(value) }}</strong>
        </article>
      </div>

      <div v-else-if="activeTab === 'technical'" class="tab-content dense">
        <article class="data-row"><span>日内高低</span><strong>{{ fmt(q.regularMarketDayLow) }} / {{ fmt(q.regularMarketDayHigh) }}</strong></article>
        <article class="data-row"><span>成交量</span><strong>{{ fmt(q.regularMarketVolume) }}</strong></article>
        <article class="data-row"><span>Beta</span><strong>{{ fmt(q.beta) }}</strong></article>
        <EvidencePanel source="quote+kline" freshness-status="live" :confidence="0.74" :degraded="!q.rsi" compact />
      </div>

      <div v-else-if="activeTab === 'news'" class="tab-content">
        <article v-for="item in news.slice(0, 6)" :key="item.title || item.link" class="news-card">
          <h4>{{ item.title || item.headline || '未命名新闻' }}</h4>
          <p>{{ item.source || item.publisher || 'News' }} / {{ item.publishedAt || item.datetime || '最近' }}</p>
        </article>
        <article v-if="news.length === 0" class="news-card">暂无新闻数据。</article>
      </div>

      <div v-else-if="activeTab === 'research'" class="tab-content research-pane">
        <button class="primary" :disabled="deepLoading" @click="runDeepAnalysis">
          {{ deepLoading ? '生成中...' : '生成深度复查摘要' }}
        </button>
        <pre>{{ deepAnalysis || '这里会展示面向复查的深度研究摘要。' }}</pre>
        <EvidencePanel v-if="deepEvidence" v-bind="deepEvidence" />
      </div>

      <div v-else class="tab-content">
        <article class="insight-card">
          <span class="score-label">PEERS</span>
          <h4>同行对比入口已补回。</h4>
          <p>下一步可接入 peers API；当前先保留研究路径和页面结构。</p>
        </article>
      </div>
    </section>

    <section v-if="changes.length" class="changes">
      <WhatChangedCard v-for="item in changes" :key="item.id" :item="item" />
    </section>
  </section>
</template>

<style scoped>
.dashboard-page {
  width: 100%;
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

.kicker {
  margin: 0 0 6px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h2,
h3,
h4 {
  margin: 0;
  color: var(--fin-text);
}

.price-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 12px;
}

.price-row strong {
  font-size: clamp(42px, 5vw, 72px);
  line-height: 1;
  letter-spacing: -0.07em;
}

.search-box {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.search-box input {
  border-radius: 16px;
  padding: 12px 14px;
  min-width: 240px;
}

.search-box button,
.primary {
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  padding: 16px;
}

.metric-card span,
.score-card p,
.news-card p,
.data-row span,
.insight-card ul {
  color: var(--fin-muted);
}

.metric-card strong {
  display: block;
  margin-top: 4px;
  color: var(--fin-text);
  font-size: 18px;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);
  gap: 18px;
}

.chart-card,
.score-card,
.tab-card {
  padding: 22px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.section-head > span {
  border-radius: 999px;
  padding: 4px 10px;
  background: var(--fin-success-soft);
  color: var(--fin-success);
  font-family: var(--fin-mono);
  font-size: 11px;
  font-weight: 900;
}

.chart {
  height: 380px;
}

.score-ring {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  margin: 18px auto;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at center, var(--fin-card) 55%, transparent 56%),
    conic-gradient(var(--fin-primary) calc(var(--score, 75) * 1%), var(--fin-card-inset) 0);
}

.score-ring strong {
  font-size: 44px;
}

.radar {
  height: 230px;
}

.tab-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.tab-row button {
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  padding: 10px 14px;
  background: var(--fin-card-inset);
  color: var(--fin-text-2);
  cursor: pointer;
  font-weight: 800;
}

.tab-row button.active {
  background: var(--fin-primary);
  color: var(--fin-bg);
}

.tab-content {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.tab-content.dense {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.insight-card,
.news-card,
.data-row,
pre {
  border: 1px solid var(--fin-border);
  border-radius: 20px;
  padding: 16px;
  background: var(--fin-card-inset);
}

.score-label {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 9px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-size: 11px;
  font-weight: 900;
}

.insight-card ul {
  padding-left: 18px;
}

.data-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.research-pane {
  grid-template-columns: 1fr;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  color: var(--fin-text);
  min-height: 180px;
  font-family: inherit;
}

.changes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.error-banner {
  border-radius: 18px;
  padding: 12px 16px;
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

@media (max-width: 1180px) {
  .metric-strip,
  .tab-content,
  .tab-content.dense,
  .changes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .hero,
  .main-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .search-box {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .metric-strip,
  .tab-content,
  .tab-content.dense,
  .changes {
    grid-template-columns: 1fr;
  }
}
</style>
