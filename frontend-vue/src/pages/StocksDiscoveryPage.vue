<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import ActionButton from '@/components/ActionButton.vue';
import DataSourceBadge from '@/components/DataSourceBadge.vue';
import EmptyState from '@/components/EmptyState.vue';
import LoadingState from '@/components/LoadingState.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import type { EvidenceInfo, ScreenerItem, ScreenerMetaResponse, ScreenerRunResponse } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import { reportFriendlyError, toFriendlyError } from '@/utils/error';

type Market = 'US' | 'CN' | 'HK';
type MarketTool = 'top-list' | 'north-flow' | 'margin';
type SignalTone = 'positive' | 'negative' | 'neutral';

interface MarketTrendRow {
  date: string;
  value: number;
}

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();

const market = ref<Market>('US');
const query = ref('');
const limit = ref(120);
const sortBy = ref('marketCap');
const sortOrder = ref<'asc' | 'desc'>('desc');
const minMarketCap = ref('');
const minPrice = ref('');
const maxPrice = ref('');
const minVolume = ref('');
const pageSize = ref(12);
const currentPage = ref(1);

const meta = ref<ScreenerMetaResponse | null>(null);
const response = ref<ScreenerRunResponse | null>(null);
const items = ref<ScreenerItem[]>([]);
const lastRunAt = ref<string | null>(null);
const loading = ref(false);
let runToken = 0;
let runController: AbortController | null = null;
const errorMsg = ref<string | null>(null);
const actionMsg = ref<string | null>(null);
const addedWatchlist = ref<Set<string>>(new Set());
const compareBasket = ref<ScreenerItem[]>([]);
const importing = ref<ScreenerItem | null>(null);
const importShares = ref('1');
const importAvgCost = ref('');
const importBusy = ref(false);
const batchBusy = ref(false);
const showChinaTools = ref(false);
const activeMarketTool = ref<MarketTool | null>(null);
const marketToolTicker = ref('600519.SS');
const marketToolLoading = ref(false);
const marketToolError = ref<string | null>(null);
const marketToolData = ref<Record<string, unknown> | null>(null);
const marketToolHistory = ref<Record<string, unknown>[]>([]);
const marketToolHistoryLoading = ref(false);
const marketToolHistoryUnavailable = ref(false);

const markets = computed<Market[]>(() => meta.value?.markets?.length ? meta.value.markets : ['US', 'CN', 'HK']);
const sortOptions = computed(() => meta.value?.sort_by?.length ? meta.value.sort_by : ['marketCap', 'price', 'volume', 'changesPercentage']);
const activeToolTitle = computed(() => {
  if (activeMarketTool.value === 'top-list') return '龙虎榜异动';
  if (activeMarketTool.value === 'north-flow') return '北向资金';
  if (activeMarketTool.value === 'margin') return '融资融券';
  return 'A股市场工具';
});

function firstValue(data: Record<string, unknown>, keys: string[]): unknown {
  return keys.map((key) => data[key]).find((value) => value !== null && value !== undefined && value !== '');
}

function numericValue(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const marketToolFields = computed(() => {
  const data = marketToolData.value || {};
  if (activeMarketTool.value === 'north-flow') {
    return [
      ['北向净流入', firstValue(data, ['north_flow', 'north_net_inflow'])],
      ['沪股通', firstValue(data, ['sh_flow', 'sh_connect'])],
      ['深股通', firstValue(data, ['sz_flow', 'sz_connect'])],
      ['时间', firstValue(data, ['time', 'date', 'trade_date'])],
    ];
  }
  if (activeMarketTool.value === 'top-list') {
    return [
      ['交易日', firstValue(data, ['date', 'trade_date'])],
      ['上榜原因', data.reason],
      ['收盘价', data.close_price],
      ['涨跌幅', data.change_percent == null ? null : `${data.change_percent}%`],
      ['净买入', data.net_buy],
      ['买入额', data.buy_amount],
      ['卖出额', data.sell_amount],
    ];
  }
  if (activeMarketTool.value === 'margin') {
    return [
      ['日期', firstValue(data, ['date', 'trade_date'])],
      ['融资余额', data.margin_balance],
      ['融资买入', data.margin_buy],
      ['融资偿还', data.margin_repay],
      ['融券余额', data.short_balance],
      ['总余额', data.total_balance],
    ];
  }
  return [];
});
const marketToolEvidence = computed<EvidenceInfo>(() => {
  const data = marketToolData.value || {};
  const source = String(firstValue(data, ['source', 'data_source']) || 'unknown');
  const sourceKey = source.toLowerCase();
  const fallbackLevel = numericValue(firstValue(data, ['fallback_level', 'fallbackLevel']));
  const isDemo = sourceKey.includes('demo') || sourceKey.includes('mock');
  const isCached = Boolean(data.cached) || sourceKey.includes('cache');
  const isFallback = Boolean(data.fallback) || (fallbackLevel !== null && fallbackLevel > 0);
  const date = firstValue(data, ['as_of', 'updated_at', 'date', 'trade_date']);
  const time = firstValue(data, ['time']);
  return {
    source,
    asOf: date && time && String(date).length <= 10 ? `${date}T${time}` : String(date || ''),
    freshnessStatus: isDemo ? 'demo' : isCached ? 'cached' : isFallback ? 'fallback' : source !== 'unknown' ? 'live' : 'unknown',
    fallbackLevel: isDemo ? 2 : isCached ? 2 : isFallback ? fallbackLevel || 1 : source !== 'unknown' ? 0 : null,
    cached: isCached,
    degraded: isDemo || isCached || isFallback,
  };
});
const marketToolSignal = computed<{ tone: SignalTone; label: string; detail: string } | null>(() => {
  const data = marketToolData.value;
  if (!data) return null;
  if (activeMarketTool.value === 'top-list') {
    const netBuy = numericValue(data.net_buy);
    if (netBuy === null) return { tone: 'neutral', label: '等待判断', detail: '当前记录缺少净买入数据。' };
    return netBuy >= 0
      ? { tone: 'positive', label: '资金净流入', detail: `榜单席位净买入 ${compact(netBuy)}，需结合上榜原因与后续量价复查。` }
      : { tone: 'negative', label: '资金净流出', detail: `榜单席位净卖出 ${compact(Math.abs(netBuy))}，需核对卖出席位与事件驱动。` };
  }
  if (activeMarketTool.value === 'north-flow') {
    const flow = numericValue(firstValue(data, ['north_flow', 'north_net_inflow']));
    if (flow === null) return { tone: 'neutral', label: '等待判断', detail: '当前快照缺少北向净流入数据。' };
    return flow >= 0
      ? { tone: 'positive', label: '市场净流入', detail: `北向资金净流入 ${compact(flow)}，仅作为市场情绪背景。` }
      : { tone: 'negative', label: '市场净流出', detail: `北向资金净流出 ${compact(Math.abs(flow))}，不应单独推导个股结论。` };
  }
  const buy = numericValue(data.margin_buy);
  const repay = numericValue(data.margin_repay);
  if (buy === null || repay === null) return { tone: 'neutral', label: '等待判断', detail: '当前快照缺少融资买入或偿还数据。' };
  const net = buy - repay;
  return net >= 0
    ? { tone: 'positive', label: '杠杆净增加', detail: `融资买入较偿还多 ${compact(net)}，需结合股价与成交量确认。` }
    : { tone: 'negative', label: '杠杆净减少', detail: `融资偿还较买入多 ${compact(Math.abs(net))}，可能反映风险偏好降温。` };
});
const marketToolTrend = computed<MarketTrendRow[]>(() => {
  const rows = marketToolHistory.value.flatMap((record) => {
    const date = firstValue(record, ['date', 'trade_date', 'time']);
    const rawValue = activeMarketTool.value === 'top-list'
      ? record.net_buy
      : activeMarketTool.value === 'north-flow'
        ? firstValue(record, ['north_flow', 'north_net_inflow'])
        : record.margin_balance;
    const value = numericValue(rawValue);
    return date && value !== null ? [{ date: String(date).slice(0, 10), value }] : [];
  });
  return rows.sort((left, right) => left.date.localeCompare(right.date)).slice(-6);
});
const marketToolTrendLabel = computed(() => {
  if (activeMarketTool.value === 'top-list') return '净买入';
  if (activeMarketTool.value === 'north-flow') return '北向净流入';
  return '融资余额';
});
const marketToolTrendDelta = computed(() => {
  const rows = marketToolTrend.value;
  if (rows.length < 2) return null;
  return rows[rows.length - 1].value - rows[rows.length - 2].value;
});
const marketToolResearchTicker = computed(() => {
  if (activeMarketTool.value === 'north-flow') return '';
  const data = marketToolData.value || {};
  return String(firstValue(data, ['symbol', 'ticker']) || marketToolTicker.value).trim().toUpperCase();
});
const screenerEvidence = computed<EvidenceInfo>(() => {
  const source = response.value?.source || (response.value?.warning ? 'static_market_demo' : 'screener');
  const isDemo = source === 'static_market_demo' || response.value?.warning === 'demo_market_fallback';
  return {
    source,
    asOf: response.value?.as_of || lastRunAt.value,
    freshnessStatus: isDemo ? 'demo' : response.value?.warning ? 'fallback' : 'live',
    fallbackLevel: isDemo ? 2 : response.value?.warning ? 1 : 0,
    degraded: isDemo || Boolean(response.value?.warning),
  };
});

const displayedItems = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((item) => `${item.symbol} ${item.name || ''} ${item.sector || ''} ${item.industry || ''}`.toLowerCase().includes(q));
});

const totalPages = computed(() => Math.max(1, Math.ceil(displayedItems.value.length / pageSize.value)));
const pageStart = computed(() => displayedItems.value.length === 0 ? 0 : (currentPage.value - 1) * pageSize.value + 1);
const pageEnd = computed(() => Math.min(displayedItems.value.length, currentPage.value * pageSize.value));
const pagedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return displayedItems.value.slice(start, start + pageSize.value);
});

function setPage(page: number) {
  currentPage.value = Math.min(Math.max(1, page), totalPages.value);
}

function nextPage() {
  setPage(currentPage.value + 1);
}

function prevPage() {
  setPage(currentPage.value - 1);
}

function num(value: string): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) && value.trim() !== '' ? parsed : undefined;
}

function compact(value: number | null | undefined): string {
  if (value == null) return '--';
  if (Math.abs(value) >= 1_000_000_000_000) return `${(value / 1_000_000_000_000).toFixed(2)}T`;
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function signedCompact(value: number): string {
  return `${value > 0 ? '+' : ''}${compact(value)}`;
}

function money(value: number | null | undefined): string {
  if (value == null) return '--';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function displayToolValue(value: unknown): string {
  if (value == null || value === '') return '--';
  if (typeof value === 'number') return compact(value);
  return String(value);
}

function marketToolErrorMessage(error: unknown): string {
  const status = (error as { response?: { status?: number } })?.response?.status;
  if (status === 404) {
    if (activeMarketTool.value === 'top-list') return `${marketToolTicker.value} 近期没有龙虎榜记录，可换一个A股代码查询。`;
    if (activeMarketTool.value === 'margin') return `${marketToolTicker.value} 暂无融资融券数据，可换一个A股代码查询。`;
    return '北向资金数据暂不可用，请稍后刷新。';
  }
  if (status === 400) return '请输入有效的A股代码，例如 600519.SS 或 000001.SZ。';
  return toFriendlyError(error, '市场工具数据暂时不可用，请稍后重试。');
}

function warningLabel(code: string | null | undefined): string {
  const labels: Record<string, string> = {
    coverage_limited_or_empty_result: '当前筛选条件下暂无覆盖结果，可放宽条件或切换市场。',
    demo_market_fallback: '当前使用内置示例股票池，适合本地演示与研究流程体验。',
    fmp_screener_unavailable: '当前 FMP key 不支持批量筛选接口，已自动切换到免费数据源。',
    live_fallback_unavailable: '实时数据源暂不可用，已切换到本地候选池。',
    empty_result: '暂无候选股票。',
  };
  return code ? labels[code] || code : '';
}

function buildFilters() {
  return {
    marketCapMoreThan: num(minMarketCap.value),
    priceMoreThan: num(minPrice.value),
    priceLowerThan: num(maxPrice.value),
    volumeMoreThan: num(minVolume.value),
    isActivelyTrading: true,
  };
}

async function loadMeta() {
  try {
    meta.value = await apiClient.getScreenerMeta();
  } catch {
    meta.value = null;
  }
}

async function run() {
  const token = ++runToken;
  runController?.abort();
  const controller = new AbortController();
  runController = controller;
  loading.value = true;
  errorMsg.value = null;
  actionMsg.value = null;
  currentPage.value = 1;
  try {
    const resp = await apiClient.runScreener({
      market: market.value,
      filters: buildFilters(),
      limit: limit.value,
      page: 1,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }, controller.signal);
    if (token !== runToken) return;
    response.value = resp;
    lastRunAt.value = new Date().toISOString();
    items.value = resp.items || resp.results || [];
    if (!resp.success && resp.error) errorMsg.value = resp.error;
  } catch (error) {
    if (token !== runToken) return;
    if ((error as { code?: string; name?: string })?.code === 'ERR_CANCELED' || (error as { name?: string })?.name === 'CanceledError') return;
    errorMsg.value = reportFriendlyError(error, '筛选失败，请放宽条件或稍后重试。');
    response.value = null;
    items.value = [];
  } finally {
    if (token === runToken) {
      loading.value = false;
      runController = null;
    }
  }
}

async function addToWatchlist(item: ScreenerItem) {
  actionMsg.value = null;
  await apiClient.addWatchlist({
    user_id: identity.userId,
    ticker: item.symbol,
    name: item.name || undefined,
    tags: [market.value, item.sector || item.exchange || '发现'].filter(Boolean),
    group: '发现池',
    priority: 3,
    watch_reason: '股票发现中心导入',
    research_status: 'new',
  });
  addedWatchlist.value = new Set([...addedWatchlist.value, item.symbol]);
  actionMsg.value = `${item.symbol} 已加入自选列表`;
}

async function addWatchlistAndNote(item: ScreenerItem) {
  try {
    await addToWatchlist(item);
    const result = await apiClient.createNote({
      session_id: identity.sessionId,
      user_id: identity.userId,
      ticker: item.symbol,
      title: `${item.symbol} 初始研究笔记`,
      content: [
        `# ${item.symbol} 初始研究笔记`,
        '',
        `来源：股票发现中心`,
        `名称：${item.name || item.symbol}`,
        `行业：${item.sector || item.industry || '待补充'}`,
        '',
        '## 待复查问题',
        '- 业务质量是否有稳定证据支持？',
        '- 估值和盈利预期是否匹配？',
        '- 最近新闻、报告或风险项是否挑战原假设？',
        '',
        '仅供研究复查，不构成投资建议。',
      ].join('\n'),
      tags: ['发现池', market.value, '初始假设'],
    });
    actionMsg.value = result.note_id
      ? `${item.symbol} 已加入自选，并创建研究笔记`
      : `${item.symbol} 已加入自选，笔记创建结果待确认`;
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '加入自选失败，请稍后重试。');
  }
}

function addToCompare(item: ScreenerItem) {
  if (compareBasket.value.some((entry) => entry.symbol === item.symbol)) return;
  compareBasket.value = [...compareBasket.value, item].slice(-4);
  actionMsg.value = `${item.symbol} 已加入对比篮子`;
}

async function batchAddWatchlist() {
  if (batchBusy.value) return;
  batchBusy.value = true;
  errorMsg.value = null;
  try {
    const candidates = displayedItems.value.slice(0, Math.min(limit.value, 12));
    for (const item of candidates) {
      if (!addedWatchlist.value.has(item.symbol)) {
        await addToWatchlist(item);
      }
    }
    actionMsg.value = `已将 ${candidates.length} 个候选标的加入发现池`;
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '创建自选和笔记失败，请稍后重试。');
  } finally {
    batchBusy.value = false;
  }
}

async function batchCreateNotes() {
  if (batchBusy.value) return;
  batchBusy.value = true;
  errorMsg.value = null;
  try {
    const candidates = displayedItems.value.slice(0, Math.min(limit.value, 8));
    for (const item of candidates) {
      await addWatchlistAndNote(item);
    }
    actionMsg.value = `已为 ${candidates.length} 个候选标的创建初始研究笔记`;
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '批量加入发现池失败，请稍后重试。');
  } finally {
    batchBusy.value = false;
  }
}

function openImport(item: ScreenerItem) {
  importing.value = item;
  importShares.value = '1';
  importAvgCost.value = item.price == null ? '' : String(item.price);
  actionMsg.value = null;
}

async function confirmImport() {
  if (!importing.value || importBusy.value) return;
  const shares = Number(importShares.value);
  const avgCost = importAvgCost.value.trim() === '' ? null : Number(importAvgCost.value);
  if (!Number.isFinite(shares) || shares <= 0) {
    errorMsg.value = '请输入大于 0 的持仓数量';
    return;
  }
  if (avgCost != null && (!Number.isFinite(avgCost) || avgCost < 0)) {
    errorMsg.value = '成本价必须为空或非负数字';
    return;
  }

  importBusy.value = true;
  errorMsg.value = null;
  try {
    const item = importing.value;
    await apiClient.upsertPosition({
      sessionId: identity.sessionId,
      ticker: item.symbol,
      shares,
      avgCost,
      name: item.name || undefined,
      tags: [market.value, item.sector || item.exchange || '发现'].filter(Boolean),
      note: '股票发现中心导入',
    });
    actionMsg.value = `${item.symbol} 已导入持仓`;
    importing.value = null;
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '持仓导入失败，请检查数量和成本价。');
  } finally {
    importBusy.value = false;
  }
}

function goDossier(symbol: string) {
  void router.push(`/dossier/${encodeURIComponent(symbol)}`);
}

function selectMarket(nextMarket: Market) {
  market.value = nextMarket;
  void run();
}

function pickDefaultChinaTicker() {
  const candidate = displayedItems.value.find((item) => String(item.symbol || '').endsWith('.SS') || String(item.symbol || '').endsWith('.SZ'));
  if (candidate?.symbol) {
    marketToolTicker.value = candidate.symbol;
  }
}

async function activateMarketTool(tool: MarketTool) {
  market.value = 'CN';
  showChinaTools.value = true;
  activeMarketTool.value = tool;
  marketToolData.value = null;
  marketToolError.value = null;
  pickDefaultChinaTicker();
  void router.replace({ path: '/stocks', query: { tool } });
  if (tool !== 'north-flow' && !marketToolTicker.value.trim()) {
    marketToolTicker.value = '600519.SS';
  }
  await loadMarketTool();
}

let marketToolSeq = 0;

function loadMarketToolHistory(tool: MarketTool, ticker: string): Promise<Record<string, unknown>> {
  if (tool === 'top-list') return apiClient.getTopListHistory(ticker, 7);
  if (tool === 'north-flow') return apiClient.getNorthFlowHistory(30);
  return apiClient.getMarginTradingHistory(ticker, 30);
}

async function loadMarketTool() {
  if (!activeMarketTool.value) return;
  const seq = ++marketToolSeq;
  const tool = activeMarketTool.value;
  const ticker = marketToolTicker.value.trim() || '600519.SS';
  marketToolLoading.value = true;
  marketToolError.value = null;
  marketToolData.value = null;
  marketToolHistory.value = [];
  marketToolHistoryLoading.value = true;
  marketToolHistoryUnavailable.value = false;
  try {
    const currentRequest = tool === 'north-flow'
      ? apiClient.getNorthFlow()
      : tool === 'top-list'
        ? apiClient.getTopList(ticker)
        : apiClient.getMarginTrading(ticker);
    const historyRequest = loadMarketToolHistory(tool, ticker).then(
      (value) => ({ ok: true as const, value }),
      () => ({ ok: false as const }),
    );
    const data = await currentRequest;
    if (seq !== marketToolSeq) return;
    marketToolData.value = data;
    marketToolLoading.value = false;
    const historyResult = await historyRequest;
    if (seq !== marketToolSeq) return;
    if (historyResult.ok) {
      marketToolHistory.value = Array.isArray(historyResult.value.records)
        ? historyResult.value.records.filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object'))
        : [];
    } else {
      marketToolHistoryUnavailable.value = true;
    }
  } catch (error) {
    if (seq !== marketToolSeq) return;
    marketToolError.value = marketToolErrorMessage(error);
  } finally {
    if (seq === marketToolSeq) {
      marketToolLoading.value = false;
      marketToolHistoryLoading.value = false;
    }
  }
}

onMounted(async () => {
  await loadMeta();
  await run();
  const tool = String(route.query.tool || '') as MarketTool;
  if (['top-list', 'north-flow', 'margin'].includes(tool)) {
    await activateMarketTool(tool);
  }
});

watch([query, pageSize], () => {
  currentPage.value = 1;
});

watch(displayedItems, () => {
  if (currentPage.value > totalPages.value) {
    currentPage.value = totalPages.value;
  }
});
</script>

<template>
  <section class="stocks-page">
    <div class="hero page-card">
      <div>
        <p class="kicker">
          STOCK DISCOVERY
        </p>
        <h2>股票发现中心</h2>
        <p>从市场筛选可研究标的，一键加入自选、创建研究笔记或进入档案；这里只提供研究入口，不提供买卖建议。</p>
      </div>
      <DataSourceBadge
        class="hero-source"
        :evidence="screenerEvidence"
      />
      <div class="hero-stat">
        <strong>{{ displayedItems.length }}</strong>
        <span>当前候选</span>
      </div>
    </div>

    <section class="filters page-card">
      <div
        class="market-tabs"
        aria-label="市场切换"
      >
        <button
          v-for="m in markets"
          :key="m"
          :class="{ active: market === m }"
          @click="selectMarket(m)"
        >
          {{ m }}
        </button>
      </div>
      <label>
        搜索
        <input
          v-model="query"
          placeholder="代码、名称、行业"
        >
      </label>
      <label>
        排序
        <select
          v-model="sortBy"
          @change="run"
        >
          <option
            v-for="opt in sortOptions"
            :key="opt"
            :value="opt"
          >{{ opt }}</option>
        </select>
      </label>
      <label>
        顺序
        <select
          v-model="sortOrder"
          @change="run"
        >
          <option value="desc">从高到低</option>
          <option value="asc">从低到高</option>
        </select>
      </label>
      <label>
        数量
        <select
          v-model.number="limit"
          @change="run"
        >
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="30">30</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="120">120</option>
          <option :value="200">200</option>
        </select>
      </label>
      <label>
        最小市值
        <input
          v-model="minMarketCap"
          inputmode="numeric"
          placeholder="如 10000000000"
          @keyup.enter="run"
        >
      </label>
      <label>
        价格区间
        <div class="range-fields">
          <input
            v-model="minPrice"
            inputmode="decimal"
            placeholder="最低"
            @keyup.enter="run"
          >
          <input
            v-model="maxPrice"
            inputmode="decimal"
            placeholder="最高"
            @keyup.enter="run"
          >
        </div>
      </label>
      <label>
        最小成交量
        <input
          v-model="minVolume"
          inputmode="numeric"
          placeholder="如 1000000"
          @keyup.enter="run"
        >
      </label>
      <ActionButton
        :loading="loading"
        loading-text="筛选中..."
        @click="run"
      >
        运行筛选
      </ActionButton>
    </section>

    <p
      v-if="response?.capability_note"
      class="notice"
    >
      {{ response.capability_note }}
    </p>
    <p
      v-if="response?.warning"
      class="notice warn"
    >
      覆盖提示：{{ warningLabel(response.warning) }}
    </p>
    <p
      v-if="actionMsg"
      class="notice success"
    >
      {{ actionMsg }}
    </p>
    <StatusBanner
      v-if="errorMsg"
      variant="error"
      :message="errorMsg"
      dismissible
      @dismiss="errorMsg = null"
    />

    <LoadingState
      v-if="loading && displayedItems.length === 0"
      label="正在筛选候选股票..."
    />
    <EmptyState
      v-else-if="displayedItems.length === 0"
      title="暂无候选股票"
      hint="可以放宽筛选条件，或切换市场后重新运行筛选。"
      compact
    />

    <section
      v-else
      class="results-shell"
    >
      <div class="results-head page-card">
        <div>
          <p class="kicker">
            RESULTS
          </p>
          <h3>候选列表</h3>
          <span>显示 {{ pageStart }}-{{ pageEnd }} / {{ displayedItems.length }}，减少长页面滚动。</span>
        </div>
        <div
          class="pager"
          aria-label="候选股票分页"
        >
          <label class="page-size">
            每页
            <select v-model.number="pageSize">
              <option :value="6">6</option>
              <option :value="9">9</option>
              <option :value="12">12</option>
            </select>
          </label>
          <button
            type="button"
            :disabled="currentPage <= 1"
            @click="prevPage"
          >
            上一页
          </button>
          <strong>第 {{ currentPage }} / {{ totalPages }} 页</strong>
          <button
            type="button"
            :disabled="currentPage >= totalPages"
            @click="nextPage"
          >
            下一页
          </button>
        </div>
      </div>

      <div class="stock-grid">
        <article
          v-for="item in pagedItems"
          :key="item.symbol"
          class="stock-card page-card"
        >
          <div class="stock-head">
            <div>
              <span class="symbol">{{ item.symbol }}</span>
              <h3>{{ item.name || item.symbol }}</h3>
            </div>
            <strong :class="Number(item.change_percent || 0) >= 0 ? 'gain' : 'loss'">
              {{ item.change_percent == null ? '--' : `${item.change_percent > 0 ? '+' : ''}${item.change_percent.toFixed(2)}%` }}
            </strong>
          </div>
          <div class="meta-line">
            <span>{{ item.exchange || market }}</span>
            <span>{{ item.sector || '未分类' }}</span>
            <span>{{ item.industry || '行业待补充' }}</span>
          </div>
          <div class="metrics">
            <div><span>价格</span><strong>{{ money(item.price) }}</strong></div>
            <div><span>市值</span><strong>{{ compact(item.market_cap) }}</strong></div>
            <div><span>成交量</span><strong>{{ compact(item.volume) }}</strong></div>
            <div><span>Beta</span><strong>{{ money(item.beta) }}</strong></div>
          </div>
          <div class="actions">
            <button
              :disabled="addedWatchlist.has(item.symbol)"
              @click="addToWatchlist(item)"
            >
              {{ addedWatchlist.has(item.symbol) ? '已加入' : '加入自选' }}
            </button>
            <button
              class="ghost"
              @click="goDossier(item.symbol)"
            >
              查看档案
            </button>
            <button
              class="ghost"
              @click="addWatchlistAndNote(item)"
            >
              自选+笔记
            </button>
            <button
              class="ghost"
              @click="openImport(item)"
            >
              持仓
            </button>
            <button
              class="ghost"
              @click="addToCompare(item)"
            >
              对比
            </button>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="displayedItems.length"
      class="workflow-bar page-card"
    >
      <div>
        <p class="kicker">
          RESEARCH WORKFLOW
        </p>
        <h3>候选池批量动作</h3>
        <span>把当前筛选结果转成可复查的研究资产，而不是交易建议。</span>
      </div>
      <ActionButton
        :loading="batchBusy"
        loading-text="处理中..."
        @click="batchAddWatchlist"
      >
        批量加入发现池
      </ActionButton>
      <ActionButton
        variant="secondary"
        :disabled="batchBusy"
        @click="batchCreateNotes"
      >
        批量创建初始笔记
      </ActionButton>
    </section>

    <section
      v-if="compareBasket.length"
      class="compare-basket page-card"
    >
      <div>
        <p class="kicker">
          COMPARE BASKET
        </p>
        <h3>对比篮子</h3>
      </div>
      <button
        v-for="item in compareBasket"
        :key="item.symbol"
        type="button"
        @click="goDossier(item.symbol)"
      >
        {{ item.symbol }}
      </button>
    </section>

    <section class="market-tools page-card">
      <button
        class="tools-head"
        type="button"
        @click="showChinaTools = !showChinaTools"
      >
        <span>
          <strong>A股市场工具</strong>
          <em>龙虎榜、北向资金、融资融券已下沉为辅助入口</em>
        </span>
        <b>{{ showChinaTools ? '收起' : '展开' }}</b>
      </button>
      <div
        v-if="showChinaTools"
        class="tools-grid"
      >
        <button
          type="button"
          :class="{ active: activeMarketTool === 'top-list' }"
          @click="activateMarketTool('top-list')"
        >
          <strong>龙虎榜异动</strong>
          <span>用于发现短期异动候选，后续进入标的研究复查。</span>
        </button>
        <button
          type="button"
          :class="{ active: activeMarketTool === 'north-flow' }"
          @click="activateMarketTool('north-flow')"
        >
          <strong>北向资金</strong>
          <span>作为市场情绪背景，不单独占据主导航。</span>
        </button>
        <button
          type="button"
          :class="{ active: activeMarketTool === 'margin' }"
          @click="activateMarketTool('margin')"
        >
          <strong>融资融券</strong>
          <span>用于观察杠杆变化，结论沉淀到报告或笔记。</span>
        </button>
      </div>
      <div
        v-if="activeMarketTool"
        class="tool-detail"
      >
        <div class="tool-detail-head">
          <div>
            <p class="kicker">
              A-SHARE TOOL
            </p>
            <h3>{{ activeToolTitle }}</h3>
          </div>
          <label
            v-if="activeMarketTool !== 'north-flow'"
            class="tool-symbol"
          >
            A股代码
            <input
              v-model="marketToolTicker"
              placeholder="如 600519.SS"
              @keyup.enter="loadMarketTool"
            >
          </label>
          <ActionButton
            :loading="marketToolLoading"
            loading-text="加载中..."
            @click="loadMarketTool"
          >
            刷新工具数据
          </ActionButton>
        </div>
        <StatusBanner
          v-if="marketToolError"
          variant="warning"
          :message="marketToolError"
        />
        <LoadingState
          v-else-if="marketToolLoading"
          :label="`正在读取 ${activeToolTitle} 数据...`"
          compact
        />
        <section
          v-else-if="marketToolData"
          class="tool-result"
        >
          <div class="tool-context">
            <DataSourceBadge
              :evidence="marketToolEvidence"
              label="工具数据"
            />
            <div
              v-if="marketToolSignal"
              class="signal-summary"
              :class="`tone-${marketToolSignal.tone}`"
            >
              <strong>{{ marketToolSignal.label }}</strong>
              <span>{{ marketToolSignal.detail }}</span>
            </div>
          </div>

          <div class="tool-metrics">
            <div
              v-for="field in marketToolFields"
              :key="String(field[0])"
            >
              <span>{{ field[0] }}</span>
              <strong>{{ displayToolValue(field[1]) }}</strong>
            </div>
          </div>

          <div class="tool-trend">
            <div class="trend-head">
              <div>
                <span>RECENT TREND</span>
                <strong>最近 {{ marketToolTrend.length }} 期{{ marketToolTrendLabel }}</strong>
              </div>
              <b
                v-if="marketToolTrendDelta !== null"
                :class="marketToolTrendDelta >= 0 ? 'positive' : 'negative'"
              >较上期 {{ signedCompact(marketToolTrendDelta) }}</b>
            </div>
            <div
              v-if="marketToolTrend.length"
              class="trend-rows"
            >
              <div
                v-for="row in marketToolTrend"
                :key="row.date"
              >
                <time>{{ row.date }}</time>
                <span>{{ compact(row.value) }}</span>
              </div>
            </div>
            <p v-else-if="marketToolHistoryLoading">
              正在读取历史趋势...
            </p>
            <p v-else-if="marketToolHistoryUnavailable">
              当前快照可用，历史趋势暂时不可用。
            </p>
            <p v-else>
              当前数据源暂未返回可比较的历史记录。
            </p>
          </div>

          <div
            v-if="marketToolResearchTicker"
            class="tool-next-action"
          >
            <span>下一步应结合公告、基本面与 K 线复查，不直接据此交易。</span>
            <button
              type="button"
              @click="goDossier(marketToolResearchTicker)"
            >
              研究 {{ marketToolResearchTicker }}
            </button>
          </div>
        </section>
        <EmptyState
          v-else
          title="选择工具后会在这里显示结果"
          hint="选择上方工具并点击刷新，不会跳转到新页面。"
          compact
        />
      </div>
    </section>

    <div
      v-if="importing"
      class="modal-backdrop"
      @click.self="importing = null"
    >
      <section class="import-modal page-card">
        <div class="modal-head">
          <div>
            <p class="kicker">
              IMPORT POSITION
            </p>
            <h3>导入 {{ importing.symbol }} 到持仓</h3>
          </div>
          <button
            class="icon-btn"
            @click="importing = null"
          >
            ×
          </button>
        </div>
        <p class="modal-copy">
          持仓导入需要你确认数量和成本价；FinSight 只记录研究资产，不提供交易指令。
        </p>
        <label>
          数量
          <input
            v-model="importShares"
            inputmode="decimal"
          >
        </label>
        <label>
          成本价
          <input
            v-model="importAvgCost"
            inputmode="decimal"
          >
        </label>
        <div class="modal-actions">
          <button
            class="secondary"
            @click="importing = null"
          >
            取消
          </button>
          <button
            class="primary"
            :disabled="importBusy"
            @click="confirmImport"
          >
            {{ importBusy ? '导入中...' : '确认导入' }}
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.stocks-page {
  display: grid;
  gap: 18px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding: clamp(16px, 1.8vw, 24px);
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 40%),
    radial-gradient(circle at 86% 14%, var(--fin-accent-soft), transparent 32%),
    var(--fin-card);
}

.kicker {
  margin: 0 0 6px;
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
  letter-spacing: 0.16em;
}

.hero h2 {
  margin: 0;
  font-size: clamp(28px, 3vw, 42px);
  letter-spacing: -0.06em;
}

.hero p:not(.kicker),
.modal-copy,
.hero-source {
  align-self: flex-start;
  margin-left: auto;
}

.hero-stat {
  min-width: 128px;
  min-height: 112px;
  display: grid;
  place-items: center;
  align-content: center;
  border: 1px solid var(--fin-border);
  border-radius: 24px;
  background: var(--fin-card-inset);
}

.hero-stat strong {
  font-size: 38px;
  line-height: 1;
}

.hero-stat span {
  color: var(--fin-muted);
  font-weight: 800;
}

.filters {
  display: grid;
  grid-template-columns: minmax(156px, auto) minmax(160px, 1.1fr) repeat(5, minmax(96px, 0.7fr)) minmax(88px, auto);
  gap: 10px;
  align-items: end;
  padding: 14px;
}

.market-tabs,
.meta-line,
.actions,
.pager,
.compare-basket {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.market-tabs {
  min-width: 156px;
  flex-wrap: nowrap;
}

.market-tabs button,
.primary,
.secondary,
.actions button,
.pager button,
.icon-btn,
.compare-basket button {
  border: 1px solid var(--fin-border);
  border-radius: 14px;
  padding: 11px 14px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  cursor: pointer;
  font-weight: 900;
  white-space: nowrap;
}

.market-tabs button.active,
.primary,
.actions button:first-child {
  border-color: var(--fin-primary);
  background: var(--fin-primary);
  color: var(--fin-bg);
}

label {
  display: grid;
  gap: 7px;
  color: var(--fin-muted);
  font-size: 13px;
  font-weight: 800;
}

input,
select {
  width: 100%;
  border-radius: 14px;
  padding: 9px 11px;
}

.range-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.notice {
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  padding: 12px 14px;
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
}

.notice.warn {
  color: var(--fin-warning);
  background: var(--fin-warning-soft);
}

.notice.success {
  color: var(--fin-success);
  background: var(--fin-success-soft);
}

.notice.danger {
  color: var(--fin-danger);
  background: var(--fin-danger-soft);
}

.compare-basket {
  align-items: center;
  padding: 16px;
}

.workflow-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
}

.workflow-bar > div {
  margin-right: auto;
}

.workflow-bar h3 {
  margin: 0;
}

.workflow-bar span {
  color: var(--fin-text-2);
}

.workflow-bar button {
  border: 1px solid var(--fin-primary);
  border-radius: 14px;
  padding: 9px 12px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.market-tools {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
}

.tools-head {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--fin-text);
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  text-align: left;
  cursor: pointer;
}

.tools-head span {
  display: grid;
  gap: 3px;
}

.tools-head strong {
  font-size: 16px;
}

.tools-head em,
.tools-grid span {
  color: var(--fin-muted);
  font-size: 13px;
  font-style: normal;
  line-height: 1.5;
}

.tools-head b {
  border-radius: 999px;
  padding: 5px 10px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-size: 12px;
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.tools-grid button {
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  padding: 14px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  text-align: left;
  cursor: pointer;
}

.tools-grid button:hover {
  border-color: var(--fin-border-strong);
  background: var(--fin-card-soft);
}

.tools-grid button.active {
  border-color: var(--fin-primary);
  background: var(--fin-primary-soft);
}

.tool-detail {
  display: grid;
  gap: 12px;
  border-top: 1px solid var(--fin-border);
  padding-top: 12px;
}

.tool-detail-head {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(180px, 260px) auto;
  gap: 12px;
  align-items: end;
}

.tool-detail-head h3 {
  margin: 0;
}

.tool-symbol {
  min-width: 0;
}

.tool-result {
  display: grid;
  gap: 12px;
}

.tool-context,
.tool-next-action,
.trend-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.signal-summary {
  min-width: 0;
  display: grid;
  gap: 2px;
  padding-left: 12px;
  border-left: 3px solid var(--fin-border-strong);
}

.signal-summary strong {
  color: var(--fin-text);
  font-size: 13px;
}

.signal-summary span,
.tool-next-action span,
.tool-trend p {
  color: var(--fin-muted);
  font-size: 12px;
  line-height: 1.5;
}

.signal-summary.tone-positive {
  border-left-color: var(--fin-success);
}

.signal-summary.tone-negative {
  border-left-color: var(--fin-danger);
}

.tool-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.tool-metrics div {
  min-width: 0;
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  padding: 10px;
  background: var(--fin-card-inset);
}

.tool-metrics span {
  display: block;
  color: var(--fin-muted);
  font-size: 12px;
  font-weight: 800;
}

.tool-metrics strong {
  display: block;
  overflow: hidden;
  margin-top: 4px;
  color: var(--fin-text);
  font-size: 14px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tool-trend {
  display: grid;
  gap: 9px;
  padding: 12px 0;
  border-top: 1px solid var(--fin-border);
  border-bottom: 1px solid var(--fin-border);
}

.trend-head div {
  display: grid;
  gap: 2px;
}

.trend-head span {
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 10px;
  font-weight: 900;
}

.trend-head strong {
  color: var(--fin-text);
  font-size: 13px;
}

.trend-head b {
  font-family: var(--fin-mono);
  font-size: 12px;
}

.trend-head .positive {
  color: var(--fin-success);
}

.trend-head .negative {
  color: var(--fin-danger);
}

.trend-rows {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  overflow: hidden;
}

.trend-rows div {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding: 9px 10px;
  background: var(--fin-card-inset);
}

.trend-rows div + div {
  border-left: 1px solid var(--fin-border);
}

.trend-rows time {
  overflow: hidden;
  color: var(--fin-muted);
  font-family: var(--fin-mono);
  font-size: 10px;
  text-overflow: ellipsis;
}

.trend-rows span {
  overflow: hidden;
  color: var(--fin-text);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
  text-overflow: ellipsis;
}

.tool-trend p {
  margin: 0;
}

.tool-next-action button {
  flex: 0 0 auto;
  border: 1px solid var(--fin-primary);
  border-radius: 8px;
  padding: 9px 12px;
  background: var(--fin-primary);
  color: var(--fin-bg);
  cursor: pointer;
  font-weight: 900;
}

.compare-basket h3 {
  margin: 0;
}

.results-shell {
  display: grid;
  gap: 12px;
}

.results-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 14px 16px;
}

.results-head h3 {
  margin: 0;
}

.results-head span {
  color: var(--fin-text-2);
  font-size: 13px;
}

.pager {
  align-items: center;
  justify-content: flex-end;
}

.pager strong {
  min-width: 92px;
  color: var(--fin-text);
  font-size: 13px;
  text-align: center;
}

.pager button {
  padding: 9px 12px;
  font-size: 13px;
}

.pager button:disabled {
  opacity: 0.42;
  cursor: default;
}

.page-size {
  display: flex;
  min-width: 116px;
  grid-template-columns: none;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.page-size select {
  width: 70px;
  padding: 8px 10px;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stock-card {
  display: grid;
  gap: 10px;
  padding: 14px;
}

.stock-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.symbol {
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-weight: 900;
  letter-spacing: 0.08em;
}

.stock-head h3 {
  margin: 4px 0 0;
  overflow: hidden;
  font-size: 16px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-line {
  flex-wrap: nowrap;
  overflow: hidden;
}

.meta-line span {
  min-width: 0;
  overflow: hidden;
  border-radius: 999px;
  padding: 4px 9px;
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.metrics div {
  border: 1px solid var(--fin-border);
  border-radius: 10px;
  padding: 8px;
  background: var(--fin-card-inset);
}

.metrics span {
  display: block;
  color: var(--fin-muted);
  font-size: 12px;
  font-weight: 800;
}

.metrics strong {
  display: block;
  margin-top: 2px;
  color: var(--fin-text);
  font-size: 14px;
}

.actions button {
  padding: 7px 9px;
  font-size: 12px;
}

.actions button:disabled {
  opacity: 0.72;
  cursor: default;
}

.actions .ghost {
  color: var(--fin-primary);
}

.gain {
  color: var(--fin-success);
}

.loss {
  color: var(--fin-danger);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 16px;
  background: var(--fin-overlay);
}

.import-modal {
  width: min(440px, 100%);
  max-height: min(88vh, 680px);
  overflow-y: auto;
  display: grid;
  gap: 16px;
  padding: 22px;
}

.modal-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.icon-btn {
  width: 38px;
  height: 38px;
  padding: 0;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

@media (max-width: 1600px) {
  .stock-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1280px) {
  .filters,
  .stock-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .hero,
  .filters,
  .stock-grid,
  .metrics,
  .tool-detail-head,
  .tool-metrics,
  .tools-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .results-head,
  .pager {
    justify-content: stretch;
  }

  .results-head {
    align-items: stretch;
    flex-direction: column;
  }

  .tool-context,
  .tool-next-action,
  .trend-head {
    align-items: stretch;
    flex-direction: column;
  }

  .trend-rows {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .trend-rows div:nth-child(4) {
    border-left: 0;
  }

  .trend-rows div:nth-child(n + 4) {
    border-top: 1px solid var(--fin-border);
  }

  .tool-next-action button {
    width: 100%;
  }

  .pager button,
  .pager strong,
  .page-size {
    flex: 1;
  }
}
</style>
