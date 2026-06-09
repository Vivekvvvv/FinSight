<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import { apiClient } from '@/api/client';
import type { PortfolioRiskLensResponse, RiskItem, RiskSnapshot } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import RiskTrendChart from './RiskTrendChart.vue';

const identity = useIdentityStore();
const sessionId = computed(() => identity.sessionId || 'default_session');
const userId = computed(() => identity.userId || 'default_user');

const riskLens = ref<PortfolioRiskLensResponse | null>(null);
const history = ref<RiskSnapshot[]>([]);
const selectedDays = ref(30);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const showTrends = ref(false);

async function loadRiskLens() {
  if (!sessionId.value) return;
  loading.value = true;
  errorMsg.value = null;

  try {
    const data = await apiClient.getPortfolioRiskLens(sessionId.value, userId.value);
    riskLens.value = data;
  } catch (err: any) {
    console.error('Failed to load risk lens:', err);
    errorMsg.value = err.response?.data?.error || err.message || 'Unknown error';
  } finally {
    loading.value = false;
  }
}

async function loadHistory(days: number = 30) {
  if (!sessionId.value) return;

  try {
    const data = await apiClient.getRiskLensHistory(sessionId.value, userId.value, days);
    if (data.success) {
      history.value = data.snapshots;
    }
  } catch (err: any) {
    console.error('Failed to load history:', err);
  }
}

async function toggleTrends() {
  showTrends.value = !showTrends.value;
  if (showTrends.value && history.value.length === 0) {
    await loadHistory(selectedDays.value);
  }
}

async function changeDays(days: number) {
  selectedDays.value = days;
  await loadHistory(days);
}

onMounted(() => {
  loadRiskLens();
});

const riskScoreColor = computed(() => {
  if (!riskLens.value) return 'text-gray-500';
  const score = riskLens.value.risk_score;
  if (score >= 70) return 'text-red-600';
  if (score >= 40) return 'text-amber-600';
  return 'text-green-600';
});

const riskScoreLabel = computed(() => {
  if (!riskLens.value) return '未知';
  const score = riskLens.value.risk_score;
  if (score >= 70) return '高风险';
  if (score >= 40) return '中等风险';
  if (score >= 20) return '低风险';
  return '健康';
});

function getSeverityClass(severity: string) {
  if (severity === 'high' || severity === 'critical') return 'bg-red-100 text-red-800';
  if (severity === 'medium') return 'bg-amber-100 text-amber-800';
  return 'bg-blue-100 text-blue-800';
}

function formatPercentage(value: number) {
  return (value * 100).toFixed(1) + '%';
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(value);
}
</script>

<template>
  <div class="portfolio-risk-lens">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-xl font-semibold">持仓风险透镜</h2>
      <div class="flex gap-2">
        <button
          @click="toggleTrends"
          class="px-3 py-1 text-sm bg-gray-500 text-white rounded hover:bg-gray-600"
        >
          {{ showTrends ? '隐藏趋势图' : '显示趋势图' }}
        </button>
        <button
          @click="loadRiskLens"
          :disabled="loading"
          class="px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
        >
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <!-- Trend Charts Section -->
    <div v-if="showTrends" class="mb-6 bg-white border rounded-lg p-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="font-semibold text-gray-800">历史趋势</h3>
        <div class="flex gap-2">
          <button
            v-for="d in [7, 30, 90]"
            :key="d"
            @click="changeDays(d)"
            :class="[
              'px-3 py-1 text-xs rounded',
              selectedDays === d
                ? 'bg-blue-500 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            ]"
          >
            {{ d }} 天
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div class="text-sm text-gray-600 mb-2">风险评分趋势</div>
          <RiskTrendChart
            :snapshots="history"
            metric="risk_score"
            label="风险评分"
            color="#ef4444"
          />
        </div>
        <div>
          <div class="text-sm text-gray-600 mb-2">持仓市值趋势</div>
          <RiskTrendChart
            :snapshots="history"
            metric="total_value"
            label="总市值"
            color="#3b82f6"
          />
        </div>
        <div>
          <div class="text-sm text-gray-600 mb-2">集中度风险数量</div>
          <RiskTrendChart
            :snapshots="history"
            metric="concentration_risk_count"
            label="集中度风险"
            color="#f59e0b"
          />
        </div>
        <div>
          <div class="text-sm text-gray-600 mb-2">亏损持仓数量</div>
          <RiskTrendChart
            :snapshots="history"
            metric="loss_positions_count"
            label="亏损持仓"
            color="#dc2626"
          />
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-gray-500 py-8 text-center">
      加载中...
    </div>

    <div v-else-if="errorMsg" class="bg-red-50 border border-red-200 rounded px-4 py-3 text-red-700">
      {{ errorMsg }}
    </div>

    <div v-else-if="!riskLens || !riskLens.success" class="text-gray-500 py-8 text-center">
      暂无数据
    </div>

    <div v-else class="space-y-6">
      <!-- Risk Score Overview -->
      <div class="bg-white border rounded-lg p-6">
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm text-gray-600 mb-1">风险评分</div>
            <div class="text-4xl font-bold" :class="riskScoreColor">{{ riskLens.risk_score }}</div>
            <div class="text-sm mt-1" :class="riskScoreColor">{{ riskScoreLabel }}</div>
          </div>
          <div class="text-right">
            <div class="text-sm text-gray-600 mb-1">总市值</div>
            <div class="text-2xl font-semibold">{{ formatCurrency(riskLens.total_value) }}</div>
          </div>
        </div>
      </div>

      <!-- Concentration Risk -->
      <div v-if="riskLens.concentration_risk.length > 0" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">集中度风险</h3>
        <div class="space-y-2">
          <div
            v-for="risk in riskLens.concentration_risk"
            :key="risk.id"
            class="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
            @click="$router.push(risk.target_route)"
          >
            <span class="px-2 py-0.5 text-xs rounded-full" :class="getSeverityClass(risk.severity)">
              {{ risk.severity }}
            </span>
            <div class="flex-1">
              <div class="font-medium text-sm">{{ risk.title }}</div>
              <div class="text-xs text-gray-600 mt-1">{{ risk.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Loss Positions -->
      <div v-if="riskLens.loss_positions.length > 0" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">亏损持仓</h3>
        <div class="space-y-2">
          <div
            v-for="risk in riskLens.loss_positions"
            :key="risk.id"
            class="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
            @click="$router.push(risk.target_route)"
          >
            <span class="px-2 py-0.5 text-xs rounded-full" :class="getSeverityClass(risk.severity)">
              {{ risk.severity }}
            </span>
            <div class="flex-1">
              <div class="font-medium text-sm">{{ risk.title }}</div>
              <div class="text-xs text-gray-600 mt-1">{{ risk.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Stale Research -->
      <div v-if="riskLens.stale_research.length > 0" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">过期研究</h3>
        <div class="space-y-2">
          <div
            v-for="risk in riskLens.stale_research"
            :key="risk.id"
            class="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
            @click="$router.push(risk.target_route)"
          >
            <span class="px-2 py-0.5 text-xs rounded-full" :class="getSeverityClass(risk.severity)">
              {{ risk.severity }}
            </span>
            <div class="flex-1">
              <div class="font-medium text-sm">{{ risk.title }}</div>
              <div class="text-xs text-gray-600 mt-1">{{ risk.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Missing Coverage -->
      <div v-if="riskLens.missing_coverage.length > 0" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">缺失研究覆盖</h3>
        <div class="space-y-2">
          <div
            v-for="risk in riskLens.missing_coverage"
            :key="risk.id"
            class="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
            @click="$router.push(risk.target_route)"
          >
            <span class="px-2 py-0.5 text-xs rounded-full" :class="getSeverityClass(risk.severity)">
              {{ risk.severity }}
            </span>
            <div class="flex-1">
              <div class="font-medium text-sm">{{ risk.title }}</div>
              <div class="text-xs text-gray-600 mt-1">{{ risk.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Sector Exposure -->
      <div v-if="riskLens.sector_exposure.length > 0" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">行业暴露</h3>
        <div class="space-y-2">
          <div
            v-for="exp in riskLens.sector_exposure"
            :key="exp.sector"
            class="flex items-center justify-between text-sm"
          >
            <span class="font-medium">{{ exp.sector }}</span>
            <div class="flex items-center gap-2">
              <span class="text-gray-600">{{ formatCurrency(exp.value) }}</span>
              <span class="text-gray-500">({{ formatPercentage(exp.percentage) }})</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Currency Exposure -->
      <div v-if="riskLens.currency_exposure.length > 1" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">币种暴露</h3>
        <div class="space-y-2">
          <div
            v-for="exp in riskLens.currency_exposure"
            :key="exp.currency"
            class="flex items-center justify-between text-sm"
          >
            <span class="font-medium">{{ exp.currency }}</span>
            <div class="flex items-center gap-2">
              <span class="text-gray-600">{{ formatCurrency(exp.value) }}</span>
              <span class="text-gray-500">({{ formatPercentage(exp.percentage) }})</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Market Exposure -->
      <div v-if="riskLens.market_exposure.length > 1" class="bg-white border rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">市场暴露</h3>
        <div class="space-y-2">
          <div
            v-for="exp in riskLens.market_exposure"
            :key="exp.market"
            class="flex items-center justify-between text-sm"
          >
            <span class="font-medium">{{ exp.market }}</span>
            <div class="flex items-center gap-2">
              <span class="text-gray-600">{{ formatCurrency(exp.value) }}</span>
              <span class="text-gray-500">({{ formatPercentage(exp.percentage) }})</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Next Actions -->
      <div v-if="riskLens.next_actions.length > 0" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h3 class="font-semibold mb-3 text-gray-800">推荐操作</h3>
        <div class="space-y-2">
          <div
            v-for="action in riskLens.next_actions.slice(0, 5)"
            :key="action.id"
            class="flex items-start gap-3 p-3 bg-white rounded-lg hover:shadow cursor-pointer"
            @click="$router.push(action.target_route)"
          >
            <span class="px-2 py-0.5 text-xs rounded-full" :class="getSeverityClass(action.severity)">
              {{ action.severity }}
            </span>
            <div class="flex-1">
              <div class="font-medium text-sm">{{ action.title }}</div>
              <div class="text-xs text-gray-600 mt-1">{{ action.reason }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="text-xs text-gray-500 text-center pt-2">
        数据截至：{{ new Date(riskLens.as_of).toLocaleString('zh-CN') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.portfolio-risk-lens {
  max-width: 900px;
  margin: 0 auto;
  padding: 1rem;
}
</style>
