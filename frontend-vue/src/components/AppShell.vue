<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import IdentityPanel from '@/components/IdentityPanel.vue';
import { useIdentityStore } from '@/stores/identity';
import type { PortfolioSummary, WatchlistItem } from '@/api/types';

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();
const sidebarOpen = ref(false);
const portfolio = ref<PortfolioSummary | null>(null);
const watchlist = ref<WatchlistItem[]>([]);

const navItems = [
  { to: '/welcome', label: '今日工作台', short: 'TODAY' },
  { to: '/dashboard/AAPL', label: '市场仪表盘', short: 'DASH' },
  { to: '/chat', label: '研究对话', short: 'CHAT' },
  { to: '/workbench', label: '研究工作台', short: 'LAB' },
  { to: '/reports', label: '报告资产库', short: 'RPT' },
  { to: '/portfolio', label: '持仓管理', short: 'PORT' },
  { to: '/watchlist', label: '观察列表', short: 'WATCH' },
  { to: '/alerts', label: '提醒中心', short: 'ALERT' },
  { to: '/notes', label: '研究笔记', short: 'NOTE' },
];

const marketStrip = [
  { symbol: 'SPY', price: '639.12', change: '+0.42%' },
  { symbol: 'QQQ', price: '558.04', change: '+0.77%' },
  { symbol: 'DOW', price: '39,804', change: '+0.18%' },
  { symbol: 'VIX', price: '12.40', change: '-1.12%' },
];

const routeTitle = computed(() => {
  if (route.path.startsWith('/dashboard')) return 'Market Intelligence';
  if (route.path.startsWith('/chat')) return 'Research Copilot';
  if (route.path.startsWith('/workbench')) return 'Daily Research Lab';
  if (route.path.startsWith('/reports')) return 'Report Archive';
  return 'FinSight AI';
});

const totalValue = computed(() => portfolio.value?.total_value ?? 0);
const totalPnl = computed(() => portfolio.value?.total_pnl ?? 0);

function closeSidebar() {
  sidebarOpen.value = false;
}

async function loadContext() {
  const results = await Promise.allSettled([
    apiClient.getPortfolioSummary(identity.sessionId),
    apiClient.listWatchlist(identity.userId),
  ]);
  if (results[0].status === 'fulfilled') portfolio.value = results[0].value;
  if (results[1].status === 'fulfilled') watchlist.value = results[1].value.items || [];
}

onMounted(() => {
  void loadContext();
});
</script>

<template>
  <div class="app-shell">
    <aside class="side-rail" :class="{ open: sidebarOpen }">
      <button class="brand-lockup" @click="router.push('/welcome')">
        <span class="brand-mark">FS</span>
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
          <span>{{ item.short }}</span>
          <strong>{{ item.label }}</strong>
        </RouterLink>
      </nav>

      <div class="rail-card">
        <p class="rail-kicker">PORTFOLIO</p>
        <strong>{{ totalValue ? `¥${totalValue.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}` : '暂无持仓' }}</strong>
        <span :class="totalPnl >= 0 ? 'pos' : 'neg'">
          {{ totalPnl >= 0 ? '+' : '' }}{{ totalPnl.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}
        </span>
      </div>

      <IdentityPanel class="identity-block" />
    </aside>

    <div class="workspace">
      <header class="terminal-bar">
        <button class="mobile-menu" @click="sidebarOpen = !sidebarOpen">☰</button>
        <div>
          <p class="terminal-kicker">FINSIGHT TERMINAL / {{ routeTitle }}</p>
          <h1>{{ routeTitle }}</h1>
        </div>
        <div class="ticker-tape" aria-label="市场状态条">
          <button
            v-for="item in marketStrip"
            :key="item.symbol"
            class="ticker-pill"
            @click="router.push(`/dashboard/${item.symbol}`)"
          >
            <strong>{{ item.symbol }}</strong>
            <span>{{ item.price }}</span>
            <em :class="item.change.startsWith('+') ? 'pos' : 'neg'">{{ item.change }}</em>
          </button>
        </div>
      </header>

      <main class="workspace-main">
        <slot />
      </main>
    </div>

    <aside class="context-rail">
      <section class="context-card">
        <p class="rail-kicker">WATCHLIST</p>
        <button
          v-for="item in watchlist.slice(0, 6)"
          :key="item.ticker"
          class="watch-chip"
          @click="router.push(`/dashboard/${item.ticker}`)"
        >
          <strong>{{ item.name || '重点标的' }}</strong>
          <span>{{ item.name || item.watch_reason || '研究关注' }}</span>
        </button>
        <button v-if="watchlist.length === 0" class="empty-action" @click="router.push('/watchlist')">
          添加重点标的
        </button>
      </section>

      <section class="context-card">
        <p class="rail-kicker">RESEARCH RULE</p>
        <strong>只输出研究动作建议</strong>
        <span class="muted">不提供买入、卖出或收益承诺。所有结论必须可复查。</span>
      </section>
    </aside>

    <div v-if="sidebarOpen" class="mobile-mask" @click="closeSidebar" />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr) 280px;
  background:
    radial-gradient(circle at 10% 0%, rgba(16, 185, 129, 0.16), transparent 32%),
    radial-gradient(circle at 90% 20%, rgba(245, 158, 11, 0.12), transparent 30%),
    #0f1412;
  color: #eef7ee;
}

.side-rail,
.context-rail {
  min-height: 100vh;
  border-color: rgba(214, 255, 226, 0.12);
  background: rgba(8, 14, 12, 0.78);
  backdrop-filter: blur(24px);
}

.side-rail {
  border-right: 1px solid rgba(214, 255, 226, 0.12);
  padding: 22px 18px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.context-rail {
  border-left: 1px solid rgba(214, 255, 226, 0.12);
  padding: 84px 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.brand-lockup {
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

.brand-mark {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(214, 255, 226, 0.28);
  border-radius: 16px;
  background: linear-gradient(135deg, #d7ff72, #2dd4bf);
  color: #0f1412;
  font-weight: 900;
  letter-spacing: -0.06em;
}

.brand-lockup strong,
.context-card strong {
  display: block;
  font-size: 16px;
}

.brand-lockup small,
.muted {
  display: block;
  color: rgba(238, 247, 238, 0.58);
  font-size: 12px;
}

.nav-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-link {
  display: grid;
  grid-template-columns: 56px 1fr;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  border-radius: 16px;
  color: rgba(238, 247, 238, 0.68);
  border: 1px solid transparent;
}

.nav-link span,
.rail-kicker,
.terminal-kicker {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(215, 255, 114, 0.72);
}

.nav-link strong {
  font-size: 14px;
}

.nav-link:hover,
.nav-link.active {
  color: #f8fff8;
  border-color: rgba(215, 255, 114, 0.28);
  background: rgba(215, 255, 114, 0.08);
}

.rail-card,
.context-card {
  border: 1px solid rgba(214, 255, 226, 0.12);
  border-radius: 22px;
  padding: 16px;
  background: rgba(238, 247, 238, 0.055);
}

.rail-card {
  margin-top: auto;
}

.rail-card strong {
  display: block;
  font-size: 22px;
}

.pos { color: #8cffb6; }
.neg { color: #ff8f8f; }

.identity-block {
  border-radius: 18px;
  overflow: hidden;
}

.workspace {
  min-width: 0;
}

.terminal-bar {
  height: 72px;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 28px;
  border-bottom: 1px solid rgba(214, 255, 226, 0.12);
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(15, 20, 18, 0.86);
  backdrop-filter: blur(18px);
}

.terminal-bar h1 {
  margin: 0;
  font-size: 18px;
  color: #f8fff8;
}

.terminal-kicker {
  margin: 0 0 2px;
}

.ticker-tape {
  margin-left: auto;
  display: flex;
  gap: 8px;
  overflow-x: auto;
  max-width: 56vw;
}

.ticker-pill,
.watch-chip,
.empty-action {
  border: 1px solid rgba(214, 255, 226, 0.12);
  border-radius: 999px;
  background: rgba(238, 247, 238, 0.055);
  color: #eef7ee;
  cursor: pointer;
}

.ticker-pill {
  padding: 8px 12px;
  display: flex;
  gap: 8px;
  align-items: center;
  white-space: nowrap;
}

.ticker-pill span,
.ticker-pill em {
  font-size: 12px;
  font-style: normal;
}

.workspace-main {
  padding: 28px;
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
  color: rgba(238, 247, 238, 0.56);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-action {
  width: 100%;
  padding: 12px;
  margin-top: 10px;
}

.mobile-menu,
.mobile-mask {
  display: none;
}

@media (max-width: 1160px) {
  .app-shell {
    grid-template-columns: 240px minmax(0, 1fr);
  }

  .context-rail {
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
    z-index: 40;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .side-rail.open {
    transform: translateX(0);
  }

  .mobile-menu {
    display: inline-flex;
    border: 1px solid rgba(214, 255, 226, 0.2);
    border-radius: 12px;
    background: rgba(238, 247, 238, 0.08);
    color: #eef7ee;
    padding: 8px 12px;
  }

  .ticker-tape {
    display: none;
  }

  .workspace-main {
    padding: 18px;
  }

  .mobile-mask {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 30;
    background: rgba(0, 0, 0, 0.56);
  }
}
</style>
