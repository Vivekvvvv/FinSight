<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { apiClient } from '@/api/client';
import NotificationManager from '@/components/NotificationManager.vue';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface DataSourceStatus {
  status: string;
  total_requests: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
  consecutive_failures: number;
  last_success_at: string | null;
  last_failure_at: string | null;
  avg_response_time_ms: number;
  is_healthy: boolean;
}

interface HealthReport {
  timestamp: string;
  overall_status: string;
  degraded_sources: string[];
  sources: Record<string, DataSourceStatus>;
}

interface TrendRecord {
  timestamp: string;
  source_name: string;
  success_rate: number;
  avg_response_time_ms: number;
  is_healthy: number;
}

const health = ref<HealthReport | null>(null);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const autoRefresh = ref(true);
const trendDays = ref(7);
const selectedSource = ref<string>('tencent');
let refreshTimer: number | null = null;
let chartInstance: echarts.ECharts | null = null;
const chartContainer = ref<HTMLElement | null>(null);

const sourceOptions = computed(() => {
  if (!health.value) return [];
  return Object.keys(health.value.sources);
});

const statusColorMap: Record<string, string> = {
  healthy: '#52c41a',
  warning: '#faad14',
  degraded: '#ff7a45',
  critical: '#ff4d4f',
};

const statusLabelMap: Record<string, string> = {
  healthy: '健康',
  warning: '警告',
  degraded: '降级',
  critical: '严重',
};

function getStatusColor(status: string): string {
  return statusColorMap[status] || '#8c8c8c';
}

function getStatusLabel(status: string): string {
  return statusLabelMap[status] || status;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  } catch {
    return iso;
  }
}

async function refresh(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.getSystemHealth();
    health.value = resp as HealthReport;
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function loadTrendChart(): Promise<void> {
  if (!chartContainer.value) return;

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const trendData = await apiClient.getHealthTrend(selectedSource.value, trendDays.value) as any;
    const records = (trendData.records || []) as TrendRecord[];

    // 按时间升序排列
    records.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    const timestamps = records.map(r => {
      const d = new Date(r.timestamp);
      return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
    });
    const successRates = records.map(r => r.success_rate);
    const responseTimes = records.map(r => r.avg_response_time_ms);

    if (!chartInstance) {
      chartInstance = echarts.init(chartContainer.value);
    }

    const option: EChartsOption = {
      title: {
        text: `${selectedSource.value} - 最近${trendDays.value}天趋势`,
        left: 'center',
        textStyle: { fontSize: 14, fontWeight: 600, color: '#1f2933' }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' }
      },
      legend: {
        data: ['成功率 (%)', '响应时间 (ms)'],
        top: 30,
        textStyle: { fontSize: 12 }
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
        boundaryGap: false,
        data: timestamps,
        axisLabel: { fontSize: 11, rotate: 45 }
      },
      yAxis: [
        {
          type: 'value',
          name: '成功率 (%)',
          position: 'left',
          min: 0,
          max: 100,
          axisLabel: { formatter: '{value}%' }
        },
        {
          type: 'value',
          name: '响应时间 (ms)',
          position: 'right',
          axisLabel: { formatter: '{value}ms' }
        }
      ],
      series: [
        {
          name: '成功率 (%)',
          type: 'line',
          smooth: true,
          data: successRates,
          itemStyle: { color: '#52c41a' },
          areaStyle: { color: 'rgba(82, 196, 26, 0.1)' }
        },
        {
          name: '响应时间 (ms)',
          type: 'line',
          smooth: true,
          yAxisIndex: 1,
          data: responseTimes,
          itemStyle: { color: '#1890ff' }
        }
      ]
    };

    chartInstance.setOption(option);
  } catch (e) {
    console.error('加载趋势图失败:', e);
  }
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  if (autoRefresh.value) {
    refreshTimer = window.setInterval(() => {
      void refresh();
    }, 10000);
  }
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value;
  if (autoRefresh.value) {
    startAutoRefresh();
  } else if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

async function handleTrendChange() {
  await loadTrendChart();
}

onMounted(async () => {
  await refresh();
  startAutoRefresh();
  await loadTrendChart();
});

import { onBeforeUnmount } from 'vue';
onBeforeUnmount(() => {
  if (refreshTimer) clearInterval(refreshTimer);
  if (chartInstance) {
    chartInstance.dispose();
    chartInstance = null;
  }
});

</script>

<template>
  <section class="page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">系统健康监控</h1>
        <span
          v-if="health"
          class="status-badge"
          :style="{ background: getStatusColor(health.overall_status) }"
        >
          {{ getStatusLabel(health.overall_status) }}
        </span>
      </div>
      <div class="header-right">
        <NotificationManager />
        <button
          class="btn-toggle"
          :class="{ active: autoRefresh }"
          @click="toggleAutoRefresh"
        >
          {{ autoRefresh ? '⏸ 停止自动刷新' : '▶ 启动自动刷新' }}
        </button>
        <button class="btn-ghost" :disabled="loading" @click="refresh">
          <span :class="{ spinning: loading }">↻</span>
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 加载状态 -->
    <div v-if="loading && !health" class="loading-state">
      <span class="loader" />
      <span>加载健康数据…</span>
    </div>

    <!-- 健康仪表盘 -->
    <div v-else-if="health" class="dashboard">
      <!-- 趋势图 -->
      <div class="trend-card">
        <div class="trend-controls">
          <label>
            数据源
            <select v-model="selectedSource" @change="handleTrendChange">
              <option v-for="src in sourceOptions" :key="src" :value="src">
                {{ src === 'tencent' ? '腾讯财经' : src === 'yahoo' ? 'Yahoo Finance' : src === 'demo' ? 'Demo模式' : src }}
              </option>
            </select>
          </label>
          <label>
            时间范围
            <select v-model="trendDays" @change="handleTrendChange">
              <option :value="1">最近1天</option>
              <option :value="7">最近7天</option>
              <option :value="30">最近30天</option>
            </select>
          </label>
        </div>
        <div ref="chartContainer" class="chart-container" />
      </div>

      <!-- 降级源警告 -->
      <div v-if="health.degraded_sources.length > 0" class="alert-card">
        <div class="alert-icon">⚠️</div>
        <div class="alert-content">
          <div class="alert-title">数据源降级警告</div>
          <div class="alert-desc">
            以下数据源已降级：
            <strong>{{ health.degraded_sources.join(', ') }}</strong>
          </div>
        </div>
      </div>

      <!-- 数据源卡片 -->
      <div class="sources-grid">
        <div
          v-for="(sourceData, sourceName) in health.sources"
          :key="sourceName"
          class="source-card"
          :class="{ degraded: !sourceData.is_healthy }"
        >
          <div class="source-header">
            <div class="source-name">
              <span class="source-icon">{{ sourceName === 'tencent' ? '🐧' : sourceName === 'yahoo' ? '🌐' : '📦' }}</span>
              <span class="source-title">{{ sourceName === 'tencent' ? '腾讯财经' : sourceName === 'yahoo' ? 'Yahoo Finance' : sourceName === 'demo' ? 'Demo模式' : sourceName }}</span>
            </div>
            <div
              class="source-status"
              :style="{ background: getStatusColor(sourceData.status), color: '#fff' }"
            >
              {{ getStatusLabel(sourceData.status) }}
            </div>
          </div>

          <div class="metrics">
            <!-- 成功率 -->
            <div class="metric-row">
              <div class="metric-label">成功率</div>
              <div class="metric-value" :class="{ good: sourceData.success_rate >= 90, warning: sourceData.success_rate >= 70 && sourceData.success_rate < 90, bad: sourceData.success_rate < 70 }">
                {{ sourceData.success_rate.toFixed(1) }}%
              </div>
            </div>

            <!-- 请求统计 -->
            <div class="metric-row">
              <div class="metric-label">请求次数</div>
              <div class="metric-value">{{ sourceData.total_requests }}</div>
            </div>

            <div class="metric-row">
              <div class="metric-label">成功/失败</div>
              <div class="metric-value">
                <span class="success">{{ sourceData.success_count }}</span> /
                <span class="failure">{{ sourceData.failure_count }}</span>
              </div>
            </div>

            <!-- 连续失败 -->
            <div v-if="sourceData.consecutive_failures > 0" class="metric-row">
              <div class="metric-label">连续失败</div>
              <div class="metric-value bad">{{ sourceData.consecutive_failures }} 次</div>
            </div>

            <!-- 平均响应时间 -->
            <div class="metric-row">
              <div class="metric-label">平均响应时间</div>
              <div class="metric-value" :class="{ good: sourceData.avg_response_time_ms < 100, warning: sourceData.avg_response_time_ms >= 100 && sourceData.avg_response_time_ms < 500 }">
                {{ sourceData.avg_response_time_ms.toFixed(1) }} ms
              </div>
            </div>

            <!-- 最后成功 -->
            <div v-if="sourceData.last_success_at" class="metric-row">
              <div class="metric-label">最后成功</div>
              <div class="metric-value small">{{ formatTime(sourceData.last_success_at) }}</div>
            </div>

            <!-- 最后失败 -->
            <div v-if="sourceData.last_failure_at" class="metric-row">
              <div class="metric-label">最后失败</div>
              <div class="metric-value small bad">{{ formatTime(sourceData.last_failure_at) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 元数据 -->
      <div class="meta-footer">
        <span class="meta-item">📊 更新时间: {{ formatTime(health.timestamp) }}</span>
        <span v-if="autoRefresh" class="meta-item">🔄 自动刷新: 10秒</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }

.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 24px; font-weight: 700; margin: 0; color: var(--fin-text); }
.status-badge {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  padding: 4px 12px;
  border-radius: 20px;
}
.header-right { display: flex; gap: 8px; align-items: center; }

.btn-toggle {
  padding: 9px 16px;
  border: 1.5px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-muted);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-toggle.active {
  background: var(--fin-primary);
  border-color: var(--fin-primary);
  color: #fff;
}
.btn-toggle:hover { opacity: 0.88; }

.btn-ghost {
  padding: 9px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  cursor: pointer;
  font-size: 16px;
  color: var(--fin-muted);
}
.btn-ghost:hover { border-color: var(--fin-primary); color: var(--fin-primary); }

.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-banner { padding: 12px 16px; background: #fff1f0; border: 1.5px solid #ffccc7; border-radius: 10px; color: #cf1322; font-size: 14px; }

.loading-state { display: flex; gap: 10px; align-items: center; justify-content: center; padding: 48px; color: var(--fin-muted); font-size: 14px; }
.loader { width: 20px; height: 20px; border: 2px solid var(--fin-border); border-top-color: var(--fin-primary); border-radius: 50%; animation: spin 0.8s linear infinite; }

.dashboard { display: flex; flex-direction: column; gap: 16px; }

/* 趋势图卡片 */
.trend-card {
  padding: 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
}

.trend-controls {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.trend-controls label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--fin-muted);
}

.trend-controls select {
  padding: 8px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
  cursor: pointer;
}

.chart-container {
  width: 100%;
  height: 400px;
}

/* 警告卡片 */
.alert-card {
  display: flex;
  gap: 14px;
  padding: 16px 20px;
  background: #fff7e6;
  border: 1.5px solid #ffa940;
  border-radius: 12px;
}
.alert-icon { font-size: 24px; }
.alert-content { flex: 1; }
.alert-title { font-size: 14px; font-weight: 600; color: #d46b08; margin-bottom: 4px; }
.alert-desc { font-size: 13px; color: #873800; line-height: 1.5; }

/* 数据源网格 */
.sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.source-card {
  padding: 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
  transition: all 0.15s;
}
.source-card.degraded {
  border-color: #ff7a45;
  background: #fff2e8;
}
.source-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }

.source-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1.5px solid var(--fin-border);
}

.source-name {
  display: flex;
  align-items: center;
  gap: 8px;
}
.source-icon { font-size: 20px; }
.source-title { font-size: 16px; font-weight: 700; color: var(--fin-text); }

.source-status {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 20px;
}

.metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.metric-label {
  font-size: 12px;
  color: var(--fin-muted);
  font-weight: 600;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--fin-text);
}
.metric-value.small { font-size: 12px; font-weight: 500; }
.metric-value.good { color: #52c41a; }
.metric-value.warning { color: #faad14; }
.metric-value.bad { color: #ff4d4f; }

.metric-value .success { color: #52c41a; }
.metric-value .failure { color: #ff4d4f; }

/* 元数据 */
.meta-footer {
  display: flex;
  gap: 20px;
  padding: 14px 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 10px;
  font-size: 12px;
  color: var(--fin-muted);
}
.meta-item { display: flex; align-items: center; gap: 6px; }

@media (max-width: 768px) {
  .sources-grid { grid-template-columns: 1fr; }
  .meta-footer { flex-direction: column; gap: 8px; }
}
</style>
