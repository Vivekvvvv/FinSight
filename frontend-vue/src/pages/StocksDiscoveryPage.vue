<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { ScreenerItem, ScreenerMetaResponse, ScreenerRunResponse } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';

type Market = 'US' | 'CN' | 'HK';

const router = useRouter();
const identity = useIdentityStore();

const market = ref<Market>('US');
const query = ref('');
const limit = ref(20);
const sortBy = ref('marketCap');
const sortOrder = ref<'asc' | 'desc'>('desc');
const minMarketCap = ref('');
const minPrice = ref('');
const maxPrice = ref('');
const minVolume = ref('');

const meta = ref<ScreenerMetaResponse | null>(null);
const response = ref<ScreenerRunResponse | null>(null);
const items = ref<ScreenerItem[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const addedWatchlist = ref<Set<string>>(new Set());
const importing = ref<ScreenerItem | null>(null);
const importShares = ref('1');
const importAvgCost = ref('');
const importBusy = ref(false);
const actionMsg = ref<string | null>(null);

const markets = computed<Market[]>(() => meta.value?.markets?.length ? meta.value.markets : ['US', 'CN', 'HK']);
const sortOptions = computed(() => meta.value?.sort_by?.length ? meta.value.sort_by : ['marketCap', 'price', 'volume', 'changesPercentage']);

const displayedItems = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return items.value;
  return items.value.filter((item) => {
    const haystack = `${item.symbol} ${item.name || ''} ${item.sector || ''} ${item.industry || ''}`.toLowerCase();
    return haystack.includes(q);
  });
});

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

function money(value: number | null | undefined): string {
  if (value == null) return '--';
  return value.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

function warningLabel(code: string | null | undefined): string {
  const labels: Record<string, string> = {
    coverage_limited_or_empty_result: '当前筛选条件下暂无覆盖结果，可放宽条件或切换市场。',
    demo_market_fallback: '当前使用内置示例股票池，适合本地演示与研究流程体验。',
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
  loading.value = true;
  errorMsg.value = null;
  actionMsg.value = null;
  try {
    const payload = {
      market: market.value,
      filters: buildFilters(),
      limit: limit.value,
      page: 1,
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    };
    const resp = await apiClient.runScreener(payload);
    response.value = resp;
    items.value = resp.items || resp.results || [];
    if (!resp.success && resp.error) errorMsg.value = resp.error;
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
    response.value = null;
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function addToWatchlist(item: ScreenerItem) {
  actionMsg.value = null;
  try {
    await apiClient.addWatchlist({
      user_id: identity.userId,
      ticker: item.symbol,
      name: item.name || undefined,
      tags: [market.value, item.sector || item.exchange || '发现'].filter(Boolean),
      group: '发现池',
      priority: 3,
      watch_reason: '股票发现中心导入',
    });
    addedWatchlist.value = new Set([...addedWatchlist.value, item.symbol]);
    actionMsg.value = `${item.symbol} 已加入自选列表`;
  } catch (error) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
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
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    importBusy.value = false;
  }
}

function goDashboard(symbol: string) {
  void router.push(`/dashboard/${encodeURIComponent(symbol)}`);
}

function goTimeline(symbol: string) {
  void router.push(`/timeline/${encodeURIComponent(symbol)}`);
}

onMounted(async () => {
  await loadMeta();
  await run();
});
</script>

<template>
  <section class="stocks-page">
    <div class="hero page-card">
      <div>
        <p class="kicker">STOCK DISCOVERY</p>
        <h2>股票发现中心</h2>
        <p>从市场筛选可研究标的，一键加入自选或导入持仓；这里只提供研究入口，不提供买卖建议。</p>
      </div>
      <div class="hero-stat">
        <strong>{{ displayedItems.length }}</strong>
        <span>当前候选</span>
      </div>
    </div>

    <section class="filters page-card">
      <div class="market-tabs" aria-label="市场切换">
        <button
          v-for="m in markets"
          :key="m"
          :class="{ active: market === m }"
          @click="market = m; run()"
        >
          {{ m }}
        </button>
      </div>
      <label>
        搜索
        <input v-model="query" placeholder="代码、名称、行业">
      </label>
      <label>
        排序
        <select v-model="sortBy" @change="run">
          <option v-for="opt in sortOptions" :key="opt" :value="opt">{{ opt }}</option>
        </select>
      </label>
      <label>
        顺序
        <select v-model="sortOrder" @change="run">
          <option value="desc">从高到低</option>
          <option value="asc">从低到高</option>
        </select>
      </label>
      <label>
        数量
        <select v-model.number="limit" @change="run">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </label>
      <label>
        最小市值
        <input v-model="minMarketCap" inputmode="numeric" placeholder="如 10000000000" @keyup.enter="run">
      </label>
      <label>
        价格区间
        <div class="range-fields">
          <input v-model="minPrice" inputmode="decimal" placeholder="最低" @keyup.enter="run">
          <input v-model="maxPrice" inputmode="decimal" placeholder="最高" @keyup.enter="run">
        </div>
      </label>
      <label>
        最小成交量
        <input v-model="minVolume" inputmode="numeric" placeholder="如 1000000" @keyup.enter="run">
      </label>
      <button class="primary" :disabled="loading" @click="run">{{ loading ? '筛选中...' : '运行筛选' }}</button>
    </section>

    <p v-if="response?.capability_note" class="notice">{{ response.capability_note }}</p>
    <p v-if="response?.warning" class="notice warn">覆盖提示：{{ warningLabel(response.warning) }}</p>
    <p v-if="actionMsg" class="notice success">{{ actionMsg }}</p>
    <p v-if="errorMsg" class="notice danger">{{ errorMsg }}</p>

    <section v-if="loading" class="state-card page-card">正在拉取股票候选...</section>
    <section v-else-if="displayedItems.length === 0" class="state-card page-card">
      <strong>暂无候选股票</strong>
      <span>可放宽筛选条件，或切换到 US 市场。CN/HK 第一版可能受数据源覆盖影响。</span>
    </section>

    <section v-else class="stock-grid">
      <article v-for="item in displayedItems" :key="item.symbol" class="stock-card page-card">
        <div class="stock-head">
          <div>
            <p class="symbol">{{ item.symbol }}</p>
            <h3>{{ item.name || item.symbol }}</h3>
          </div>
          <span :class="Number(item.change_percent || 0) >= 0 ? 'gain' : 'loss'">
            {{ item.change_percent == null ? '--' : `${item.change_percent > 0 ? '+' : ''}${money(item.change_percent)}%` }}
          </span>
        </div>
        <div class="meta-line">
          <span>{{ item.exchange || market }}</span>
          <span>{{ item.sector || '未标注板块' }}</span>
          <span>{{ item.industry || item.country || '研究候选' }}</span>
        </div>
        <div class="metrics">
          <div><span>价格</span><strong>{{ money(item.price) }}</strong></div>
          <div><span>市值</span><strong>{{ compact(item.market_cap) }}</strong></div>
          <div><span>成交量</span><strong>{{ compact(item.volume) }}</strong></div>
          <div><span>Beta</span><strong>{{ money(item.beta) }}</strong></div>
        </div>
        <div class="actions">
          <button :disabled="addedWatchlist.has(item.symbol)" @click="addToWatchlist(item)">
            {{ addedWatchlist.has(item.symbol) ? '已加入自选' : '加入自选' }}
          </button>
          <button @click="openImport(item)">导入持仓</button>
          <button @click="goDashboard(item.symbol)">查看分析</button>
          <button class="ghost" @click="goTimeline(item.symbol)">时间线</button>
        </div>
      </article>
    </section>

    <div v-if="importing" class="modal-backdrop" @click.self="importing = null">
      <section class="import-modal page-card">
        <div class="modal-head">
          <div>
            <p class="kicker">PORTFOLIO IMPORT</p>
            <h3>导入 {{ importing.symbol }} 到持仓</h3>
          </div>
          <button class="icon-btn" @click="importing = null">×</button>
        </div>
        <p class="modal-copy">系统已预填最新价格作为成本参考。请确认数量和成本价；这只是持仓记录，不构成交易建议。</p>
        <label>
          持仓数量
          <input v-model="importShares" inputmode="decimal" placeholder="1">
        </label>
        <label>
          成本价
          <input v-model="importAvgCost" inputmode="decimal" placeholder="可留空">
        </label>
        <div class="modal-actions">
          <button class="primary" :disabled="importBusy" @click="confirmImport">
            {{ importBusy ? '导入中...' : '确认导入' }}
          </button>
          <button class="secondary" @click="importing = null">取消</button>
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
  padding: clamp(24px, 2.6vw, 38px);
  background:
    linear-gradient(135deg, var(--fin-primary-soft), transparent 42%),
    radial-gradient(circle at 88% 10%, var(--fin-accent-soft), transparent 32%),
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

h2,
h3,
p {
  margin: 0;
}

.hero h2 {
  font-size: clamp(34px, 4vw, 58px);
  letter-spacing: -0.06em;
}

.hero p:not(.kicker),
.modal-copy,
.state-card span {
  color: var(--fin-text-2);
}

.hero-stat {
  min-width: 160px;
  display: grid;
  place-items: center;
  align-content: center;
  border: 1px solid var(--fin-border);
  border-radius: 24px;
  background: var(--fin-card-inset);
}

.hero-stat strong {
  font-size: 48px;
  line-height: 1;
}

.hero-stat span {
  color: var(--fin-muted);
  font-weight: 800;
}

.filters {
  display: grid;
  grid-template-columns: auto minmax(180px, 1fr) repeat(5, minmax(130px, 0.75fr)) auto;
  gap: 12px;
  align-items: end;
  padding: 18px;
}

.market-tabs {
  display: flex;
  gap: 8px;
}

.market-tabs button,
.primary,
.secondary,
.actions button,
.icon-btn {
  border: 1px solid var(--fin-border);
  border-radius: 14px;
  padding: 11px 14px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  cursor: pointer;
  font-weight: 900;
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
  padding: 11px 12px;
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

.state-card {
  display: grid;
  gap: 8px;
  padding: 32px;
  text-align: center;
}

.stock-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.stock-card {
  display: grid;
  gap: 14px;
  padding: 18px;
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
  margin-top: 4px;
  font-size: 18px;
}

.meta-line,
.metrics,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-line span {
  border-radius: 999px;
  padding: 4px 9px;
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
  font-size: 12px;
  font-weight: 800;
}

.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.metrics div {
  border: 1px solid var(--fin-border);
  border-radius: 14px;
  padding: 10px;
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
  font-size: 15px;
}

.actions button {
  padding: 9px 11px;
  font-size: 13px;
}

.actions button:disabled {
  opacity: 0.72;
  cursor: default;
}

.actions .ghost {
  color: var(--fin-primary);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: grid;
  place-items: center;
  padding: 24px;
  background: var(--fin-overlay);
}

.import-modal {
  width: min(440px, 94vw);
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
  .metrics {
    grid-template-columns: 1fr;
    display: grid;
  }

  .market-tabs {
    flex-wrap: wrap;
  }
}
</style>
