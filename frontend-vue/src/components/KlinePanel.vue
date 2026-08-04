<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { BarChart, CandlestickChart, LineChart } from 'echarts/charts';
import {
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';
import { apiClient } from '@/api/client';
import type { KlinePoint, KlineResponse } from '@/api/types';
import { useThemeStore } from '@/stores/theme';

use([
  BarChart,
  CandlestickChart,
  LineChart,
  AxisPointerComponent,
  DataZoomComponent,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const props = defineProps<{
  symbol: string;
}>();

const periods = [
  { label: '1M', value: '1mo', interval: '1d' },
  { label: '3M', value: '3mo', interval: '1d' },
  { label: '6M', value: '6mo', interval: '1d' },
  { label: '1Y', value: '1y', interval: '1d' },
] as const;

const theme = useThemeStore();
const selectedPeriod = ref<(typeof periods)[number]['value']>('1mo');
const response = ref<KlineResponse | null>(null);
const loading = ref(true);
const error = ref('');
let loadTimer: ReturnType<typeof setTimeout> | null = null;
let requestController: AbortController | null = null;
let requestSequence = 0;

const normalizedSymbol = computed(() => props.symbol.trim().toUpperCase());
const selectedConfig = computed(() => (
  periods.find((item) => item.value === selectedPeriod.value) || periods[0]
));

function numberValue(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const points = computed<KlinePoint[]>(() => {
  const payload = response.value?.data;
  if (!payload) return [];
  const rows = Array.isArray(payload.kline_data) ? payload.kline_data : [];
  const normalizedRows = rows.flatMap((row) => {
    const open = numberValue(row.open);
    const high = numberValue(row.high);
    const low = numberValue(row.low);
    const close = numberValue(row.close);
    if (!row.time || open === null || high === null || low === null || close === null) return [];
    return [{
      time: String(row.time).slice(0, 10),
      open,
      high,
      low,
      close,
      volume: numberValue(row.volume),
    }];
  });
  if (normalizedRows.length > 0) return normalizedRows;

  const dates = Array.isArray(payload.dates) ? payload.dates : [];
  const values = Array.isArray(payload.values) ? payload.values : [];
  return dates.flatMap((date, index) => {
    const value = values[index];
    if (!Array.isArray(value) || value.length < 4) return [];
    const [open, close, low, high] = value.map(numberValue);
    if (open === null || close === null || low === null || high === null) return [];
    return [{ time: String(date), open, high, low, close, volume: null }];
  });
});

const linePoints = computed(() => {
  const rows = response.value?.data?.line_data;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap((row) => {
    const value = numberValue(row.value);
    if (!row.time || value === null) return [];
    return [{ time: String(row.time), value }];
  });
});
const isIntradayLine = computed(() => response.value?.data?.chart_kind === 'intraday_line' && linePoints.value.length > 0);

const latest = computed(() => points.value[points.value.length - 1] || null);
const previous = computed(() => points.value[points.value.length - 2] || null);
const priceChange = computed(() => {
  if (!latest.value || !previous.value) return null;
  const amount = latest.value.close - previous.value.close;
  const percent = previous.value.close === 0 ? 0 : amount / previous.value.close * 100;
  return { amount, percent };
});
const latestDisplayPrice = computed(() => latest.value?.close ?? linePoints.value[linePoints.value.length - 1]?.value ?? null);
const chartTitle = computed(() => isIntradayLine.value ? '当日分时' : '日 K');
const displayedPointCount = computed(() => isIntradayLine.value ? linePoints.value.length : points.value.length);

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

const chartOption = computed<EChartsOption>(() => {
  void theme.resolved;
  const axisColor = cssVar('--fin-chart-axis', '#8c887e');
  const gridColor = cssVar('--fin-chart-grid', 'rgba(28,25,23,0.08)');
  const textColor = cssVar('--fin-text', '#1a1a18');
  const tooltipBg = cssVar('--fin-card-strong', '#ffffff');
  const borderColor = cssVar('--fin-border', '#e9e6df');
  const upColor = cssVar('--fin-success', '#3d9970');
  const downColor = cssVar('--fin-danger', '#d1493f');
  const labels = points.value.map((point) => point.time);

  if (isIntradayLine.value) {
    const intradayLabels = linePoints.value.map((point) => new Date(point.time).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }));
    return {
      animationDuration: 280,
      tooltip: { trigger: 'axis', confine: true, backgroundColor: tooltipBg, borderColor, textStyle: { color: textColor, fontSize: 12 } },
      grid: { left: 54, right: 18, top: 18, bottom: 32 },
      xAxis: { type: 'category', data: intradayLabels, boundaryGap: false, axisLabel: { color: axisColor, fontSize: 10, hideOverlap: true }, axisLine: { lineStyle: { color: gridColor } }, axisTick: { show: false } },
      yAxis: { type: 'value', scale: true, position: 'right', axisLabel: { color: axisColor, fontSize: 10 }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: gridColor, type: 'dashed' } } },
      dataZoom: [{ type: 'inside', start: 0, end: 100, zoomOnMouseWheel: 'shift' }],
      series: [{ name: normalizedSymbol.value, type: 'line', showSymbol: false, lineStyle: { width: 2, color: upColor }, areaStyle: { color: `${upColor}18` }, data: linePoints.value.map((point) => point.value) }],
    };
  }

  return {
    animationDuration: 280,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: tooltipBg,
      borderColor,
      textStyle: { color: textColor, fontSize: 12 },
      axisPointer: { type: 'cross' },
    },
    grid: [
      { left: 54, right: 18, top: 14, height: '62%' },
      { left: 54, right: 18, top: '76%', height: '16%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: gridColor } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: 'category',
        gridIndex: 1,
        data: labels,
        boundaryGap: true,
        axisLine: { lineStyle: { color: gridColor } },
        axisTick: { show: false },
        axisLabel: { color: axisColor, fontSize: 10, hideOverlap: true },
      },
    ],
    yAxis: [
      {
        scale: true,
        position: 'right',
        splitNumber: 4,
        axisLabel: { color: axisColor, fontSize: 10 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
      },
      {
        scale: true,
        gridIndex: 1,
        position: 'right',
        axisLabel: { show: false },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
      },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100, zoomOnMouseWheel: 'shift' },
    ],
    series: [
      {
        name: normalizedSymbol.value,
        type: 'candlestick',
        data: points.value.map((point) => [point.open, point.close, point.low, point.high]),
        itemStyle: {
          color: upColor,
          color0: downColor,
          borderColor: upColor,
          borderColor0: downColor,
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        barMaxWidth: 9,
        data: points.value.map((point) => ({
          value: point.volume || 0,
          itemStyle: {
            color: point.close >= point.open ? `${upColor}99` : `${downColor}99`,
          },
        })),
      },
    ],
  };
});

async function loadKline(): Promise<void> {
  const symbol = normalizedSymbol.value;
  if (!/^[A-Z0-9][A-Z0-9._-]{0,19}$/.test(symbol)) {
    response.value = null;
    error.value = '请输入有效标的代码';
    loading.value = false;
    return;
  }

  const sequence = ++requestSequence;
  requestController?.abort();
  requestController = new AbortController();
  loading.value = true;
  error.value = '';
  try {
    const result = await apiClient.getKline(
      symbol,
      selectedConfig.value.value,
      selectedConfig.value.interval,
      requestController.signal,
    );
    if (sequence !== requestSequence) return;
    response.value = result;
    if (points.value.length === 0 && linePoints.value.length === 0) error.value = '当前周期暂无 K 线数据';
  } catch (loadError) {
    if (sequence !== requestSequence || (loadError instanceof DOMException && loadError.name === 'AbortError')) return;
    response.value = null;
    error.value = 'K 线暂时不可用，请稍后重试';
  } finally {
    if (sequence === requestSequence) loading.value = false;
  }
}

function scheduleLoad(): void {
  if (loadTimer) clearTimeout(loadTimer);
  loadTimer = setTimeout(() => void loadKline(), 320);
}

watch([normalizedSymbol, selectedPeriod], scheduleLoad, { immediate: true });

onUnmounted(() => {
  if (loadTimer) clearTimeout(loadTimer);
  requestController?.abort();
});
</script>

<template>
  <section
    class="kline-panel"
    aria-label="标的 K 线"
  >
    <header class="kline-head">
      <div class="instrument">
        <span class="instrument-mark">K</span>
        <div>
          <p>{{ normalizedSymbol || '—' }} · {{ chartTitle }}</p>
          <div class="price-row">
            <strong>{{ latestDisplayPrice == null ? '—' : latestDisplayPrice.toFixed(2) }}</strong>
            <span
              v-if="priceChange"
              :class="priceChange.amount >= 0 ? 'positive' : 'negative'"
            >
              {{ priceChange.amount >= 0 ? '+' : '' }}{{ priceChange.amount.toFixed(2) }}
              ({{ priceChange.percent >= 0 ? '+' : '' }}{{ priceChange.percent.toFixed(2) }}%)
            </span>
          </div>
        </div>
      </div>

      <div
        v-if="!isIntradayLine"
        class="period-control"
        role="group"
        aria-label="K 线周期"
      >
        <button
          v-for="item in periods"
          :key="item.value"
          type="button"
          :class="{ active: selectedPeriod === item.value }"
          :aria-pressed="selectedPeriod === item.value"
          @click="selectedPeriod = item.value"
        >
          {{ item.label }}
        </button>
      </div>

      <div class="source-meta">
        <span>{{ response?.data.source || '等待数据' }}</span>
        <span>{{ displayedPointCount }} 点</span>
        <span v-if="response?.cached">缓存</span>
      </div>
    </header>

    <div class="chart-stage">
      <div
        v-if="loading"
        class="chart-loading"
        aria-live="polite"
      >
        <span />
        正在加载 {{ normalizedSymbol }} K 线
      </div>
      <div
        v-else-if="error"
        class="chart-error"
        role="status"
      >
        <span>{{ error }}</span>
        <button
          type="button"
          @click="loadKline"
        >
          重试
        </button>
      </div>
      <VChart
        v-else
        class="kline-chart"
        :option="chartOption"
        autoresize
      />
    </div>
  </section>
</template>

<style scoped>
.kline-panel {
  min-height: 0;
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius);
  background: var(--fin-card);
  box-shadow: var(--fin-shadow);
  overflow: hidden;
}

.kline-head {
  min-height: 62px;
  display: grid;
  grid-template-columns: minmax(210px, auto) auto 1fr;
  align-items: center;
  gap: 18px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--fin-border);
}

.instrument,
.price-row,
.source-meta,
.period-control {
  display: flex;
  align-items: center;
}

.instrument {
  gap: 10px;
}

.instrument-mark {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--fin-border-strong);
  border-radius: var(--fin-radius-sm);
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 13px;
  font-weight: 900;
}

.instrument p {
  margin: 0;
  color: var(--fin-muted);
  font-family: var(--fin-mono);
  font-size: 10px;
  font-weight: 800;
}

.price-row {
  gap: 8px;
  line-height: 1.25;
}

.price-row strong {
  color: var(--fin-text);
  font-family: var(--fin-mono);
  font-size: 18px;
}

.price-row span,
.source-meta {
  font-family: var(--fin-mono);
  font-size: 10px;
  font-weight: 800;
}

.positive {
  color: var(--fin-success);
}

.negative {
  color: var(--fin-danger);
}

.period-control {
  padding: 3px;
  gap: 2px;
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-sm);
  background: var(--fin-card-inset);
}

.period-control button {
  min-width: 36px;
  height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--fin-muted);
  cursor: pointer;
  font-family: var(--fin-mono);
  font-size: 10px;
  font-weight: 900;
}

.period-control button.active {
  background: var(--fin-card);
  color: var(--fin-primary);
  box-shadow: 0 1px 4px rgba(28, 25, 23, 0.1);
}

.source-meta {
  justify-content: flex-end;
  gap: 10px;
  color: var(--fin-muted);
}

.source-meta span + span::before {
  content: '·';
  margin-right: 10px;
  color: var(--fin-border-strong);
}

.chart-stage {
  position: relative;
  height: 232px;
}

.kline-chart {
  width: 100%;
  height: 100%;
}

.chart-loading,
.chart-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--fin-muted);
  font-size: 13px;
}

.chart-loading span {
  width: 16px;
  height: 16px;
  border: 2px solid var(--fin-border);
  border-top-color: var(--fin-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.chart-error button {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--fin-border-strong);
  border-radius: var(--fin-radius-sm);
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  cursor: pointer;
  font-weight: 800;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 720px) {
  .kline-head {
    grid-template-columns: 1fr auto;
    gap: 8px;
    padding: 9px 10px;
  }

  .source-meta {
    display: none;
  }

  .period-control button {
    min-width: 31px;
    padding: 0 5px;
  }

  .chart-stage {
    height: 206px;
  }
}
</style>
