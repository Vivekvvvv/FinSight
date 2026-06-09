<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { CandlestickChart, LineChart, RadarChart, BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, RadarComponent } from 'echarts/components';
import { apiClient } from '@/api/client';
import EvidencePanel from '@/components/EvidencePanel.vue';
import WhatChangedCard from '@/components/WhatChangedCard.vue';
import type { DashboardInsightsResponse, WhatChangedItem } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';

use([CanvasRenderer, CandlestickChart, LineChart, RadarChart, BarChart, GridComponent, TooltipComponent, LegendComponent, RadarComponent]);

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();
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
  const dates = kline.value?.data?.dates || [];
  const values = kline.value?.data?.values || [];
  if (!dates.length || !values.length) {
    return {
      grid: { left: 34, right: 18, top: 28, bottom: 30 },
      xAxis: { type: 'category', data: ['D-4', 'D-3', 'D-2', 'D-1', 'D'] },
      yAxis: { type: 'value', scale: true },
      series: [{ type: 'line', smooth: true, data: [190, 194, 193, 198, 195], lineStyle: { color: '#d7ff72' } }],
    };
  }
  return {
    grid: { left: 42, right: 18, top: 26, bottom: 34 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#789085' } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#789085' } },
    series: [{
      name: symbolInput.value,
      type: 'candlestick',
      data: values,
      itemStyle: { color: '#8cffb6', color0: '#ff8f8f', borderColor: '#8cffb6', borderColor0: '#ff8f8f' },
    }],
  };
});

const radarOption = computed(() => ({
  radar: {
    indicator: [
      { name: '基本面', max: 10 },
      { name: '技术面', max: 10 },
      { name: '新闻', max: 10 },
      { name: '风险', max: 10 },
      { name: '证据', max: 10 },
    ],
    axisName: { color: '#5d7067' },
  },
  series: [{
    type: 'radar',
    data: [{ value: [8.1, 7.2, 6.8, 6.2, 8.6], name: '研究覆盖' }],
    areaStyle: { color: 'rgba(47, 111, 87, 0.18)' },
    lineStyle: { color: '#2f6f57' },
  }],
}));

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
        <h2>{{ symbolInput }} · {{ q.shortName || q.longName || '研究标的' }}</h2>
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
        <button :disabled="loading">{{ loading ? '刷新中…' : '查询' }}</button>
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
        <div class="score-ring">
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
          <p>{{ item.source || item.publisher || 'News' }} · {{ item.publishedAt || item.datetime || '最近' }}</p>
        </article>
        <article v-if="news.length === 0" class="news-card">暂无新闻数据。</article>
      </div>

      <div v-else-if="activeTab === 'research'" class="tab-content research-pane">
        <button class="primary" :disabled="deepLoading" @click="runDeepAnalysis">
          {{ deepLoading ? '生成中…' : '生成深度复查摘要' }}
        </button>
        <pre>{{ deepAnalysis || '这里会展示面向复查的深度研究摘要。' }}</pre>
        <EvidencePanel v-if="deepEvidence" v-bind="deepEvidence" />
      </div>

      <div v-else class="tab-content">
        <article class="insight-card">
          <span class="score-label">PEERS</span>
          <h4>同行对比入口已补回。</h4>
          <p>下一步可接入 peers API，当前先保留研究路径和页面结构。</p>
        </article>
      </div>
    </section>

    <section v-if="changes.length" class="changes">
      <WhatChangedCard
        v-for="item in changes"
        :key="item.id"
        :item="item"
        @navigate="router.push(item.target_route)"
      />
    </section>
  </section>
</template>

<style scoped>
.dashboard-page {
  display: grid;
  gap: 18px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: 28px;
  background:
    linear-gradient(135deg, rgba(215, 255, 114, 0.22), transparent 34%),
    #f7f3e8;
}

.kicker {
  margin: 0 0 6px;
  color: #2f6f57;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h2, h3, h4 {
  margin: 0;
  color: #17211d;
}

.price-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-top: 12px;
}

.price-row strong {
  font-size: 48px;
  line-height: 1;
  letter-spacing: -0.06em;
}

.gain { color: #168a54; }
.loss { color: #c44545; }

.search-box {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-box input {
  border: 1px solid rgba(23, 33, 29, 0.14);
  border-radius: 16px;
  padding: 12px 14px;
  min-width: 220px;
  background: #fffaf0;
}

.search-box button,
.primary {
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  background: #17211d;
  color: #d7ff72;
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

.metric-card span {
  color: #66746c;
  font-size: 12px;
}

.metric-card strong {
  display: block;
  margin-top: 4px;
  color: #17211d;
  font-size: 18px;
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
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
}

.chart {
  height: 340px;
}

.score-ring {
  width: 150px;
  height: 150px;
  border-radius: 50%;
  margin: 18px auto;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle at center, #f7f3e8 54%, transparent 55%),
    conic-gradient(#2f6f57 calc(var(--score, 75) * 1%), rgba(23, 33, 29, 0.08) 0);
}

.score-ring strong {
  font-size: 42px;
}

.score-card p {
  color: #66746c;
}

.radar {
  height: 220px;
}

.tab-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}

.tab-row button {
  border: 1px solid rgba(23, 33, 29, 0.1);
  border-radius: 999px;
  padding: 10px 14px;
  background: #efe9d8;
  color: #405047;
  cursor: pointer;
}

.tab-row button.active {
  background: #17211d;
  color: #d7ff72;
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
.data-row {
  border: 1px solid rgba(23, 33, 29, 0.1);
  border-radius: 20px;
  padding: 16px;
  background: #fffaf0;
}

.score-label {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 9px;
  background: #dff7df;
  color: #174936;
  font-size: 11px;
  font-weight: 900;
}

.insight-card ul {
  padding-left: 18px;
  color: #4e5f56;
}

.data-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.news-card p,
.data-row span {
  color: #66746c;
}

.research-pane {
  grid-template-columns: 1fr;
}

pre {
  white-space: pre-wrap;
  border: 1px solid rgba(23, 33, 29, 0.1);
  border-radius: 20px;
  padding: 16px;
  background: #fffaf0;
  color: #17211d;
  min-height: 180px;
}

.changes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.error-banner {
  border-radius: 18px;
  padding: 12px 16px;
  background: rgba(196, 69, 69, 0.12);
  color: #ffb4b4;
}

@media (max-width: 980px) {
  .hero,
  .main-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .metric-strip,
  .tab-content,
  .tab-content.dense,
  .changes {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .metric-strip,
  .tab-content,
  .tab-content.dense,
  .changes {
    grid-template-columns: 1fr;
  }

  .price-row strong {
    font-size: 36px;
  }
}
</style>
