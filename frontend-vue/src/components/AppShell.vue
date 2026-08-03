<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import EmptyState from '@/components/EmptyState.vue';
import IdentityPanel from '@/components/IdentityPanel.vue';
import LoadingState from '@/components/LoadingState.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import ThemeToggle from '@/components/ThemeToggle.vue';
import { useIdentityStore } from '@/stores/identity';
import type { DemoStatusResponse, PortfolioSummary, WatchlistItem } from '@/api/types';
import { usePullToRefresh } from '@/composables/usePullToRefresh';
import { reportFriendlyError } from '@/utils/error';

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();
const sidebarOpen = ref(false);
const contextOpen = ref(false);
const portfolio = ref<PortfolioSummary | null>(null);
const watchlist = ref<WatchlistItem[]>([]);
const demoStatus = ref<DemoStatusResponse | null>(null);
const contextLoading = ref(false);
const contextError = ref<string | null>(null);

const navItems = [
  { to: '/welcome', label: '今日工作台', group: '每日流程', icon: '今' },
  { to: '/dossier/AAPL', label: '标的研究', group: '研究对象', icon: '研' },
  { to: '/stocks', label: '股票发现', group: '发现候选', icon: '股' },
  { to: '/portfolio', label: '组合管理', group: '持仓复查', icon: '组' },
  { to: '/reports', label: '报告库', group: '研究资产', icon: '报' },
  { to: '/notes', label: '研究笔记', group: '证据沉淀', icon: '记' },
  { to: '/chat', label: 'AI 助手', group: '问答生成', icon: 'AI' },
];

// 移动端底部导航保留最高频 5 个入口。
const mobileNavItems = [
  { to: '/welcome', label: '今日', icon: '今' },
  { to: '/dossier/AAPL', label: '研究', icon: '研' },
  { to: '/stocks', label: '发现', icon: '股' },
  { to: '/portfolio', label: '组合', icon: '组' },
  { to: '/chat', label: '助手', icon: 'AI' },
];

const marketStrip = [
  { symbol: 'SPY', price: '639.12', change: '+0.42%' },
  { symbol: 'QQQ', price: '558.04', change: '+0.77%' },
  { symbol: 'DOW', price: '39,804', change: '+0.18%' },
  { symbol: 'VIX', price: '12.40', change: '-1.12%' },
];

const routeTitle = computed(() => {
  if (route.path.startsWith('/welcome')) return '今日工作台';
  if (route.path.startsWith('/dossier')) return '标的研究';
  if (route.path.startsWith('/stocks')) return '股票发现';
  if (route.path.startsWith('/portfolio')) return '组合管理';
  if (route.path.startsWith('/reports')) return '报告库';
  if (route.path.startsWith('/notes')) return '研究笔记';
  if (route.path.startsWith('/chat')) return 'AI 助手';
  return 'FinSight AI';
});

const totalValue = computed(() => portfolio.value?.total_value ?? 0);
const totalPnl = computed(() => portfolio.value?.total_pnl ?? 0);
const sourceComponents = computed(() => demoStatus.value?.components || []);
const missingServices = computed(() => demoStatus.value?.missing_services || []);
const sourceStatus = computed(() => {
  if (contextLoading.value && !demoStatus.value) return { label: '检测中', tone: 'unknown', detail: '状态同步' };
  if (contextError.value && !demoStatus.value) return { label: '状态异常', tone: 'warn', detail: '点击查看' };
  const status = demoStatus.value?.overall_status || (demoStatus.value?.demo_mode ? 'demo' : 'unknown');
  if (status === 'demo') return { label: 'DEMO 数据', tone: 'demo', detail: '演示数据' };
  if (status === 'live_ready') return { label: 'LIVE 数据', tone: 'live', detail: '真实源可用' };
  if (status === 'fallback_ready') return { label: 'FALLBACK 数据', tone: 'warn', detail: '备用源可用' };
  if (status === 'needs_config') return { label: '待配置', tone: 'warn', detail: '缺少 key 或服务' };
  return { label: '未知', tone: 'unknown', detail: '等待检测' };
});

function componentStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    demo: 'Demo',
    live_ready: 'Live',
    fallback_ready: 'Fallback',
    missing_key: '缺 key',
  };
  return labels[status] || status;
}

function closeSidebar() {
  sidebarOpen.value = false;
}

async function loadContext() {
  contextLoading.value = true;
  contextError.value = null;
  const results = await Promise.allSettled([
    apiClient.getPortfolioSummary(identity.sessionId),
    apiClient.listWatchlist(identity.userId),
    apiClient.getDataSourceStatus(),
  ]);
  if (results[0].status === 'fulfilled') portfolio.value = results[0].value;
  if (results[1].status === 'fulfilled') watchlist.value = results[1].value.items || [];
  if (results[2].status === 'fulfilled') demoStatus.value = results[2].value;
  else contextError.value = reportFriendlyError(results[2].reason, '数据源状态暂时不可用，请稍后刷新。');

  if (results.every((item) => item.status === 'rejected')) {
    contextError.value = '研究上下文暂时不可用，请检查本地后端是否已启动后重试。';
  }
  contextLoading.value = false;
}

onMounted(() => {
  void loadContext();
});

watch(
  () => route.query.drawer,
  (drawer) => {
    if (drawer === 'data' || drawer === 'system') contextOpen.value = true;
  },
  { immediate: true },
);

watch(contextOpen, (open) => {
  if (open && !demoStatus.value && !contextLoading.value) void loadContext();
});

const { isRefreshing, pullStyle } = usePullToRefresh(loadContext);
</script>

<template>
  <div class="app-shell">
    <aside
      class="side-rail"
      :class="{ open: sidebarOpen }"
    >
      <button
        class="brand-lockup"
        @click="router.push('/welcome')"
      >
        <img
          src="/logo.svg"
          alt="FinSight"
          class="brand-logo"
        >
        <span>
          <strong>FinSight</strong>
          <small>Research Terminal</small>
        </span>
      </button>

      <nav class="nav-stack">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          active-class="active"
          @click="closeSidebar"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <strong>
            {{ item.label }}
            <small>{{ item.group }}</small>
          </strong>
        </RouterLink>
      </nav>

      <div class="rail-card">
        <p class="rail-kicker">
          PORTFOLIO
        </p>
        <strong>{{ totalValue ? `$${totalValue.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}` : '暂无持仓' }}</strong>
        <span :class="totalPnl >= 0 ? 'pos' : 'neg'">
          {{ totalPnl >= 0 ? '+' : '' }}{{ totalPnl.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}
        </span>
      </div>

      <IdentityPanel class="identity-block" />
    </aside>

    <div class="workspace">
      <header class="terminal-bar">
        <button
          class="mobile-menu"
          type="button"
          @click="sidebarOpen = !sidebarOpen"
        >
          菜单
        </button>
        <div class="route-title">
          <p class="terminal-kicker">
            FINSIGHT TERMINAL / {{ routeTitle }}
          </p>
          <h1>{{ routeTitle }}</h1>
        </div>
        <div
          class="ticker-tape"
          aria-label="市场状态条"
        >
          <button
            v-for="item in marketStrip"
            :key="item.symbol"
            class="ticker-pill"
            type="button"
            @click="router.push(`/dossier/${item.symbol}`)"
          >
            <strong>{{ item.symbol }}</strong>
            <span>{{ item.price }}</span>
            <em :class="item.change.startsWith('+') ? 'pos' : 'neg'">{{ item.change }}</em>
          </button>
        </div>
        <button
          class="source-pill"
          :class="sourceStatus.tone"
          type="button"
          @click="contextOpen = true"
        >
          <span>{{ sourceStatus.label }}</span>
          <small>{{ sourceStatus.detail }}</small>
        </button>
        <ThemeToggle />
        <button
          class="context-button"
          type="button"
          @click="contextOpen = true"
        >
          上下文
        </button>
      </header>

      <main
        class="workspace-main"
        :style="pullStyle"
      >
        <!-- 下拉刷新指示器 -->
        <div
          v-if="isRefreshing"
          class="pull-indicator"
        >
          ↻ 刷新中...
        </div>
        <slot />
      </main>
    </div>

    <aside
      v-if="contextOpen"
      class="context-drawer open"
      aria-label="研究上下文"
    >
      <div class="drawer-head">
        <div>
          <p class="rail-kicker">
            CONTEXT
          </p>
          <strong>研究上下文</strong>
        </div>
        <button
          type="button"
          @click="contextOpen = false"
        >
          关闭
        </button>
      </div>

      <section class="context-card">
        <p class="rail-kicker">
          WATCHLIST
        </p>
        <button
          v-for="item in watchlist.slice(0, 6)"
          :key="item.ticker"
          class="watch-chip"
          type="button"
          @click="router.push(`/dossier/${item.ticker}`)"
        >
          <strong>{{ item.ticker }}</strong>
          <span>{{ item.watch_reason || item.name || '研究关注' }}</span>
        </button>
        <button
          v-if="watchlist.length === 0"
          class="empty-action"
          type="button"
          @click="router.push('/stocks')"
        >
          添加重点标的
        </button>
      </section>

      <section class="context-card">
        <p class="rail-kicker">
          RESEARCH RULE
        </p>
        <strong>只输出研究动作建议</strong>
        <span class="muted">不提供买入、卖出或收益承诺。所有结论必须可复查。</span>
        <span
          v-if="demoStatus?.demo_mode"
          class="muted demo-note"
        >
          当前为 Demo Mode：使用示例数据展示完整研究闭环。
        </span>
      </section>

      <section class="context-card data-source-card">
        <p class="rail-kicker">
          DATA SOURCE
        </p>
        <strong>数据源状态</strong>
        <p class="muted">
          这里说明当前看到的是演示数据、真实数据，还是缺少配置。
        </p>
        <StatusBanner
          v-if="contextError"
          variant="warning"
          :message="contextError"
          action-label="重试"
          @action="loadContext"
        />
        <LoadingState
          v-if="contextLoading && !demoStatus"
          label="正在检测数据源状态..."
          compact
        />
        <div
          v-else-if="sourceComponents.length"
          class="source-list"
        >
          <article
            v-for="item in sourceComponents"
            :key="item.key"
            class="source-row"
          >
            <div>
              <strong>{{ item.label }}</strong>
              <span>{{ item.detail }}</span>
              <em v-if="item.required_action">{{ item.required_action }}</em>
            </div>
            <b :class="item.status">{{ componentStatusLabel(item.status) }}</b>
          </article>
        </div>
        <EmptyState
          v-else
          title="暂无数据源状态"
          hint="状态接口返回后会在这里显示行情、AI、检索等来源。"
          compact
        />
        <p
          v-if="missingServices.length"
          class="missing-list"
        >
          缺失配置：{{ missingServices.join(' / ') }}
        </p>
      </section>
    </aside>

    <div
      v-if="sidebarOpen"
      class="mobile-mask"
      @click="closeSidebar"
    />
    <div
      v-if="contextOpen"
      class="drawer-mask"
      @click="contextOpen = false"
    />

    <!-- 移动端底部导航（<820px） -->
    <nav
      class="mobile-bottom-nav"
      aria-label="移动端导航"
    >
      <RouterLink
        v-for="item in mobileNavItems"
        :key="item.to"
        :to="item.to"
        class="mb-nav-item"
        active-class="active"
      >
        <span class="mb-icon">{{ item.icon }}</span>
        <span class="mb-label">{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  background:
    radial-gradient(circle at 8% 0%, var(--fin-accent-soft), transparent 32%),
    radial-gradient(circle at 96% 10%, var(--fin-primary-soft), transparent 30%),
    var(--fin-bg);
  color: var(--fin-text);
}

.side-rail {
  height: 100dvh;
  min-height: 0;
  border-right: 1px solid var(--fin-border);
  padding: 22px 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: color-mix(in srgb, var(--fin-bg) 90%, transparent);
  overflow: hidden;
}

.brand-lockup {
  flex-shrink: 0;
  border: 0;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0;
  cursor: pointer;
  text-align: left;
}

.brand-logo {
  width: 46px;
  height: 46px;
  border-radius: 17px;
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
}

.brand-lockup strong,
.context-card strong,
.drawer-head strong {
  display: block;
  font-size: 16px;
}

.brand-lockup small,
.muted {
  display: block;
  color: var(--fin-muted);
  font-size: 13px;
}

.nav-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 2px;
  scrollbar-gutter: stable;
}

.nav-link {
  display: grid;
  grid-template-columns: 38px 1fr;
  align-items: center;
  gap: 10px;
  padding: 12px 13px;
  border-radius: 8px;
  color: var(--fin-text-2);
  border: 1px solid transparent;
}

.nav-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--fin-card-inset);
  color: var(--fin-primary);
  font-weight: 900;
}

.nav-link small {
  display: block;
  margin-top: 2px;
  color: var(--fin-muted);
  font-size: 11px;
  font-weight: 700;
}

.rail-kicker,
.terminal-kicker {
  font-family: var(--fin-mono);
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--fin-primary);
}

.nav-link strong {
  font-size: 15px;
  letter-spacing: 0.01em;
}

.nav-link:hover,
.nav-link.active {
  color: var(--fin-text);
  border-color: var(--fin-border-strong);
  background:
    linear-gradient(90deg, var(--fin-primary-soft), transparent 80%),
    var(--fin-card-soft);
}

.rail-card,
.context-card {
  border: 1px solid var(--fin-border);
  border-radius: 22px;
  padding: 16px;
  background: var(--fin-card-soft);
}

.demo-pill,
.source-pill {
  border: 1px solid color-mix(in srgb, var(--fin-accent) 55%, transparent);
  color: var(--fin-accent);
  background: color-mix(in srgb, var(--fin-accent) 14%, transparent);
  border-radius: 999px;
  padding: 8px 11px;
  font-size: 12px;
  font-weight: 900;
  letter-spacing: .08em;
  white-space: nowrap;
}

.source-pill {
  display: grid;
  gap: 1px;
  min-width: 118px;
  border-radius: 18px;
  text-align: left;
  cursor: pointer;
}

.source-pill span {
  font-size: 12px;
}

.source-pill small {
  color: var(--fin-muted);
  font-size: 11px;
  letter-spacing: 0;
}

.source-pill.live {
  border-color: color-mix(in srgb, var(--fin-success) 55%, transparent);
  color: var(--fin-success);
  background: var(--fin-success-soft);
}

.source-pill.warn {
  border-color: color-mix(in srgb, var(--fin-warning) 55%, transparent);
  color: var(--fin-warning);
  background: var(--fin-warning-soft);
}

.source-pill.unknown {
  border-color: var(--fin-border);
  color: var(--fin-muted);
  background: var(--fin-card-soft);
}

.demo-note {
  margin-top: 8px;
  color: var(--fin-accent);
}

.data-source-card {
  display: grid;
  gap: 12px;
}

.source-list {
  display: grid;
  gap: 10px;
}

.source-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  padding: 12px;
  background: var(--fin-card-inset);
}

.source-row strong,
.source-row span,
.source-row em {
  display: block;
}

.source-row span,
.source-row em,
.missing-list {
  color: var(--fin-muted);
  font-size: 12px;
  line-height: 1.55;
}

.source-row em {
  margin-top: 4px;
  color: var(--fin-warning);
  font-style: normal;
}

.source-row b {
  border-radius: 999px;
  padding: 4px 8px;
  background: var(--fin-card-soft);
  color: var(--fin-muted);
  font-size: 11px;
  white-space: nowrap;
}

.source-row b.demo {
  color: var(--fin-accent);
  background: color-mix(in srgb, var(--fin-accent) 14%, transparent);
}

.source-row b.live_ready {
  color: var(--fin-success);
  background: var(--fin-success-soft);
}

.source-row b.missing_key {
  color: var(--fin-warning);
  background: var(--fin-warning-soft);
}

.missing-list {
  margin: 0;
  border-top: 1px dashed var(--fin-border);
  padding-top: 10px;
}

.rail-card strong {
  display: block;
  font-size: 22px;
}

.identity-block {
  border-radius: 18px;
  overflow: hidden;
  flex-shrink: 0;
}

.rail-card {
  flex-shrink: 0;
}

.workspace {
  min-width: 0;
  width: 100%;
}

.terminal-bar {
  min-height: 76px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 clamp(20px, 2.2vw, 34px);
  border-bottom: 1px solid var(--fin-border);
  position: sticky;
  top: 0;
  z-index: 20;
  background: color-mix(in srgb, var(--fin-bg) 92%, transparent);
}

.route-title {
  min-width: 190px;
}

.terminal-bar h1 {
  margin: 0;
  font-size: 20px;
  color: var(--fin-text);
  letter-spacing: -0.01em;
}

.terminal-kicker {
  margin: 0 0 2px;
}

.ticker-tape {
  margin-left: auto;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  max-width: 42vw;
}

.ticker-pill,
.watch-chip,
.empty-action,
.context-button,
.mobile-menu,
.drawer-head button {
  border: 1px solid var(--fin-border);
  background: var(--fin-card-soft);
  color: var(--fin-text);
  cursor: pointer;
}

.ticker-pill {
  border-radius: 999px;
  padding: 9px 13px;
  display: flex;
  gap: 8px;
  align-items: center;
  white-space: nowrap;
}

.ticker-pill span,
.ticker-pill em {
  font-size: 13px;
  font-style: normal;
}

.workspace-main {
  width: 100%;
  max-width: none;
  padding: clamp(20px, 2.4vw, 36px);
}

.context-button,
.mobile-menu,
.drawer-head button {
  border-radius: 14px;
  padding: 9px 12px;
  font-weight: 900;
  white-space: nowrap;
}

.context-drawer {
  position: fixed;
  z-index: 50;
  inset: 0 0 0 auto;
  width: min(380px, calc(100vw - 36px));
  max-height: 100dvh;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  border-left: 1px solid var(--fin-border);
  background: var(--fin-card);
  box-shadow: -28px 0 90px rgba(0, 0, 0, 0.28);
  transform: translateX(104%);
  visibility: hidden;
  pointer-events: none;
  transition: transform 0.22s var(--fin-ease);
}

.context-drawer:not(.open) {
  display: none;
}

.context-drawer.open {
  display: flex;
  transform: translateX(0);
  visibility: visible;
  pointer-events: auto;
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.watch-chip {
  width: 100%;
  padding: 12px 14px;
  margin-top: 10px;
  text-align: left;
  border-radius: 16px;
}

.watch-chip span {
  display: block;
  margin-top: 2px;
  color: var(--fin-muted);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-action {
  width: 100%;
  padding: 12px;
  margin-top: 10px;
  border-radius: 16px;
}

.mobile-menu,
.mobile-mask,
.drawer-mask {
  display: none;
}

.drawer-mask {
  position: fixed;
  inset: 0;
  z-index: 45;
  background: var(--fin-overlay);
}

@media (max-width: 1120px) {
  .ticker-tape {
    display: none;
  }
}

@media (max-width: 820px) {
  .app-shell {
    display: block;
  }

  .side-rail {
    position: fixed;
    inset: 0 auto 0 0;
    width: 280px;
    z-index: 60;
    transform: translateX(-100%);
    transition: transform 0.2s var(--fin-ease);
  }

  .side-rail.open {
    transform: translateX(0);
  }

  .mobile-menu {
    display: inline-flex;
  }

  .workspace-main {
    padding: 16px;
  }

  .mobile-mask,
  .drawer-mask {
    display: block;
  }
}

@media (min-width: 821px) {
  .drawer-mask {
    display: block;
  }
}

/* ── 移动端底部导航 ─────────────────────────────────────────────── */
.mobile-bottom-nav {
  display: none;
}

@media (max-width: 820px) {
  .mobile-bottom-nav {
    display: flex;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 70;
    background: color-mix(in srgb, var(--fin-bg) 95%, transparent);
    border-top: 1px solid var(--fin-border);
    padding: 6px 0 max(6px, env(safe-area-inset-bottom));
  }

  .workspace-main {
    padding-bottom: calc(96px + env(safe-area-inset-bottom)) !important;
  }

  .mb-nav-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 6px 4px;
    color: var(--fin-muted);
    text-decoration: none;
    transition: color 0.15s;
  }

  .mb-nav-item.active {
    color: var(--fin-primary);
  }

  .mb-icon {
    font-size: 18px;
    line-height: 1;
  }

  .mb-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
}

/* ── 下拉刷新指示器 ────────────────────────────────────────────── */
.pull-indicator {
  position: fixed;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  padding: 6px 18px;
  border-radius: 0 0 18px 18px;
  background: var(--fin-primary);
  color: white;
  font-size: 13px;
  font-weight: 600;
}
</style>
