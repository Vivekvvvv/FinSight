import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

const EMPTY_PORTFOLIO = {
  success: true,
  session_id: SESSION_ID,
  count: 0,
  positions: [],
  total_value: 0,
  total_cost: 0,
  total_pnl: 0,
};

// 外观设置全在前端本地生效，这里只需让 AppShell 顺利挂载，业务接口给最小 mock。
test.beforeEach(async ({ page }) => {
  await page.addInitScript(([sid, uid, email, token]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);
  }, [SESSION_ID, USER_ID, EMAIL, 'mock-token-e2e']);
  // 注意：Playwright 每个用例是独立 context，localStorage 天然为空；
  // 不要在 addInitScript 里清 finsight-appearance —— 它会在 reload 时再次执行，
  // 把持久化验证用例刚写入的偏好清掉。

  await page.route('**/api/me', (route) =>
    json(route, { success: true, user_id: USER_ID, email: EMAIL, role: 'user', auth_type: 'token' }));
  const demoStatus = {
    success: true,
    demo_mode: true,
    data_source: 'demo',
    overall_status: 'demo',
    as_of: '2026-06-17T10:00:00Z',
    missing_services: [],
    components: [],
    notes: [],
  };
  await page.route('**/api/demo/status', (route) => json(route, demoStatus));
  await page.route('**/api/data-sources/status', (route) => json(route, demoStatus));
  await page.route('**/api/portfolio/summary**', (route) => json(route, EMPTY_PORTFOLIO));
  await page.route('**/api/user/watchlist**', (route) => json(route, { success: true, count: 0, items: [] }));
  await page.route('**/api/tasks/daily**', (route) => json(route, { success: true, session_id: SESSION_ID, count: 0, tasks: [] }));
  await page.route('**/api/today**', (route) =>
    json(route, {
      success: true,
      as_of: '2026-06-17T10:00:00Z',
      freshness_status: 'live',
      summary: '',
      portfolio_snapshot: { position_count: 0, total_cost: 0, total_value: 0, total_pnl: 0, risk_positions: [] },
      watchlist_movers: [],
      alert_feed: [],
      reports_to_review: [],
      next_actions: [],
    }));
  await page.route('**/api/what-changed**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', count: 0, items: [] }));
  await page.route('**/api/research-quality**', (route) =>
    json(route, { success: true, as_of: '2026-06-17T10:00:00Z', summary: { total_reports: 0, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 1, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
});

function rootAttr(page: import('@playwright/test').Page, name: string) {
  return page.evaluate((attr) => document.documentElement.getAttribute(attr), name);
}

test('外观齿轮打开面板并逐项应用到 <html>', async ({ page }) => {
  await page.goto('/welcome');

  const trigger = page.getByRole('button', { name: '外观设置' });
  await expect(trigger).toBeVisible();

  // 打开面板
  await trigger.click();
  const panel = page.getByRole('dialog', { name: '外观设置面板' });
  await expect(panel).toBeVisible();

  // 主题：浅色
  await panel.getByRole('button', { name: '浅色', exact: true }).click();
  expect(await rootAttr(page, 'data-theme')).toBe('light');

  // 颜色：晴蓝
  await panel.getByRole('button', { name: '晴蓝', exact: true }).click();
  expect(await rootAttr(page, 'data-accent')).toBe('azure');
  const primary = await page.evaluate(() =>
    getComputedStyle(document.documentElement).getPropertyValue('--fin-primary').trim());
  expect(primary.toLowerCase()).toBe('#2f6fed');

  // 字体 / 圆角 / 密度
  await panel.getByRole('button', { name: '衬线', exact: true }).click();
  expect(await rootAttr(page, 'data-font')).toBe('serif');
  await panel.getByRole('button', { name: '直角', exact: true }).click();
  expect(await rootAttr(page, 'data-radius')).toBe('sharp');
  await panel.getByRole('button', { name: '宽松', exact: true }).click();
  expect(await rootAttr(page, 'data-density')).toBe('spacious');

  // 侧边栏 / 布局 / 方向 / 内容宽度
  await panel.getByRole('button', { name: '收起', exact: true }).click();
  expect(await rootAttr(page, 'data-rail')).toBe('collapsed');
  await panel.getByRole('button', { name: '靠右', exact: true }).click();
  expect(await rootAttr(page, 'data-shell-layout')).toBe('right');
  await panel.getByRole('button', { name: '从右到左', exact: true }).click();
  expect(await rootAttr(page, 'dir')).toBe('rtl');
  await panel.getByRole('button', { name: '全宽', exact: true }).click();
  expect(await rootAttr(page, 'data-content-width')).toBe('full');
});

test('外观偏好在刷新后保持', async ({ page }) => {
  await page.goto('/welcome');
  await page.getByRole('button', { name: '外观设置' }).click();
  const panel = page.getByRole('dialog', { name: '外观设置面板' });
  await panel.getByRole('button', { name: '浅色', exact: true }).click();
  await panel.getByRole('button', { name: '玫红', exact: true }).click();
  await panel.getByRole('button', { name: '大', exact: true }).click();

  await page.reload();
  await expect(page.getByRole('button', { name: '外观设置' })).toBeVisible();
  expect(await rootAttr(page, 'data-theme')).toBe('light');
  expect(await rootAttr(page, 'data-accent')).toBe('rose');
  expect(await rootAttr(page, 'data-radius')).toBe('large');
});

test('重置回到默认外观', async ({ page }) => {
  await page.goto('/welcome');
  await page.getByRole('button', { name: '外观设置' }).click();
  const panel = page.getByRole('dialog', { name: '外观设置面板' });

  await panel.getByRole('button', { name: '浅色', exact: true }).click();
  await panel.getByRole('button', { name: '翠绿', exact: true }).click();
  expect(await rootAttr(page, 'data-accent')).toBe('emerald');

  const reset = panel.getByRole('button', { name: '重置' });
  await expect(reset).toBeEnabled();
  await reset.click();

  expect(await rootAttr(page, 'data-accent')).toBe('ember');
  expect(await rootAttr(page, 'data-radius')).toBe('default');
  expect(await rootAttr(page, 'data-rail')).toBe('expanded');
  expect(await rootAttr(page, 'dir')).toBe('ltr');
  await expect(reset).toBeDisabled();
});

test('点击面板外部关闭', async ({ page }) => {
  await page.goto('/welcome');
  await page.getByRole('button', { name: '外观设置' }).click();
  await expect(page.getByRole('dialog', { name: '外观设置面板' })).toBeVisible();

  await page.locator('.workspace-main').click({ position: { x: 10, y: 10 } });
  await expect(page.getByRole('dialog', { name: '外观设置面板' })).toBeHidden();
});
