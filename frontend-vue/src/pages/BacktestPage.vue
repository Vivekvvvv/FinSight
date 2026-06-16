<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { http } from '@/api/client';
import * as echarts from 'echarts';

// ── 类型 ──────────────────────────────────────────────────────────────────────
interface Strategy {
  id: string;
  name: string;
  description: string;
  default_params: Record<string, number>;
}

interface Metrics {
  final_equity: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  trade_count: number;
  win_rate_pct: number;
}

interface EquityPoint {
  time: string;
  equity: number;
  price: number;
  position: number;
}

interface Trade {
  type: 'buy' | 'sell';
  time: string;
  price: number;
  shares: number;
  fee: number;
  pnl?: number;
}

interface BacktestResult {
  success: boolean;
  ticker: string;
  strategy: string;
  strategy_params: Record<string, number>;
  source: string;
  period: { start: string; end: string; bars: number };
  settings: { initial_cash: number; fee_bps: number; slippage_bps: number; t_plus_one: boolean };
  metrics: Metrics;
  trades: Trade[];
  equity_curve: EquityPoint[];
}

// ── 状态 ──────────────────────────────────────────────────────────────────────
const ticker     = ref('600519.SS');
const strategy   = ref('ma_cross');
const startDate  = ref('2022-01-01');
const endDate    = ref('2024-12-31');
const initialCash = ref(100000);
const feeBps     = ref(5);
const tPlusOne   = ref(true);
const loading    = ref(false);
const errorMsg   = ref<string | null>(null);
const result     = ref<BacktestResult | null>(null);
const strategies = ref<Strategy[]>([]);
const strategyParams = ref<Record<string, number>>({});

const chartEl = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

// ── computed ──────────────────────────────────────────────────────────────────
const currentStrategy = computed(() =>
  strategies.value.find(s => s.id === strategy.value)
);

const annualizedReturn = computed(() => {
  if (!result.value) return 0;
  const { period, metrics } = result.value;
  const days = (new Date(period.end).getTime() - new Date(period.start).getTime()) / 86400000;
  const years = days / 365;
  if (years <= 0) return 0;
  return ((1 + metrics.total_return_pct / 100) ** (1 / years) - 1) * 100;
});

const sharpeRatio = computed(() => {
  if (!result.value?.equity_curve?.length) return 0;
  const curve = result.value.equity_curve;
  const returns: number[] = [];
  for (let i = 1; i < curve.length; i++) {
    returns.push((curve[i].equity - curve[i-1].equity) / curve[i-1].equity);
  }
  if (!returns.length) return 0;
  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  const std  = Math.sqrt(returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length);
  return std > 0 ? (mean / std) * Math.sqrt(252) : 0;
});

// ── 方法 ──────────────────────────────────────────────────────────────────────
function onStrategyChange() {
  const s = currentStrategy.value;
  if (s) strategyParams.value = { ...s.default_params };
}

async function loadStrategies() {
  try {
    const { data } = await http.get('/api/backtest/strategies');
    strategies.value = data.strategies || [];
    if (strategies.value.length) {
      strategy.value = strategies.value[0].id;
      onStrategyChange();
    }
  } catch { /* 静默失败 */ }
}

async function runBacktest() {
  loading.value = true;
  errorMsg.value = null;
  result.value = null;
  try {
    const { data } = await http.post('/api/backtest/run', {
      ticker: ticker.value.trim().toUpperCase(),
      strategy: strategy.value,
      params: strategyParams.value,
      start_date: startDate.value,
      end_date: endDate.value,
      initial_cash: initialCash.value,
      fee_bps: feeBps.value,
      t_plus_one: tPlusOne.value,
      market: ticker.value.includes('.SS') || ticker.value.includes('.SZ') ? 'CN' : undefined,
    });
    result.value = data;
    await nextTick();
    renderChart();
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '回测失败';
  } finally {
    loading.value = false;
  }
}

function renderChart() {
  if (!chartEl.value || !result.value) return;
  if (!chart) chart = echarts.init(chartEl.value);

  const curve = result.value.equity_curve;
  const times    = curve.map(p => p.time.slice(0, 10));
  const equities = curve.map(p => p.equity);
  const prices   = curve.map(p => p.price);
  const baseline = curve.map(p =>
    result.value!.settings.initial_cash * (p.price / curve[0].price)
  );

  // 标记买卖点
  const buyMarks = result.value.trades
    .filter(t => t.type === 'buy')
    .map(t => ({ name: 'Buy', value: t.price, xAxis: t.time.slice(0, 10), yAxis: t.price }));
  const sellMarks = result.value.trades
    .filter(t => t.type === 'sell')
    .map(t => ({ name: 'Sell', value: t.price, xAxis: t.time.slice(0, 10), yAxis: t.price }));

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['策略净值', '基准（买持）', '股价'], textStyle: { color: '#999' } },
    grid: [
      { left: 60, right: 16, top: 40, bottom: '35%' },
      { left: 60, right: 16, top: '68%', bottom: 30 },
    ],
    xAxis: [
      { type: 'category', data: times, gridIndex: 0, axisLabel: { color: '#666' }, boundaryGap: false },
      { type: 'category', data: times, gridIndex: 1, axisLabel: { color: '#666', rotate: 30 }, boundaryGap: false },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, axisLabel: { color: '#666', formatter: (v: number) => (v / 10000).toFixed(0) + 'w' }, splitLine: { lineStyle: { color: '#333', type: 'dashed' } } },
      { type: 'value', gridIndex: 1, axisLabel: { color: '#666' }, splitLine: { lineStyle: { color: '#333', type: 'dashed' } } },
    ],
    series: [
      {
        name: '策略净值',
        type: 'line',
        data: equities,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        itemStyle: { color: '#5470c6' },
        areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(84,112,198,0.25)' }, { offset: 1, color: 'rgba(84,112,198,0.02)' }] } },
        lineStyle: { width: 2 },
        showSymbol: false,
      },
      {
        name: '基准（买持）',
        type: 'line',
        data: baseline,
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        itemStyle: { color: '#91cc75' },
        lineStyle: { type: 'dashed', width: 1 },
        showSymbol: false,
      },
      {
        name: '股价',
        type: 'line',
        data: prices,
        xAxisIndex: 1,
        yAxisIndex: 1,
        smooth: true,
        itemStyle: { color: '#fac858' },
        lineStyle: { width: 1.5 },
        showSymbol: false,
        markPoint: {
          data: [
            ...buyMarks.map(m => ({ ...m, symbol: 'arrow', symbolSize: 10, itemStyle: { color: '#f56c6c' } })),
            ...sellMarks.map(m => ({ ...m, symbol: 'arrow', symbolRotate: 180, symbolSize: 10, itemStyle: { color: '#67c23a' } })),
          ],
        },
      },
    ],
  } as any);
}

function handleResize() { chart?.resize(); }

function fmt(n: number, digits = 2) {
  return n.toFixed(digits);
}
function fmtMoney(n: number) {
  return n >= 10000 ? (n / 10000).toFixed(2) + '万' : n.toFixed(2);
}

// ── 生命周期 ──────────────────────────────────────────────────────────────────
import { nextTick } from 'vue';

onMounted(() => {
  loadStrategies();
  window.addEventListener('resize', handleResize);
});
onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chart?.dispose();
});
</script>

<template>
  <div class="backtest-page">
    <header class="page-header">
      <h2>策略回测</h2>
      <p class="muted">基于历史K线验证量化策略，支持 MA 均线交叉、MACD、RSI 均值回归</p>
    </header>

    <!-- 配置面板 -->
    <section class="config-panel">
      <div class="config-grid">
        <div class="field">
          <label>股票代码</label>
          <input v-model="ticker" placeholder="600519.SS" :disabled="loading" />
        </div>
        <div class="field">
          <label>策略</label>
          <select v-model="strategy" :disabled="loading" @change="onStrategyChange">
            <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
          <span v-if="currentStrategy" class="field-hint">{{ currentStrategy.description }}</span>
        </div>
        <div class="field">
          <label>开始日期</label>
          <input v-model="startDate" type="date" :disabled="loading" />
        </div>
        <div class="field">
          <label>结束日期</label>
          <input v-model="endDate" type="date" :disabled="loading" />
        </div>
        <div class="field">
          <label>初始资金 (元)</label>
          <input v-model.number="initialCash" type="number" :disabled="loading" />
        </div>
        <div class="field">
          <label>手续费 (bps)</label>
          <input v-model.number="feeBps" type="number" min="0" :disabled="loading" />
        </div>
        <div class="field toggle-field">
          <label class="toggle-label">
            <input v-model="tPlusOne" type="checkbox" :disabled="loading" />
            T+1限制
          </label>
        </div>
      </div>

      <!-- 策略参数 -->
      <div v-if="Object.keys(strategyParams).length" class="params-row">
        <span class="params-label">策略参数</span>
        <div v-for="(val, key) in strategyParams" :key="key" class="param-field">
          <label>{{ key }}</label>
          <input v-model.number="strategyParams[key]" type="number" :disabled="loading" />
        </div>
      </div>

      <button class="btn-run" :disabled="loading" @click="runBacktest">
        {{ loading ? '回测中...' : '▶ 运行回测' }}
      </button>
    </section>

    <section v-if="errorMsg" class="error-banner">{{ errorMsg }}</section>

    <template v-if="result?.success && !loading">
      <!-- 指标卡 -->
      <section class="metrics-row">
        <article class="metric-card" :class="result.metrics.total_return_pct >= 0 ? 'pos-bg' : 'neg-bg'">
          <p class="m-label">总收益率</p>
          <strong :class="result.metrics.total_return_pct >= 0 ? 'pos' : 'neg'">
            {{ result.metrics.total_return_pct >= 0 ? '+' : '' }}{{ fmt(result.metrics.total_return_pct) }}%
          </strong>
        </article>
        <article class="metric-card">
          <p class="m-label">年化收益</p>
          <strong :class="annualizedReturn >= 0 ? 'pos' : 'neg'">
            {{ annualizedReturn >= 0 ? '+' : '' }}{{ fmt(annualizedReturn) }}%
          </strong>
        </article>
        <article class="metric-card">
          <p class="m-label">最大回撤</p>
          <strong class="neg">{{ fmt(result.metrics.max_drawdown_pct) }}%</strong>
        </article>
        <article class="metric-card">
          <p class="m-label">夏普比率</p>
          <strong :class="sharpeRatio >= 1 ? 'pos' : sharpeRatio >= 0 ? '' : 'neg'">
            {{ fmt(sharpeRatio) }}
          </strong>
        </article>
        <article class="metric-card">
          <p class="m-label">胜率</p>
          <strong>{{ fmt(result.metrics.win_rate_pct) }}%</strong>
        </article>
        <article class="metric-card">
          <p class="m-label">交易次数</p>
          <strong>{{ result.metrics.trade_count }}</strong>
        </article>
        <article class="metric-card">
          <p class="m-label">最终净值</p>
          <strong>{{ fmtMoney(result.metrics.final_equity) }}</strong>
        </article>
        <article class="metric-card">
          <p class="m-label">数据点</p>
          <strong>{{ result.period.bars }}</strong>
          <span class="m-sub">{{ result.period.start.slice(0,10) }} ~ {{ result.period.end.slice(0,10) }}</span>
        </article>
      </section>

      <!-- 权益曲线图 -->
      <section class="chart-card">
        <h3>权益曲线 vs 基准（买入持有）</h3>
        <div ref="chartEl" style="width:100%;height:480px;" />
      </section>

      <!-- 交易记录 -->
      <section class="trades-card" v-if="result.trades.length">
        <h3>交易记录 <span class="count-badge">{{ result.trades.length }} 笔</span></h3>
        <div class="trades-table-wrap">
          <table class="trades-table">
            <thead>
              <tr>
                <th>方向</th>
                <th>时间</th>
                <th>价格</th>
                <th>手数</th>
                <th>手续费</th>
                <th>盈亏</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(t, i) in result.trades" :key="i" :class="t.type">
                <td><span class="dir-tag" :class="t.type">{{ t.type === 'buy' ? '买入' : '卖出' }}</span></td>
                <td>{{ t.time.slice(0, 10) }}</td>
                <td>{{ t.price.toFixed(2) }}</td>
                <td>{{ t.shares.toFixed(2) }}</td>
                <td>{{ t.fee.toFixed(2) }}</td>
                <td v-if="t.pnl !== undefined">
                  <span :class="t.pnl! >= 0 ? 'pos' : 'neg'">
                    {{ t.pnl! >= 0 ? '+' : '' }}{{ t.pnl!.toFixed(2) }}
                  </span>
                </td>
                <td v-else>—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <section v-if="!result && !loading && !errorMsg" class="empty-state">
      <p>配置策略参数后点击「运行回测」</p>
    </section>
  </div>
</template>

<style scoped>
.backtest-page { max-width: 1300px; margin: 0 auto; display: grid; gap: 24px; }
.page-header h2 { margin: 0; font-size: 28px; }
.page-header .muted { margin: 6px 0 0; color: var(--fin-muted); font-size: 14px; }

.config-panel {
  padding: 20px 24px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  display: grid;
  gap: 16px;
}
.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
  align-items: end;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; font-weight: 600; color: var(--fin-muted); text-transform: uppercase; letter-spacing: .06em; }
.field input, .field select {
  padding: 8px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
}
.field-hint { font-size: 11px; color: var(--fin-muted); margin-top: 2px; }
.toggle-field { justify-content: flex-end; }
.toggle-label { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--fin-text-2); cursor: pointer; padding-bottom: 8px; }

.params-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  padding: 12px 14px;
  background: var(--fin-card-inset);
  border-radius: 12px;
}
.params-label { font-size: 12px; color: var(--fin-muted); white-space: nowrap; }
.param-field { display: flex; align-items: center; gap: 6px; }
.param-field label { font-size: 12px; color: var(--fin-text-2); white-space: nowrap; }
.param-field input { width: 72px; padding: 5px 8px; border: 1px solid var(--fin-border); border-radius: 8px; background: var(--fin-card); color: var(--fin-text); font-size: 13px; }

.btn-run {
  justify-self: start;
  padding: 10px 32px;
  border: 0;
  border-radius: 12px;
  background: var(--fin-primary);
  color: white;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}
.btn-run:disabled { opacity: 0.5; cursor: not-allowed; }

.error-banner { padding: 14px 18px; border: 1px solid var(--fin-error); border-radius: 12px; background: color-mix(in srgb,var(--fin-error) 10%,transparent); color: var(--fin-error); }

.metrics-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
.metric-card {
  padding: 16px 18px;
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  background: var(--fin-card-soft);
}
.pos-bg { border-color: color-mix(in srgb,var(--fin-success) 40%,transparent); }
.neg-bg { border-color: color-mix(in srgb,var(--fin-error) 40%,transparent); }
.m-label { margin: 0 0 6px; font-size: 12px; color: var(--fin-muted); }
.metric-card strong { font-size: 22px; display: block; }
.m-sub { font-size: 11px; color: var(--fin-muted); margin-top: 4px; display: block; }
.pos { color: var(--fin-success); }
.neg { color: var(--fin-error); }

.chart-card, .trades-card {
  padding: 20px 24px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}
.chart-card h3, .trades-card h3 { margin: 0 0 16px; font-size: 17px; display: flex; align-items: center; gap: 10px; }
.count-badge { padding: 2px 8px; border-radius: 999px; background: var(--fin-primary); color: white; font-size: 12px; font-weight: 600; }

.trades-table-wrap { overflow-x: auto; max-height: 400px; overflow-y: auto; }
.trades-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.trades-table th { padding: 10px 12px; text-align: left; font-size: 11px; text-transform: uppercase; color: var(--fin-muted); border-bottom: 1px solid var(--fin-border); position: sticky; top: 0; background: var(--fin-card-soft); }
.trades-table td { padding: 8px 12px; border-bottom: 1px solid var(--fin-border); color: var(--fin-text-2); }
.dir-tag { padding: 2px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
.dir-tag.buy { background: color-mix(in srgb,var(--fin-error) 15%,transparent); color: var(--fin-error); }
.dir-tag.sell { background: color-mix(in srgb,var(--fin-success) 15%,transparent); color: var(--fin-success); }

.empty-state { padding: 60px; text-align: center; color: var(--fin-muted); }

@media (max-width: 768px) {
  .config-grid { grid-template-columns: 1fr 1fr; }
  .metrics-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
