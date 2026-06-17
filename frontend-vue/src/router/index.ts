import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useIdentityStore } from '@/stores/identity';

function symbolParam(value: unknown, fallback = 'AAPL'): string {
  const raw = Array.isArray(value) ? value[0] : value;
  return String(raw || fallback).toUpperCase();
}

// 当前默认前端路由，API 由 frontend-vue/src/api/client.ts 直连 Python FastAPI。
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/welcome' },
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue') },
  { path: '/welcome', name: 'welcome', component: () => import('@/pages/WelcomePage.vue') },
  { path: '/chat', name: 'chat', component: () => import('@/pages/ChatPage.vue') },
  { path: '/stocks', name: 'stocks', component: () => import('@/pages/StocksDiscoveryPage.vue'), meta: { requiresAuth: true } },
  { path: '/dossier/:symbol', name: 'symbol-dossier', component: () => import('@/pages/SymbolDossierPage.vue'), meta: { requiresAuth: true } },
  { path: '/dashboard', redirect: '/dossier/AAPL' },
  { path: '/dashboard/:symbol', redirect: (to) => `/dossier/${encodeURIComponent(symbolParam(to.params.symbol))}` },
  { path: '/workbench', redirect: '/welcome' },
  { path: '/data-sources', redirect: { path: '/welcome', query: { drawer: 'data' } } },
  { path: '/rag-inspector', redirect: { path: '/welcome', query: { drawer: 'data' } } },
  { path: '/watchlist', redirect: { path: '/stocks', query: { tab: 'watchlist' } } },
  { path: '/portfolio', name: 'portfolio', component: () => import('@/pages/PortfolioPage.vue'), meta: { requiresAuth: true } },
  { path: '/portfolio/risk-lens', redirect: { path: '/portfolio', query: { tool: 'risk' } } },
  { path: '/notes', name: 'research-notes', component: () => import('@/pages/ResearchNotesPage.vue'), meta: { requiresAuth: true } },
  { path: '/timeline/:symbol', redirect: (to) => `/dossier/${encodeURIComponent(symbolParam(to.params.symbol))}` },
  { path: '/reports', name: 'reports', component: () => import('@/pages/ReportsLibraryPage.vue') },
  { path: '/alerts', redirect: '/welcome' },
  { path: '/system/health', redirect: { path: '/welcome', query: { drawer: 'system' } } },
  { path: '/top-list/:ticker?', redirect: { path: '/stocks', query: { tool: 'top-list' } } },
  { path: '/north-flow', redirect: { path: '/stocks', query: { tool: 'north-flow' } } },
  { path: '/margin-trading', redirect: { path: '/stocks', query: { tool: 'margin' } } },
  { path: '/research/report/:ticker?', redirect: (to) => ({ path: '/reports', query: { tool: 'generate', ticker: symbolParam(to.params.ticker, '') || undefined } }) },
  { path: '/research/financials', redirect: { path: '/reports', query: { tool: 'financials' } } },
  { path: '/research/qa', redirect: { path: '/chat', query: { mode: 'qa' } } },
  { path: '/backtest', redirect: { path: '/portfolio', query: { tool: 'backtest' } } },
  { path: '/portfolio/optimize', redirect: { path: '/portfolio', query: { tool: 'optimize' } } },
  { path: '/:pathMatch(.*)*', redirect: '/welcome' },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

// 路由守卫：游客访问需要登录的页面时跳转到 /login。
router.beforeEach((to) => {
  if (to.path === '/login') return true;

  const identity = useIdentityStore();
  if (to.meta.requiresAuth && identity.isGuest) {
    return '/login';
  }

  return true;
});
