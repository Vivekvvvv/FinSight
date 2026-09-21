import { expect, test, type Route } from '@playwright/test';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

// 全新访客（无 token）：/api/me 未授权返回 401，与真实后端一致。
test.beforeEach(async ({ page }) => {
  await page.route('**/api/me', (route) => json(route, { detail: 'unauthorized' }, 401));
  const demo = { success: true, demo_mode: true, overall_status: 'demo', as_of: '2026-06-17T10:00:00Z', missing_services: [], components: [], notes: [] };
  await page.route('**/api/demo/status', (route) => json(route, demo));
  await page.route('**/api/data-sources/status', (route) => json(route, demo));
  await page.route('**/api/portfolio/summary**', (route) => json(route, { success: true, count: 0, positions: [], total_value: 0, total_cost: 0, total_pnl: 0 }));
  await page.route('**/api/user/watchlist**', (route) => json(route, { success: true, count: 0, items: [] }));
  await page.route('**/api/tasks/daily**', (route) => json(route, { success: true, count: 0, tasks: [] }));
  await page.route('**/api/today**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', freshness_status: 'live', summary: '', portfolio_snapshot: { position_count: 0, total_cost: 0, total_value: 0, total_pnl: 0, risk_positions: [] }, watchlist_movers: [], alert_feed: [], reports_to_review: [], next_actions: [] }));
  await page.route('**/api/what-changed**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', count: 0, items: [] }));
  await page.route('**/api/research-quality**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', summary: { total_reports: 0, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 1, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
});

test('匿名体验进入后是游客身份，且受保护页被守卫拦回登录', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: '匿名体验' }).click();
  await page.waitForURL('**/welcome');

  // 账户菜单应显示“游客”，不再是默认的“开发”
  await page.getByRole('button', { name: '账户菜单' }).click();
  await expect(page.getByRole('menu', { name: '账户菜单' })).toContainText('游客');

  // 关闭菜单，走应用内导航（点侧边栏“组合管理”）——真实访客路径，
  // 不走整页刷新（整页刷新会重建内存态 store，另属未持久化问题）。
  await page.keyboard.press('Escape');
  await page.locator('.nav-stack').getByRole('link', { name: /组合管理/ }).click();
  await page.waitForURL('**/login');
  expect(page.url()).toContain('/login');
});
