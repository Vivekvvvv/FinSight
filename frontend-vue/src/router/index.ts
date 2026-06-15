import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useIdentityStore } from '@/stores/identity';

// 当前默认前端路由，API 由 frontend-vue/src/api/client.ts 直连 Python FastAPI。
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/welcome' },
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue') },
  { path: '/welcome', name: 'welcome', component: () => import('@/pages/WelcomePage.vue') },
  { path: '/chat', name: 'chat', component: () => import('@/pages/ChatPage.vue') },
  { path: '/stocks', name: 'stocks', component: () => import('@/pages/StocksDiscoveryPage.vue'), meta: { requiresAuth: true } },
  { path: '/dossier/:symbol', name: 'symbol-dossier', component: () => import('@/pages/SymbolDossierPage.vue'), meta: { requiresAuth: true } },
  { path: '/dashboard', name: 'dashboard', component: () => import('@/pages/DashboardPage.vue') },
  { path: '/dashboard/:symbol', name: 'dashboard-symbol', component: () => import('@/pages/DashboardPage.vue') },
  { path: '/workbench', name: 'workbench', component: () => import('@/pages/WorkbenchPage.vue') },
  { path: '/data-sources', name: 'data-sources', component: () => import('@/pages/DataSourcesPage.vue'), meta: { requiresAuth: true } },
  { path: '/rag-inspector', name: 'rag-inspector', component: () => import('@/pages/RagInspectorPage.vue') },
  { path: '/watchlist', name: 'watchlist', component: () => import('@/pages/WatchlistPage.vue'), meta: { requiresAuth: true } },
  { path: '/portfolio', name: 'portfolio', component: () => import('@/pages/PortfolioPage.vue'), meta: { requiresAuth: true } },
  { path: '/portfolio/risk-lens', name: 'portfolio-risk-lens', component: () => import('@/components/PortfolioRiskLens.vue'), meta: { requiresAuth: true } },
  { path: '/notes', name: 'research-notes', component: () => import('@/pages/ResearchNotesPage.vue'), meta: { requiresAuth: true } },
  { path: '/timeline/:symbol', name: 'timeline', component: () => import('@/pages/TimelinePage.vue'), meta: { requiresAuth: true } },
  { path: '/reports', name: 'reports', component: () => import('@/pages/ReportsLibraryPage.vue') },
  { path: '/alerts', name: 'alerts', component: () => import('@/pages/AlertsPage.vue'), meta: { requiresAuth: true } },
  { path: '/system/health', name: 'system-health', component: () => import('@/pages/SystemHealthPage.vue') },
  { path: '/top-list/:ticker?', name: 'top-list', component: () => import('@/pages/TopListPage.vue') },
  { path: '/north-flow', name: 'north-flow', component: () => import('@/pages/NorthFlowPage.vue') },
  { path: '/margin-trading', name: 'margin-trading', component: () => import('@/pages/MarginTradingPage.vue') },
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
