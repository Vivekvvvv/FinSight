import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

test.beforeEach(async ({ page }) => {
  // 先写入身份，再让主题相关的 localStorage 键在隐私模式下抛 SecurityError。
  await page.addInitScript(([sid, uid, email, token]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);

    const THEME_KEYS = new Set(['finsight-appearance', 'finsight-theme']);
    const proto = Object.getPrototypeOf(window.localStorage) as Storage;
    const rawGet = proto.getItem.bind(window.localStorage);
    const rawSet = proto.setItem.bind(window.localStorage);
    window.localStorage.getItem = (key: string) => {
      if (THEME_KEYS.has(key)) throw new DOMException('denied', 'SecurityError');
      return rawGet(key);
    };
    window.localStorage.setItem = (key: string, value: string) => {
      if (THEME_KEYS.has(key)) throw new DOMException('denied', 'SecurityError');
      return rawSet(key, value);
    };
  }, [SESSION_ID, USER_ID, EMAIL, 'mock-token-e2e']);

  await page.route('**/api/me', (route) =>
    json(route, { success: true, user_id: USER_ID, email: EMAIL, role: 'user', auth_type: 'token' }));
  const demo = { success: true, demo_mode: true, overall_status: 'demo', as_of: '2026-06-17T10:00:00Z', missing_services: [], components: [], notes: [] };
  await page.route('**/api/demo/status', (route) => json(route, demo));
  await page.route('**/api/data-sources/status', (route) => json(route, demo));
  await page.route('**/api/portfolio/summary**', (route) => json(route, { success: true, session_id: SESSION_ID, count: 0, positions: [], total_value: 0, total_cost: 0, total_pnl: 0 }));
  await page.route('**/api/user/watchlist**', (route) => json(route, { success: true, count: 0, items: [] }));
  await page.route('**/api/tasks/daily**', (route) => json(route, { success: true, count: 0, tasks: [] }));
  await page.route('**/api/today**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', freshness_status: 'live', summary: '', portfolio_snapshot: { position_count: 0, total_cost: 0, total_value: 0, total_pnl: 0, risk_positions: [] }, watchlist_movers: [], alert_feed: [], reports_to_review: [], next_actions: [] }));
  await page.route('**/api/what-changed**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', count: 0, items: [] }));
  await page.route('**/api/research-quality**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', summary: { total_reports: 0, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 1, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
});

// MEDIUM：readAppearance 在 store 构造期即读 localStorage；隐私模式下 getItem
// 抛 SecurityError 而未兜住时，整个应用启动即崩，什么都渲染不出来。
test('主题偏好键在隐私模式下抛 SecurityError，应用仍能正常启动渲染', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));

  await page.goto('/welcome');

  // 应用外壳应挂载，且 <html data-theme> 已被 apply() 正常写上（未因读盘失败而中断）。
  await expect(page.locator('.app-shell')).toBeVisible();
  const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
  expect(theme === 'dark' || theme === 'light').toBe(true);

  const securityErrors = pageErrors.filter((m) => m.includes('SecurityError'));
  expect(securityErrors, `不应有未捕获的 SecurityError：${securityErrors.join(' | ')}`).toHaveLength(0);
});
