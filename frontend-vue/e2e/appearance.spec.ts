import { expect, test, type Locator, type Page, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

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
    success: true, demo_mode: true, data_source: 'demo', overall_status: 'demo',
    as_of: '2026-06-17T10:00:00Z', missing_services: [], components: [], notes: [],
  };
  await page.route('**/api/demo/status', (route) => json(route, demoStatus));
  await page.route('**/api/data-sources/status', (route) => json(route, demoStatus));
  await page.route('**/api/portfolio/summary**', (route) =>
    json(route, { success: true, session_id: SESSION_ID, count: 0, positions: [], total_value: 0, total_cost: 0, total_pnl: 0 }));
  await page.route('**/api/user/watchlist**', (route) => json(route, { success: true, count: 0, items: [] }));
  await page.route('**/api/tasks/daily**', (route) => json(route, { success: true, session_id: SESSION_ID, count: 0, tasks: [] }));
  await page.route('**/api/today**', (route) =>
    json(route, {
      success: true, as_of: '2026-06-17T10:00:00Z', freshness_status: 'live', summary: '',
      portfolio_snapshot: { position_count: 0, total_cost: 0, total_value: 0, total_pnl: 0, risk_positions: [] },
      watchlist_movers: [], alert_feed: [], reports_to_review: [], next_actions: [],
    }));
  await page.route('**/api/what-changed**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', count: 0, items: [] }));
  await page.route('**/api/research-quality**', (route) =>
    json(route, { success: true, as_of: '2026-06-17T10:00:00Z', summary: { total_reports: 0, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 1, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
});

function rootAttr(page: Page, name: string) {
  return page.evaluate((attr) => document.documentElement.getAttribute(attr), name);
}

// 很多卡片标签在不同分组里重名（如「默认」），必须先按分组标题定位再选卡片。
function group(dialog: Locator, heading: string): Locator {
  return dialog.locator('section.group').filter({ has: dialog.page().getByRole('heading', { name: heading, exact: true }) });
}

async function openModal(page: Page): Promise<Locator> {
  await page.getByRole('button', { name: '外观设置' }).click();
  const dialog = page.getByRole('dialog', { name: '主题设置' });
  await expect(dialog).toBeVisible();
  return dialog;
}

test('主题设置弹窗逐项应用到 <html>', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);

  await group(dialog, '主题').getByRole('button', { name: '浅色', exact: true }).click();
  expect(await rootAttr(page, 'data-theme')).toBe('light');

  await group(dialog, '颜色预设').getByRole('button', { name: '海风', exact: true }).click();
  expect(await rootAttr(page, 'data-accent')).toBe('seabreeze');
  const primary = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--fin-primary').trim());
  expect(primary.toLowerCase()).toBe('#2563eb');

  await group(dialog, '字体').getByRole('button', { name: 'Serif', exact: true }).click();
  expect(await rootAttr(page, 'data-font')).toBe('serif');

  await group(dialog, '圆角').getByRole('button', { name: '0', exact: true }).click();
  expect(await rootAttr(page, 'data-radius')).toBe('0');

  await group(dialog, '密度').getByRole('button', { name: '超大', exact: true }).click();
  expect(await rootAttr(page, 'data-density')).toBe('xl');

  await group(dialog, '侧边栏').getByRole('button', { name: '侧边栏', exact: true }).click();
  expect(await rootAttr(page, 'data-sidebar')).toBe('rail');

  await group(dialog, '布局').getByRole('button', { name: '紧凑', exact: true }).click();
  expect(await rootAttr(page, 'data-shell-layout')).toBe('compact');

  await group(dialog, '内容宽度').getByRole('button', { name: '居中', exact: true }).click();
  expect(await rootAttr(page, 'data-content-width')).toBe('centered');

  await group(dialog, '方向').getByRole('button', { name: '从右到左', exact: true }).click();
  expect(await rootAttr(page, 'dir')).toBe('rtl');
});

test('外观偏好在刷新后保持', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);
  await group(dialog, '主题').getByRole('button', { name: '浅色', exact: true }).click();
  await group(dialog, '颜色预设').getByRole('button', { name: '玫瑰花园', exact: true }).click();
  await group(dialog, '圆角').getByRole('button', { name: '1.0', exact: true }).click();

  await page.reload();
  await expect(page.getByRole('button', { name: '外观设置' })).toBeVisible();
  expect(await rootAttr(page, 'data-theme')).toBe('light');
  expect(await rootAttr(page, 'data-accent')).toBe('rosegarden');
  expect(await rootAttr(page, 'data-radius')).toBe('1.0');
});

test('重置回到默认外观', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);

  await group(dialog, '颜色预设').getByRole('button', { name: '湖光', exact: true }).click();
  await group(dialog, '圆角').getByRole('button', { name: '0', exact: true }).click();
  await group(dialog, '侧边栏').getByRole('button', { name: '侧边栏', exact: true }).click();
  expect(await rootAttr(page, 'data-accent')).toBe('lake');

  const reset = dialog.getByRole('button', { name: '重置为默认' });
  await expect(reset).toBeEnabled();
  await reset.click();

  expect(await rootAttr(page, 'data-accent')).toBe('default');
  expect(await rootAttr(page, 'data-radius')).toBe('auto');
  expect(await rootAttr(page, 'data-sidebar')).toBe('inset');
  expect(await rootAttr(page, 'dir')).toBe('ltr');
  await expect(reset).toBeDisabled();
});

test('所有颜色预设在浅色下都解析出正确的品牌主色', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);
  await group(dialog, '主题').getByRole('button', { name: '浅色', exact: true }).click();

  const expected: Record<string, string> = {
    默认: '#cc785c', Anthropic: '#cc785c', 超大字体简易: '#1f2937', 暗夜: '#334155',
    玫瑰花园: '#db2777', 湖光: '#0d9488', 日落霞光: '#ea580c', 森林低语: '#15803d',
    海风: '#2563eb', 薰衣草梦: '#7c3aed',
  };
  const colors = group(dialog, '颜色预设');
  for (const [label, hex] of Object.entries(expected)) {
    await colors.getByRole('button', { name: label, exact: true }).click();
    const primary = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--fin-primary').trim().toLowerCase());
    expect(primary, `颜色预设「${label}」应为 ${hex}`).toBe(hex);
  }
});

test('切换侧边栏与布局形态都不会让页面塌陷', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);
  const bodyWidth = () => page.evaluate(() => Math.round(document.body.getBoundingClientRect().width));

  for (const label of ['浮动', '侧边栏', '内嵌']) {
    await group(dialog, '侧边栏').getByRole('button', { name: label, exact: true }).click();
    expect(await bodyWidth(), `侧边栏「${label}」后页面不应塌陷`).toBeGreaterThan(600);
  }
  for (const label of ['紧凑', '全屏布局', '默认']) {
    await group(dialog, '布局').getByRole('button', { name: label, exact: true }).click();
    expect(await bodyWidth(), `布局「${label}」后页面不应塌陷`).toBeGreaterThan(600);
  }
});

test('关闭按钮与遮罩点击都能关闭弹窗', async ({ page }) => {
  await page.goto('/welcome');
  const dialog = await openModal(page);

  await dialog.getByRole('button', { name: '关闭' }).click();
  await expect(dialog).toBeHidden();

  // 遮罩点击关闭
  await openModal(page);
  await page.locator('.appearance-overlay').click({ position: { x: 8, y: 8 } });
  await expect(page.getByRole('dialog', { name: '主题设置' })).toBeHidden();
});
