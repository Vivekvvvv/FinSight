<script setup lang="ts">
import { ref } from 'vue';
import { http } from '@/api/client';

interface AnalysisResult {
  ticker: string;
  status: string;
  error?: string;
  revenue_analysis?: { trend: string; yoy_growth?: string; highlight: string };
  profitability?: { gross_margin?: string; net_margin?: string; roe?: string; assessment: string };
  cash_flow?: { operating_cf?: string; free_cf?: string; quality: string };
  risk_factors?: { list: string[] };
  investment_highlights?: { list: string[] };
  overall_rating?: { score: number; label: string; summary: string };
}

const ticker = ref('600519.SS');
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const result = ref<AnalysisResult | null>(null);

async function analyze(): Promise<void> {
  if (!ticker.value.trim()) return;
  loading.value = true;
  errorMsg.value = null;
  result.value = null;
  try {
    const resp = await http.post('/api/research/financials/analyze', {
      ticker: ticker.value.trim().toUpperCase(),
    });
    result.value = resp.data;
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '分析失败';
  } finally {
    loading.value = false;
  }
}

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--fin-success)';
  if (score >= 6) return 'var(--fin-primary)';
  if (score >= 4) return 'var(--fin-warning)';
  return 'var(--fin-error)';
}
</script>

<template>
  <div class="financials-analyze-page">
    <header class="page-header">
      <h2>AI财报分析</h2>
      <p class="muted">使用LLM深度解读财报，提取营收、盈利、现金流关键指标</p>
    </header>

    <section class="control-panel">
      <div class="input-group">
        <label>股票代码</label>
        <input
          v-model="ticker"
          type="text"
          placeholder="例如: 600519.SS, AAPL"
          :disabled="loading"
          @keyup.enter="analyze"
        />
      </div>
      <button class="btn-primary" :disabled="loading" @click="analyze">
        {{ loading ? '分析中...' : '开始分析' }}
      </button>
    </section>

    <section v-if="loading" class="loading-state">
      <div class="spinner" />
      <p>正在解读财报，请稍候...</p>
    </section>

    <section v-if="errorMsg" class="error-banner">{{ errorMsg }}</section>

    <template v-if="result && result.status === 'success' && !loading">
      <!-- 综合评级 -->
      <section class="rating-card" v-if="result.overall_rating">
        <div class="rating-score" :style="{ color: scoreColor(result.overall_rating.score) }">
          {{ result.overall_rating.score }}<span class="score-max">/10</span>
        </div>
        <div class="rating-info">
          <strong>{{ result.overall_rating.label }}</strong>
          <p>{{ result.overall_rating.summary }}</p>
          <span class="ticker-badge">{{ result.ticker }}</span>
        </div>
      </section>

      <!-- 指标卡片 -->
      <section class="metrics-grid">
        <article class="metric-card" v-if="result.revenue_analysis">
          <p class="metric-title">营收分析</p>
          <strong class="trend-tag" :class="result.revenue_analysis.trend.includes('增') ? 'pos' : result.revenue_analysis.trend.includes('跌') ? 'neg' : ''">
            {{ result.revenue_analysis.trend }}
          </strong>
          <p v-if="result.revenue_analysis.yoy_growth" class="metric-detail">
            同比增速：{{ result.revenue_analysis.yoy_growth }}
          </p>
          <p class="metric-highlight">{{ result.revenue_analysis.highlight }}</p>
        </article>

        <article class="metric-card" v-if="result.profitability">
          <p class="metric-title">盈利能力</p>
          <p v-if="result.profitability.gross_margin" class="metric-detail">毛利率：{{ result.profitability.gross_margin }}</p>
          <p v-if="result.profitability.net_margin" class="metric-detail">净利率：{{ result.profitability.net_margin }}</p>
          <p v-if="result.profitability.roe" class="metric-detail">ROE：{{ result.profitability.roe }}</p>
          <p class="metric-highlight">{{ result.profitability.assessment }}</p>
        </article>

        <article class="metric-card" v-if="result.cash_flow">
          <p class="metric-title">现金流质量</p>
          <strong class="quality-tag" :class="result.cash_flow.quality === '高' ? 'pos' : result.cash_flow.quality === '低' ? 'neg' : ''">
            {{ result.cash_flow.quality }}
          </strong>
          <p v-if="result.cash_flow.operating_cf" class="metric-detail">经营现金流：{{ result.cash_flow.operating_cf }}</p>
          <p v-if="result.cash_flow.free_cf" class="metric-detail">自由现金流：{{ result.cash_flow.free_cf }}</p>
        </article>
      </section>

      <!-- 投资亮点与风险 -->
      <section class="factors-grid">
        <article class="factor-card highlights" v-if="result.investment_highlights?.list?.length">
          <h3>✨ 投资亮点</h3>
          <ul>
            <li v-for="h in result.investment_highlights.list" :key="h">{{ h }}</li>
          </ul>
        </article>

        <article class="factor-card risks" v-if="result.risk_factors?.list?.length">
          <h3>⚠️ 风险因素</h3>
          <ul>
            <li v-for="r in result.risk_factors.list" :key="r">{{ r }}</li>
          </ul>
        </article>
      </section>
    </template>

    <section v-if="result?.status === 'error'" class="error-banner">
      {{ result.error || '分析失败' }}
    </section>

    <section v-if="!result && !loading && !errorMsg" class="empty-state">
      <p>输入股票代码，AI将自动读取财报并生成深度解读</p>
    </section>
  </div>
</template>

<style scoped>
.financials-analyze-page {
  max-width: 1100px;
  margin: 0 auto;
  display: grid;
  gap: 24px;
}
.page-header h2 { margin: 0; font-size: 28px; }
.page-header .muted { margin: 6px 0 0; color: var(--fin-muted); font-size: 14px; }

.control-panel {
  display: flex;
  gap: 16px;
  align-items: flex-end;
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}
.input-group { display: flex; flex-direction: column; gap: 8px; flex: 1; max-width: 320px; }
.input-group label { font-size: 13px; font-weight: 600; color: var(--fin-text-2); }
.input-group input {
  padding: 10px 14px;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 14px;
}
.btn-primary {
  padding: 10px 28px;
  border: 0;
  border-radius: 12px;
  background: var(--fin-primary);
  color: white;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 48px;
  color: var(--fin-muted);
}
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--fin-border);
  border-top-color: var(--fin-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-banner {
  padding: 16px;
  border: 1px solid var(--fin-error);
  border-radius: 12px;
  background: color-mix(in srgb, var(--fin-error) 10%, transparent);
  color: var(--fin-error);
}

.rating-card {
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 24px 28px;
  border: 1px solid var(--fin-border);
  border-radius: 20px;
  background: var(--fin-card-soft);
}
.rating-score {
  font-size: 56px;
  font-weight: 900;
  line-height: 1;
}
.score-max { font-size: 22px; opacity: 0.6; }
.rating-info strong { font-size: 20px; }
.rating-info p { margin: 6px 0 10px; color: var(--fin-text-2); font-size: 14px; }
.ticker-badge {
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--fin-primary);
  color: white;
  font-size: 12px;
  font-weight: 700;
  font-family: var(--fin-mono);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}
.metric-card {
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.metric-title {
  margin: 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--fin-muted);
}
.trend-tag, .quality-tag {
  font-size: 18px;
  font-weight: 700;
}
.metric-detail { margin: 0; font-size: 13px; color: var(--fin-text-2); }
.metric-highlight { margin: 0; font-size: 13px; color: var(--fin-muted); }
.pos { color: var(--fin-success); }
.neg { color: var(--fin-error); }

.factors-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.factor-card {
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}
.factor-card h3 { margin: 0 0 14px; font-size: 16px; }
.factor-card ul { margin: 0; padding-left: 18px; display: grid; gap: 8px; }
.factor-card li { font-size: 14px; color: var(--fin-text-2); }
.highlights { border-color: color-mix(in srgb, var(--fin-success) 40%, transparent); }
.risks { border-color: color-mix(in srgb, var(--fin-warning) 40%, transparent); }

.empty-state {
  padding: 60px;
  text-align: center;
  color: var(--fin-muted);
}

@media (max-width: 768px) {
  .control-panel { flex-direction: column; align-items: stretch; }
  .input-group { max-width: none; }
  .factors-grid { grid-template-columns: 1fr; }
}
</style>
