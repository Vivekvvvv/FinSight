<script setup lang="ts">
import { computed, onMounted, ref, onUnmounted } from 'vue';
import { http } from '@/api/client';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface MarginRecord {
  date: string;
  margin_balance: number;
  margin_buy: number;
  margin_repay: number;
  short_balance: number;
  short_sell: number;
  short_repay: number;
  total_balance: number;
  close_price?: number;
}

const ticker = ref('600519.SS');
const days = ref(90);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const records = ref<MarginRecord[]>([]);

const trendChartContainer = ref<HTMLElement | null>(null);
const ratioChartContainer = ref<HTMLElement | null>(null);
let trendChartInstance: echarts.ECharts | null = null;
let ratioChartInstance: echarts.ECharts | null = null;

const latestData = computed(() => records.value[records.value.length - 1] || null);
const marginBalance = computed(() => latestData.value?.margin_balance || 0);
const shortBalance = computed(() => latestData.value?.short_balance || 0);
const totalBalance = computed(() => latestData.value?.total_balance || 0);

const marginBalanceChange = computed(() => {
  if (records.value.length < 2) return 0;
  const prev = records.value[records.value.length - 2].margin_balance;
  const curr = latestData.value?.margin_balance || 0;
  return curr - prev;
});

function formatMoney(value: number): string {
  if (value >= 100000000) {
    return (value / 100000000).toFixed(2) + '亿';
  } else if (value >= 10000) {
    return (value / 10000).toFixed(2) + '万';
  }
  return value.toFixed(2);
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

async function loadHistory(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await http.get(`/api/stock/margin/${ticker.value}/history?days=${days.value}`);
    records.value = resp.data.records || [];

    if (records.value.length > 0) {
      renderTrendChart();
      renderRatioChart();
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function renderTrendChart(): void {
  if (!trendChartContainer.value || records.value.length === 0) return;

  if (!trendChartInstance) {
    trendChartInstance = echarts.init(trendChartContainer.value);
  }

  const dates = records.value.map(r => formatDate(r.date));
  const marginBalances = records.value.map(r => (r.margin_balance / 100000000).toFixed(2));
  const prices = records.value.map(r => r.close_price || 0);

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
    },
    legend: {
      data: ['融资余额', '股价'],
      textStyle: { color: '#888' },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#444' } },
      axisLabel: { color: '#888' },
    },
    yAxis: [
      {
        type: 'value',
        name: '融资余额(亿)',
        position: 'left',
        axisLine: { lineStyle: { color: '#5470c6' } },
        axisLabel: { color: '#888', formatter: '{value}' },
        splitLine: { lineStyle: { color: '#333', type: 'dashed' } },
      },
      {
        type: 'value',
        name: '股价(元)',
        position: 'right',
        axisLine: { lineStyle: { color: '#91cc75' } },
        axisLabel: { color: '#888', formatter: '{value}' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '融资余额',
        type: 'line',
        yAxisIndex: 0,
        data: marginBalances,
        smooth: true,
        itemStyle: { color: '#5470c6' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(84, 112, 198, 0.3)' },
              { offset: 1, color: 'rgba(84, 112, 198, 0.05)' },
            ],
          },
        },
      },
      {
        name: '股价',
        type: 'line',
        yAxisIndex: 1,
        data: prices,
        smooth: true,
        itemStyle: { color: '#91cc75' },
        lineStyle: { width: 2 },
      },
    ],
  };

  trendChartInstance.setOption(option);
}

function renderRatioChart(): void {
  if (!ratioChartContainer.value || records.value.length === 0) return;

  if (!ratioChartInstance) {
    ratioChartInstance = echarts.init(ratioChartContainer.value);
  }

  const dates = records.value.map(r => formatDate(r.date));
  const marginBuyRatios = records.value.map(r => {
    const total = r.margin_buy + r.margin_repay;
    return total > 0 ? ((r.margin_buy / total) * 100).toFixed(2) : '0';
  });

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: unknown) => {
        const item = (params as Array<{name: string; seriesName: string; value: number}>)[0];
        return `${item.name}<br/>${item.seriesName}: ${item.value}%`;
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: '#444' } },
      axisLabel: { color: '#888', rotate: 45 },
    },
    yAxis: {
      type: 'value',
      name: '买入占比(%)',
      axisLine: { lineStyle: { color: '#444' } },
      axisLabel: { color: '#888', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#333', type: 'dashed' } },
    },
    series: [
      {
        name: '融资买入占比',
        type: 'bar',
        data: marginBuyRatios,
        itemStyle: {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          color: (params: any) => {
            const value = parseFloat(params.value);
            return value >= 50 ? '#f56c6c' : '#67c23a';
          },
        },
        barWidth: '60%',
      },
    ],
  };

  ratioChartInstance.setOption(option);
}

function handleResize(): void {
  trendChartInstance?.resize();
  ratioChartInstance?.resize();
}

onMounted(() => {
  void loadHistory();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  trendChartInstance?.dispose();
  ratioChartInstance?.dispose();
});
</script>

<template>
  <div class="margin-trading-page">
    <header class="page-header">
      <h2>融资融券分析</h2>
      <p class="muted">A股融资融券余额趋势与买入占比</p>
    </header>

    <section class="control-panel">
      <div class="input-group">
        <label>股票代码</label>
        <input
          v-model="ticker"
          type="text"
          placeholder="例如: 600519.SS"
          @keyup.enter="loadHistory"
        />
      </div>
      <div class="input-group">
        <label>查询范围</label>
        <select v-model.number="days" @change="loadHistory">
          <option :value="30">最近30天</option>
          <option :value="90">最近90天</option>
          <option :value="180">最近180天</option>
        </select>
      </div>
      <button class="btn-primary" :disabled="loading" @click="loadHistory">
        {{ loading ? '查询中...' : '查询' }}
      </button>
    </section>

    <section v-if="errorMsg" class="error-banner">
      {{ errorMsg }}
    </section>

    <section v-if="!loading && records.length > 0" class="stats-grid">
      <article class="stat-card">
        <p class="stat-label">融资余额</p>
        <strong class="stat-value">{{ formatMoney(marginBalance) }}</strong>
        <span
          class="stat-change"
          :class="marginBalanceChange >= 0 ? 'pos' : 'neg'"
        >
          {{ marginBalanceChange >= 0 ? '+' : '' }}{{ formatMoney(marginBalanceChange) }}
        </span>
      </article>

      <article class="stat-card">
        <p class="stat-label">融券余量</p>
        <strong class="stat-value">{{ formatMoney(shortBalance) }}</strong>
        <span class="stat-desc">卖空规模</span>
      </article>

      <article class="stat-card">
        <p class="stat-label">融资融券余额</p>
        <strong class="stat-value">{{ formatMoney(totalBalance) }}</strong>
        <span class="stat-desc">总两融规模</span>
      </article>

      <article class="stat-card">
        <p class="stat-label">数据记录数</p>
        <strong class="stat-value">{{ records.length }}</strong>
        <span class="stat-desc">{{ days }}天历史</span>
      </article>
    </section>

    <section v-if="!loading && records.length > 0" class="chart-section">
      <article class="chart-card">
        <header class="chart-header">
          <h3>融资余额 & 股价趋势</h3>
          <p class="muted">左轴：融资余额(亿) | 右轴：股价(元)</p>
        </header>
        <div ref="trendChartContainer" class="chart-container" />
      </article>

      <article class="chart-card">
        <header class="chart-header">
          <h3>融资买入占比</h3>
          <p class="muted">融资买入 / (融资买入 + 融资偿还) × 100%</p>
        </header>
        <div ref="ratioChartContainer" class="chart-container" />
      </article>
    </section>

    <section v-if="!loading && records.length === 0 && !errorMsg" class="empty-state">
      <p>暂无数据，请输入A股代码查询</p>
    </section>
  </div>
</template>

<style scoped>
.margin-trading-page {
  max-width: 1400px;
  margin: 0 auto;
  display: grid;
  gap: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 28px;
  color: var(--fin-text);
}

.page-header .muted {
  margin: 6px 0 0;
  color: var(--fin-muted);
  font-size: 14px;
}

.control-panel {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  max-width: 240px;
}

.input-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--fin-text-2);
}

.input-group input,
.input-group select {
  padding: 10px 14px;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 14px;
}

.btn-primary {
  padding: 10px 24px;
  border: 0;
  border-radius: 12px;
  background: var(--fin-primary);
  color: white;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  padding: 16px;
  border: 1px solid var(--fin-error);
  border-radius: 12px;
  background: color-mix(in srgb, var(--fin-error) 10%, transparent);
  color: var(--fin-error);
  font-size: 14px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}

.stat-card {
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-label {
  margin: 0;
  font-size: 13px;
  color: var(--fin-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stat-value {
  font-size: 26px;
  color: var(--fin-text);
}

.stat-change {
  font-size: 14px;
  font-weight: 600;
}

.stat-change.pos {
  color: var(--fin-success);
}

.stat-change.neg {
  color: var(--fin-error);
}

.stat-desc {
  font-size: 13px;
  color: var(--fin-muted);
}

.chart-section {
  display: grid;
  gap: 24px;
}

.chart-card {
  padding: 24px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}

.chart-header {
  margin-bottom: 20px;
}

.chart-header h3 {
  margin: 0 0 6px;
  font-size: 18px;
  color: var(--fin-text);
}

.chart-header .muted {
  margin: 0;
  font-size: 13px;
  color: var(--fin-muted);
}

.chart-container {
  width: 100%;
  height: 400px;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--fin-muted);
  font-size: 15px;
}

@media (max-width: 768px) {
  .control-panel {
    flex-direction: column;
    align-items: stretch;
  }

  .input-group {
    max-width: none;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .chart-container {
    height: 300px;
  }
}
</style>
