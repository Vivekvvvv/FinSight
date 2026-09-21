import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

test.beforeEach(async ({ page }) => {
  await page.addInitScript(([sid, uid, email, token]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);
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

// MEDIUM：浏览器中断触摸只派发 touchcancel、不派发 touchend；不处理时下拉刷新的
// pulling/pullDistance 归不了零，内容卡在下拉位移。验证 touchcancel 后 transform 复位。
test('触摸被 touchcancel 中断后，下拉位移应复位而不是卡住', async ({ page }) => {
  await page.goto('/welcome');
  const main = page.locator('.workspace-main');
  await expect(main).toBeVisible();

  // 顶部滚动位置归零，模拟一次下拉手势：touchstart → touchmove（越过阈值）→ touchcancel
  const transform = await page.evaluate(async () => {
    const target = document.documentElement;
    target.scrollTop = 0;
    const mk = (type: string, y: number) => {
      const t = new Touch({ identifier: 1, target: document.body, clientX: 10, clientY: y });
      return new TouchEvent(type, { touches: type === 'touchend' || type === 'touchcancel' ? [] : [t], cancelable: true, bubbles: true });
    };
    document.dispatchEvent(mk('touchstart', 10));
    document.dispatchEvent(mk('touchmove', 260)); // dy=250, *0.5=125 > threshold(80)
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    document.dispatchEvent(mk('touchcancel', 260));
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    await new Promise((r) => requestAnimationFrame(() => r(null)));
    const el = document.querySelector('.workspace-main') as HTMLElement | null;
    return el?.style.transform ?? '';
  });

  // 复位后 pullDistance=0 → translateY(0px)；未复位则会停在 translateY(100px)（threshold+20 上限）。
  expect(transform).toBe('translateY(0px)');
});
