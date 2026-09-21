import { expect, test, type Page, type Route } from '@playwright/test';

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
  await page.route('**/api/auth/logout', (route) => json(route, { success: true }));
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

async function openMenu(page: Page) {
  await page.getByRole('button', { name: '账户菜单' }).click();
  const menu = page.getByRole('menu', { name: '账户菜单' });
  await expect(menu).toBeVisible();
  return menu;
}

test('右上角头像按钮打开账户菜单，含个人资料与登出', async ({ page }) => {
  await page.goto('/welcome');

  const trigger = page.getByRole('button', { name: '账户菜单' });
  await expect(trigger).toBeVisible();
  // 头像展示用户名首字母
  await expect(trigger).toContainText('V');

  const menu = await openMenu(page);
  await expect(menu).toContainText('vue-e2e');
  await expect(menu.getByRole('menuitem', { name: '个人资料' })).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: '登出' })).toBeVisible();
});

test('个人资料打开资料弹窗并展示身份信息', async ({ page }) => {
  await page.goto('/welcome');
  const menu = await openMenu(page);
  await menu.getByRole('menuitem', { name: '个人资料' }).click();

  const dialog = page.getByRole('dialog', { name: '个人资料' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText('用户名', { exact: true })).toBeVisible();
  await expect(dialog.getByText(USER_ID, { exact: true })).toBeVisible();
  await expect(dialog.getByText(EMAIL, { exact: true })).toBeVisible();
  await expect(dialog.getByText('角色', { exact: true })).toBeVisible();

  await dialog.getByRole('button', { name: '关闭' }).click();
  await expect(dialog).toBeHidden();
});

test('登出会清空本地身份并跳转登录页', async ({ page }) => {
  await page.goto('/welcome');
  const menu = await openMenu(page);
  await menu.getByRole('menuitem', { name: '登出' }).click();

  await page.waitForURL('**/login');
  const token = await page.evaluate(() => localStorage.getItem('finsight-access-token'));
  expect(token).toBeNull();
});

test('资料弹窗打开焦点移入、关闭焦点归还头像按钮', async ({ page }) => {
  await page.goto('/welcome');
  const menu = await openMenu(page);
  await menu.getByRole('menuitem', { name: '个人资料' }).click();

  const dialog = page.getByRole('dialog', { name: '个人资料' });
  await expect(dialog).toBeVisible();
  // 打开后焦点应在弹窗内（关闭按钮），而非丢到 <body>
  await expect(dialog.getByRole('button', { name: '关闭' })).toBeFocused();

  await dialog.getByRole('button', { name: '关闭' }).click();
  await expect(dialog).toBeHidden();
  // 关闭后焦点应回到头像触发按钮
  await expect(page.getByRole('button', { name: '账户菜单' })).toBeFocused();
});

test('点击外部关闭账户菜单', async ({ page }) => {
  await page.goto('/welcome');
  await openMenu(page);
  await page.locator('.workspace-main').click({ position: { x: 12, y: 12 } });
  await expect(page.getByRole('menu', { name: '账户菜单' })).toBeHidden();
});

// 顶栏新增外观/账户菜单后曾在窄屏溢出（653px>375px），把账户菜单挤出视口不可点。
test('窄屏(375)顶栏不横向溢出，账户菜单仍在视口内且可点开', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 720 });
  await page.goto('/welcome');

  const trigger = page.getByRole('button', { name: '账户菜单' });
  await expect(trigger).toBeVisible();

  // 页面不出现横向滚动
  const overflowX = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflowX, `窄屏不应横向溢出，实际溢出 ${overflowX}px`).toBeLessThanOrEqual(1);

  // 头像触发按钮完整落在视口内（右边缘不越界）
  const box = await trigger.boundingBox();
  expect(box, '账户菜单按钮应可见').not.toBeNull();
  expect(Math.round(box!.x + box!.width)).toBeLessThanOrEqual(375);

  // 且确实能点开菜单
  await trigger.click();
  await expect(page.getByRole('menu', { name: '账户菜单' })).toBeVisible();
});
