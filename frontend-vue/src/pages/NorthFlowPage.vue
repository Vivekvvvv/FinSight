<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { apiClient, http } from '@/api/client';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface NorthFlowData {
  date: string;
  time: string;
  north_flow: number;
  sh_flow: number;
  sz_flow: number;
  data_points: Array<{
    time: string;
    north: number;
    sh: number;
    sz: number;
  }>;
}

interface HistoryRecord {
  date: string;
  north_flow: number;
  sh_flow: number;
  sz_flow: number;
}

const loading = ref(false);
const errorMsg = ref<string | null>(null);
const realtimeData = ref<NorthFlowData | null>(null);
const historyData = ref<HistoryRecord[]>([]);
const days = ref(30);

const intradayChartContainer = ref<HTMLElement | null>(null);
const historyChartContainer = ref<HTMLElement | null>(null);
let intradayChartInstance: echarts.ECharts | null = null;
let historyChartInstance: echarts.ECharts | null = null;

const totalFlow = computed(() => realtimeData.value?.north_flow || 0);
const shFlow = computed(() => realtimeData.value?.sh_flow || 0);
const szFlow = computed(() => realtimeData.value?.sz_flow || 0);

const avgHistoryFlow = computed(() => {
  if (historyData.value.length === 0) return 0;
  const sum = historyData.value.reduce((acc, r) => acc + r.north_flow, 0);
  return sum / historyData.value.length;
});

function formatMoney(value: number): string {
  const absValue = Math.abs(value);
  if (absValue >= 100000000) {
    return (value / 100000000).toFixed(2) + '亿';
  } else if (absValue >= 10000) {
    return (value / 10000).toFixed(2) + '万';
  }
  return value.toFixed(2);
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

async function loadRealtime(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await http.get('/api/market/north-flow');
    realtimeData.value = resp.data;

    if (realtimeData.value) {
      renderIntradayChart();
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadHistory(): Promise<void> {
  try {
    const resp = await http.get(`/api/market/north-flow/history?days=${days.value}`);
    historyData.value = resp.data.records || [];

    if (historyData.value.length > 0) {
      renderHistoryChart();
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

function renderIntradayChart(): void {
  if (!intradayChartContainer.value || !realtimeData.value) return;

  if (!intradayChartInstance) {
    intradayChartInstance = echarts.init(intradayChartContainer.value);
  }

  const points = realtimeData.value.data_points || [];
  const times = points.map(p => p.time);
  const northValues = points.map(p => p.north / 100000000);  // 转为亿元
  const shValues = points.map(p => p.sh / 100000000);
  const szValues = points.map(p => p.sz / 100000000);

  const option: EChartsOption = {
    title: {
      text: '今日分时资金流向',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: any) => {
        const time = params[0].name;
        let text = `${time}<br/>`;
        params.forEach((p: any) => {
          text += `${p.marker}${p.seriesName}: ${p.value.toFixed(2)}亿<br/>`;
        });
        return text;
      }
    },
    legend: {
      data: ['北向总计', '沪股通', '深股通'],
      top: 30
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: times,
      boundaryGap: false,
      axisLabel: { fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      name: '流入（亿元）',
      axisLabel: { formatter: '{value}' }
    },
    series: [
      {
        name: '北向总计',
        type: 'line',
        smooth: true,
        data: northValues,
        itemStyle: { color: '#1890ff' },
        lineStyle: { width: 2 }
      },
      {
        name: '沪股通',
        type: 'line',
        smooth: true,
        data: shValues,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '深股通',
        type: 'line',
        smooth: true,
        data: szValues,
        itemStyle: { color: '#faad14' }
      }
    ]
  };

  intradayChartInstance.setOption(option);
}

function renderHistoryChart(): void {
  if (!historyChartContainer.value || historyData.value.length === 0) return;

  if (!historyChartInstance) {
    historyChartInstance = echarts.init(historyChartContainer.value);
  }

  const dates = historyData.value.map(r => formatDate(r.date)).reverse();
  const northValues = historyData.value.map(r => r.north_flow / 100000000).reverse();
  const shValues = historyData.value.map(r => r.sh_flow / 100000000).reverse();
  const szValues = historyData.value.map(r => r.sz_flow / 100000000).reverse();

  const option: EChartsOption = {
    title: {
      text: `最近${days.value}天资金流向趋势`,
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' }
    },
    legend: {
      data: ['北向总计', '沪股通', '深股通'],
      top: 30
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLabel: { fontSize: 11, rotate: 45 }
    },
    yAxis: [
      {
        type: 'value',
        name: '北向总计（亿元）',
        position: 'left',
        axisLabel: { formatter: '{value}' }
      },
      {
        type: 'value',
        name: '沪深股通（亿元）',
        position: 'right',
        axisLabel: { formatter: '{value}' }
      }
    ],
    series: [
      {
        name: '北向总计',
        type: 'line',
        smooth: true,
        data: northValues,
        itemStyle: { color: '#1890ff' },
        areaStyle: { color: 'rgba(24, 144, 255, 0.1)' },
        lineStyle: { width: 3 }
      },
      {
        name: '沪股通',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: shValues,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '深股通',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: szValues,
        itemStyle: { color: '#faad14' }
      }
    ]
  };

  historyChartInstance.setOption(option);
}

async function handleDaysChange(): Promise<void> {
  await loadHistory();
}

onMounted(async () => {
  await Promise.all([loadRealtime(), loadHistory()]);
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">北向资金</h1>
        <p class="subtitle">沪深股通资金流向实时追踪</p>
      </div>
      <div class="controls">
        <label>
          历史范围
          <select v-model="days" class="select" @change="handleDaysChange">
            <option :value="7">最近7天</option>
            <option :value="30">最近30天</option>
            <option :value="90">最近90天</option>
          </select>
        </label>
        <button class="btn-primary" :disabled="loading" @click="loadRealtime">
          {{ loading ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <div v-if="realtimeData" class="stats-row">
      <div class="stat-card">
        <div class="stat-label">今日北向总计</div>
        <div class="stat-value" :class="{ positive: totalFlow > 0, negative: totalFlow < 0 }">
          {{ formatMoney(totalFlow) }}
        </div>
        <div class="stat-time">{{ realtimeData.time }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">沪股通</div>
        <div class="stat-value" :class="{ positive: shFlow > 0, negative: shFlow < 0 }">
          {{ formatMoney(shFlow) }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">深股通</div>
        <div class="stat-value" :class="{ positive: szFlow > 0, negative: szFlow < 0 }">
          {{ formatMoney(szFlow) }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">近期日均</div>
        <div class="stat-value" :class="{ positive: avgHistoryFlow > 0, negative: avgHistoryFlow < 0 }">
          {{ formatMoney(avgHistoryFlow) }}
        </div>
      </div>
    </div>

    <div v-if="realtimeData" class="chart-card">
      <div ref="intradayChartContainer" class="chart-container" />
    </div>

    <div v-if="historyData.length > 0" class="chart-card">
      <div ref="historyChartContainer" class="chart-container" />
    </div>

    <div v-if="!loading && !realtimeData" class="empty-state">
      暂无北向资金数据
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  color: var(--fin-text);
}

.subtitle {
  margin: 4px 0 0;
  color: var(--fin-muted);
  font-size: 14px;
}

.controls {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.controls label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--fin-muted);
}

.select {
  padding: 9px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
  cursor: pointer;
}

.btn-primary {
  padding: 9px 16px;
  border: 0;
  border-radius: 8px;
  background: var(--fin-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  padding: 12px 16px;
  background: #fff1f0;
  border: 1.5px solid #ffccc7;
  border-radius: 10px;
  color: #cf1322;
  font-size: 14px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}

.stat-card {
  padding: 16px 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
}

.stat-label {
  font-size: 12px;
  color: var(--fin-muted);
  font-weight: 600;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--fin-text);
}

.stat-value.positive { color: #ff4d4f; }
.stat-value.negative { color: #52c41a; }

.stat-time {
  margin-top: 4px;
  font-size: 11px;
  color: var(--fin-muted);
}

.chart-card {
  padding: 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
}

.chart-container {
  width: 100%;
  height: 400px;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--fin-muted);
  font-size: 14px;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .controls {
    width: 100%;
  }
}
</style>
