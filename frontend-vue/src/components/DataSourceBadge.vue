<script setup lang="ts">
import { computed } from 'vue';
import type { EvidenceInfo } from '@/api/types';

const props = withDefaults(defineProps<{
  evidence?: EvidenceInfo | null;
  source?: string | null;
  asOf?: string | null;
  freshnessStatus?: EvidenceInfo['freshnessStatus'] | string | null;
  fallbackLevel?: number | null;
  compact?: boolean;
  label?: string;
}>(), {
  evidence: null,
  source: null,
  asOf: null,
  freshnessStatus: null,
  fallbackLevel: null,
  compact: false,
  label: '数据源',
});

const source = computed(() => props.source ?? props.evidence?.source ?? 'unknown');
const asOf = computed(() => props.asOf ?? props.evidence?.asOf ?? null);
const freshness = computed(() => props.freshnessStatus ?? props.evidence?.freshnessStatus ?? 'unknown');
const fallbackLevel = computed(() => props.fallbackLevel ?? props.evidence?.fallbackLevel ?? null);

const tone = computed(() => {
  if (freshness.value === 'live') return 'live';
  if (freshness.value === 'demo') return 'demo';
  if (freshness.value === 'cached' || freshness.value === 'fallback' || freshness.value === 'delayed_15min') return 'fallback';
  if (freshness.value === 'stale') return 'stale';
  return 'unknown';
});

const sourceLabel = computed(() => {
  const value = String(source.value || 'unknown').toLowerCase();
  const labels: Record<string, string> = {
    demo: 'Demo 演示',
    static_market_demo: 'Demo 候选池',
    today_workspace: '今日工作台',
    'today-workspace': '今日工作台',
    dossier_aggregate: '研究档案聚合',
    'dossier-aggregate': '研究档案聚合',
    fmp_stock_screener: 'FMP 筛选器',
    alpha_vantage_top_movers: 'Alpha Vantage',
    yfinance_popular: 'yfinance 热门池',
    baostock: 'BaoStock',
    yfinance: 'yfinance',
    cache: '本地缓存',
    cached: '本地缓存',
    eastmoney: '东方财富',
    eastmoney_quote: '东方财富行情',
    tencent: '腾讯行情',
    tools_bridge: '行情工具链',
    financials: '财务源',
    quote: '报价源',
    kline: 'K 线源',
    live: '实时源',
    avg_cost_fallback: '成本价兜底',
    unavailable: '价格不可用',
    mock: '测试数据',
    unknown: '未知来源',
  };
  return labels[value] || source.value || '未知来源';
});

const freshnessLabel = computed(() => {
  const value = String(freshness.value || 'unknown');
  const labels: Record<string, string> = {
    live: 'Live',
    delayed_15min: '延迟 15 分钟',
    fallback: 'Fallback',
    cached: 'Cached',
    stale: 'Stale',
    demo: 'Demo',
    unknown: 'Unknown',
  };
  return labels[value] || value;
});

const asOfLabel = computed(() => {
  if (!asOf.value) return '';
  const parsed = new Date(asOf.value);
  if (Number.isNaN(parsed.getTime())) return String(asOf.value);
  return parsed.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
});
</script>

<template>
  <span class="data-source-badge" :class="[`tone-${tone}`, { compact }]">
    <span class="dot" />
    <span v-if="!compact" class="label">{{ label }}</span>
    <strong>{{ freshnessLabel }}</strong>
    <span>{{ sourceLabel }}</span>
    <span v-if="fallbackLevel !== null" class="level">L{{ fallbackLevel }}</span>
    <time v-if="asOfLabel && !compact">{{ asOfLabel }}</time>
  </span>
</template>

<style scoped>
.data-source-badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: fit-content;
  max-width: 100%;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  padding: 7px 10px;
  background: var(--fin-card-inset);
  color: var(--fin-text-2);
  font-size: 12px;
  font-weight: 850;
  line-height: 1;
  white-space: nowrap;
}

.data-source-badge.compact {
  padding: 6px 9px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--fin-muted);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--fin-muted) 16%, transparent);
}

.label,
time,
.level {
  color: var(--fin-muted);
}

strong {
  color: var(--fin-text);
}

.tone-live .dot {
  background: var(--fin-success);
  box-shadow: 0 0 0 4px var(--fin-success-soft);
}

.tone-demo .dot {
  background: var(--fin-info);
  box-shadow: 0 0 0 4px var(--fin-info-soft);
}

.tone-fallback .dot {
  background: var(--fin-warning);
  box-shadow: 0 0 0 4px var(--fin-warning-soft);
}

.tone-stale .dot {
  background: var(--fin-danger);
  box-shadow: 0 0 0 4px var(--fin-danger-soft);
}
</style>
