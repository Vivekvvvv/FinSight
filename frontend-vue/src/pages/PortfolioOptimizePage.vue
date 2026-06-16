<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { http } from '@/api/client';
import * as echarts from 'echarts';

interface FrontierPoint { return: number; volatility: number; sharpe: number }
interface PortfolioResult {
  label: string;
  weights: Record<string, number>;
  expected_annual_return: number;
  annual_volatility: number;
  sharpe_ratio: number;
}
interface OptimizeResult {
  tickers: string[];
  efficient_frontier: FrontierPoint[];
  max_sharpe_portfolio: PortfolioResult;
  min_vol_portfolio: PortfolioResult;
  equal_weight_baseline: { label: string; expected_annual_return: number; annual_volatility: number; sharpe_ratio: number };
  correlation_matrix: { tickers: string[]; data: number[][] };
  warnings?: string[];
}

const tickerInput = ref('600519.SS\n000858.SZ\n601318.SS');
const riskFreeRate = ref(0.02);
const nSim = ref(2000);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const result = ref<OptimizeResult | null>(null);
const activeTab = ref<'max_sharpe' | 'min_vol'>('max_sharpe');

const frontierEl = ref<HTMLElement | null>(null);
const corrEl     = ref<HTMLElement | null>(null);
let frontierChart: echarts.ECharts | null = null;
let corrChart: echarts.ECharts | null = null;

async function run() {
  const tickers = tickerInput.value.split(/[\n,，\s]+/).map(t => t.trim()).filter(Boolean);
  if (tickers.length < 2) { errorMsg.value = '至少输入2只股票'; return; }
  loading.value = true;
  errorMsg.value = null;
  result.value = null;
  try {
    const { data } = await http.post('/api/portfolio/optimize', {
      tickers,
      risk_free_rate: riskFreeRate.value,
      n_simulations: nSim.value,
    });
    result.value = data;
    await nextTick();
    renderFrontier();
    renderCorr();
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '优化失败';
  } finally {
    loading.value = false;
  }
}

function renderFrontier() {
  if (!frontierEl.value || !result.value) return;
  if (!frontierChart) frontierChart = echarts.init(frontierEl.value);

  const pts = result.value.efficient_frontier;
  const ms  = result.value.max_sharpe_portfolio;
  const mv  = result.value.min_vol_portfolio;
  const eq  = result.value.equal_weight_baseline;

  frontierChart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        if (p.seriesName === '有效前沿') return `波动率: ${p.data[0]}%<br/>收益率: ${p.data[1]}%<br/>夏普: ${p.data[2]}`;
        return `${p.seriesName}<br/>波动率: ${p.data[0]}%<br/>收益率: ${p.data[1]}%<br/>夏普: ${p.data[2]}`;
      },
    },
    legend: { textStyle: { color: '#999' } },
    xAxis: { type: 'value', name: '年化波动率(%)', nameTextStyle: { color: '#666' }, axisLabel: { color: '#666' }, splitLine: { lineStyle: { color: '#333', type: 'dashed' } } },
    yAxis: { type: 'value', name: '年化收益率(%)', nameTextStyle: { color: '#666' }, axisLabel: { color: '#666' }, splitLine: { lineStyle: { color: '#333', type: 'dashed' } } },
    series: [
      {
        name: '有效前沿',
        type: 'scatter',
        data: pts.map(p => [p.volatility, p.return, p.sharpe]),
        symbolSize: 4,
        itemStyle: {
          color: (p: any) => {
            const s = p.data[2];
            const t = Math.min(Math.max((s + 0.5) / 3, 0), 1);
            const r = Math.round(84 + (91 - 84) * t);
            const g = Math.round(112 + (204 - 112) * t);
            const b = Math.round(198 + (117 - 198) * t);
            return `rgba(${r},${g},${b},0.6)`;
          },
        },
      },
      {
        name: '最大夏普',
        type: 'scatter',
        data: [[ms.annual_volatility, ms.expected_annual_return, ms.sharpe_ratio]],
        symbolSize: 18,
        symbol: 'star',
        itemStyle: { color: '#f56c6c' },
        label: { show: true, formatter: '最大夏普', position: 'top', color: '#f56c6c', fontSize: 11 },
      },
      {
        name: '最小波动',
        type: 'scatter',
        data: [[mv.annual_volatility, mv.expected_annual_return, mv.sharpe_ratio]],
        symbolSize: 18,
        symbol: 'diamond',
        itemStyle: { color: '#fac858' },
        label: { show: true, formatter: '最小波动', position: 'top', color: '#fac858', fontSize: 11 },
      },
      {
        name: '等权基准',
        type: 'scatter',
        data: [[eq.annual_volatility, eq.expected_annual_return, eq.sharpe_ratio]],
        symbolSize: 14,
        symbol: 'rect',
        itemStyle: { color: '#999' },
        label: { show: true, formatter: '等权', position: 'top', color: '#999', fontSize: 11 },
      },
    ],
  } as any);
}

function renderCorr() {
  if (!corrEl.value || !result.value) return;
  if (!corrChart) corrChart = echarts.init(corrEl.value);

  const { tickers, data } = result.value.correlation_matrix;
  const cells: [number, number, number][] = [];
  for (let i = 0; i < tickers.length; i++) {
    for (let j = 0; j < tickers.length; j++) {
      cells.push([j, i, parseFloat(data[i][j].toFixed(2))]);
    }
  }

  corrChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { formatter: (p: any) => `${tickers[p.data[1]]} × ${tickers[p.data[0]]}: ${p.data[2]}` },
    xAxis: { type: 'category', data: tickers, axisLabel: { color: '#888', rotate: 30 } },
    yAxis: { type: 'category', data: tickers, axisLabel: { color: '#888' } },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#f56c6c', '#fff', '#5470c6'] }, textStyle: { color: '#888' } },
    series: [{
      type: 'heatmap',
      data: cells,
      label: { show: true, formatter: (p: any) => p.data[2], fontSize: 11 },
    }],
  } as any);
}

function handleResize() { frontierChart?.resize(); corrChart?.resize(); }

const activePortfolio = computed(() =>
  activeTab.value === 'max_sharpe' ? result.value?.max_sharpe_portfolio : result.value?.min_vol_portfolio
);

import { computed, nextTick } from 'vue';

onMounted(() => window.addEventListener('resize', handleResize));
onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  frontierChart?.dispose();
  corrChart?.dispose();
});
</script>

<template>
  <div class="optimize-page">
    <header class="page-header">
      <h2>组合优化</h2>
      <p class="muted">马科维茨均值方差模型，寻找最大夏普比率与最小波动率组合</p>
    </header>

    <section class="config-panel">
      <div class="field">
        <label>股票列表（每行一个，2-10只）</label>
        <textarea v-model="tickerInput" rows="5" :disabled="loading" placeholder="600519.SS&#10;000858.SZ&#10;601318.SS" />
      </div>
      <div class="field-row">
        <div class="field-sm">
          <label>无风险利率</label>
          <input v-model.number="riskFreeRate" type="number" step="0.001" min="0" max="0.1" :disabled="loading" />
        </div>
        <div class="field-sm">
          <label>模拟次数</label>
          <select v-model.number="nSim" :disabled="loading">
            <option :value="1000">1000（快速）</option>
            <option :value="2000">2000（标准）</option>
            <option :value="5000">5000（精细）</option>
          </select>
        </div>
      </div>
      <button class="btn-run" :disabled="loading" @click="run">
        {{ loading ? '计算中...' : '▶ 开始优化' }}
      </button>
    </section>

    <section v-if="loading" class="loading-state">
      <div class="spinner" />
      <p>正在获取历史数据并运行蒙特卡洛模拟...</p>
    </section>

    <section v-if="errorMsg" class="error-banner">{{ errorMsg }}</section>

    <div v-if="result && !loading" class="results">
      <div v-if="result.warnings?.length" class="warn-banner">
        ⚠ {{ result.warnings.join(' / ') }}
      </div>

      <!-- 有效前沿图 -->
      <section class="chart-card">
        <h3>有效前沿（{{ result.tickers.length }} 只股票，{{ result.efficient_frontier.length }} 个组合）</h3>
        <div ref="frontierEl" style="width:100%;height:420px;" />
      </section>

      <!-- 组合详情 -->
      <section class="portfolio-section">
        <div class="tabs">
          <button :class="{ active: activeTab === 'max_sharpe' }" @click="activeTab = 'max_sharpe'">最大夏普比率</button>
          <button :class="{ active: activeTab === 'min_vol' }" @click="activeTab = 'min_vol'">最小波动率</button>
        </div>

        <div v-if="activePortfolio" class="portfolio-detail">
          <div class="port-metrics">
            <article class="pm-card">
              <p>年化收益</p>
              <strong :class="activePortfolio.expected_annual_return >= 0 ? 'pos' : 'neg'">
                {{ activePortfolio.expected_annual_return }}%
              </strong>
            </article>
            <article class="pm-card">
              <p>年化波动</p>
              <strong>{{ activePortfolio.annual_volatility }}%</strong>
            </article>
            <article class="pm-card">
              <p>夏普比率</p>
              <strong :class="activePortfolio.sharpe_ratio >= 1 ? 'pos' : ''">
                {{ activePortfolio.sharpe_ratio }}
              </strong>
            </article>
          </div>

          <div class="weights-grid">
            <div v-for="(w, t) in activePortfolio.weights" :key="t" class="weight-row">
              <span class="w-ticker">{{ t }}</span>
              <div class="w-bar-wrap">
                <div class="w-bar" :style="{ width: (w * 100) + '%' }" />
              </div>
              <span class="w-pct">{{ (w * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 相关系数矩阵 -->
      <section class="chart-card" v-if="result.tickers.length >= 2">
        <h3>相关系数矩阵</h3>
        <div ref="corrEl" :style="{ width: '100%', height: (result.tickers.length * 60 + 80) + 'px' }" />
      </section>

      <!-- 等权基准对比 -->
      <section class="baseline-card">
        <h3>等权基准对比</h3>
        <div class="baseline-metrics">
          <span>年化收益：<b>{{ result.equal_weight_baseline.expected_annual_return }}%</b></span>
          <span>年化波动：<b>{{ result.equal_weight_baseline.annual_volatility }}%</b></span>
          <span>夏普比率：<b>{{ result.equal_weight_baseline.sharpe_ratio }}</b></span>
        </div>
      </section>
    </div>

    <section v-if="!result && !loading && !errorMsg" class="empty-state">
      <p>输入2-10只股票，AI将自动抓取近2年历史数据并运行组合优化</p>
    </section>
  </div>
</template>

<style scoped>
.optimize-page { max-width: 1200px; margin: 0 auto; display: grid; gap: 24px; }
.page-header h2 { margin: 0; font-size: 28px; }
.page-header .muted { margin: 6px 0 0; color: var(--fin-muted); font-size: 14px; }

.config-panel {
  padding: 20px 24px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  display: grid;
  gap: 14px;
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; font-weight: 600; color: var(--fin-muted); text-transform: uppercase; letter-spacing: .06em; }
.field textarea {
  padding: 10px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
  font-family: var(--fin-mono);
  resize: vertical;
}
.field-row { display: flex; gap: 16px; }
.field-sm { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.field-sm label { font-size: 12px; font-weight: 600; color: var(--fin-muted); }
.field-sm input, .field-sm select {
  padding: 8px 12px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
}
.btn-run { justify-self: start; padding: 10px 32px; border: 0; border-radius: 12px; background: var(--fin-primary); color: white; font-size: 15px; font-weight: 700; cursor: pointer; }
.btn-run:disabled { opacity: 0.5; cursor: not-allowed; }

.loading-state { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 48px; color: var(--fin-muted); }
.spinner { width: 36px; height: 36px; border: 3px solid var(--fin-border); border-top-color: var(--fin-primary); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.error-banner { padding: 14px 18px; border: 1px solid var(--fin-error); border-radius: 12px; background: color-mix(in srgb,var(--fin-error) 10%,transparent); color: var(--fin-error); }
.warn-banner { padding: 12px 16px; border: 1px solid var(--fin-warning); border-radius: 12px; background: color-mix(in srgb,var(--fin-warning) 10%,transparent); color: var(--fin-warning); font-size: 13px; }

.results { display: grid; gap: 24px; }

.chart-card, .portfolio-section, .baseline-card {
  padding: 20px 24px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}
.chart-card h3, .portfolio-section h3, .baseline-card h3 { margin: 0 0 16px; font-size: 17px; }

.tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tabs button {
  padding: 7px 18px;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  color: var(--fin-text-2);
  cursor: pointer;
  font-size: 13px;
}
.tabs button.active { background: var(--fin-primary); color: white; border-color: var(--fin-primary); }

.port-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.pm-card { padding: 14px; border: 1px solid var(--fin-border); border-radius: 14px; background: var(--fin-card); }
.pm-card p { margin: 0 0 6px; font-size: 12px; color: var(--fin-muted); }
.pm-card strong { font-size: 20px; }
.pos { color: var(--fin-success); }
.neg { color: var(--fin-error); }

.weights-grid { display: grid; gap: 10px; }
.weight-row { display: grid; grid-template-columns: 120px 1fr 60px; align-items: center; gap: 12px; }
.w-ticker { font-family: var(--fin-mono); font-size: 13px; color: var(--fin-text-2); }
.w-bar-wrap { height: 8px; background: var(--fin-card-inset); border-radius: 4px; overflow: hidden; }
.w-bar { height: 100%; background: var(--fin-primary); border-radius: 4px; transition: width .4s; }
.w-pct { font-size: 13px; font-weight: 600; color: var(--fin-text); text-align: right; }

.baseline-metrics { display: flex; gap: 24px; flex-wrap: wrap; }
.baseline-metrics span { font-size: 14px; color: var(--fin-text-2); }
.baseline-metrics b { color: var(--fin-text); }

.empty-state { padding: 60px; text-align: center; color: var(--fin-muted); }

@media (max-width: 768px) {
  .port-metrics { grid-template-columns: 1fr 1fr; }
  .weight-row { grid-template-columns: 90px 1fr 48px; }
}
</style>
