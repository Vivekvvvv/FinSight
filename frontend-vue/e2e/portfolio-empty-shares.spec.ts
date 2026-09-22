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
  await page.route('**/api/portfolio/summary**', (route) => json(route, {
    success: true, session_id: SESSION_ID, count: 1, total_value: 100, total_cost: 100, total_pnl: 0,
    positions: [{ ticker: 'MSFT', shares: 1, avg_cost: 100, current_price: 100, market_value: 100, cost_basis: 100, unrealized_pnl: 0, unrealized_pnl_pct: 0, name: 'Microsoft', tags: [], note: '', price_source: 'live' }],
  }));
});

// MEDIUM：Number('') === 0，手动新增持仓时股数留空会被当成 0 股静默保存，
// 绕过“非负 shares”校验。验证留空时报错且不发起 upsert 请求。
test('手动新增持仓：股数留空应报错而不是静默按 0 股保存', async ({ page }) => {
  let upsertCalled = false;
  await page.route('**/api/portfolio/positions/**', async (route) => {
    if (route.request().method() === 'PUT') {
      upsertCalled = true;
      return json(route, { success: true });
    }
    return route.fallback();
  });

  await page.goto('/portfolio');

  await page.getByRole('button', { name: '+ 新增持仓' }).click();
  await page.locator('input[placeholder="AAPL"]').fill('AAPL');
  // 股数留空
  await page.getByRole('button', { name: '确认保存' }).click();

  await expect(page.getByText('请输入合法 ticker 与非负 shares')).toBeVisible();

  // 校验拦下后不应发起保存请求（修复前 Number('')=0 会静默 PUT 一个 0 股持仓）
  await page.waitForTimeout(300);
  expect(upsertCalled, '股数留空不应发起 upsert 请求').toBe(false);
});

// 内联编辑同一条路径同一个 Number('') 陷阱：清空股数保存应报错而非静默按 0 股。
test('内联编辑持仓：清空股数应报错而不是静默按 0 股保存', async ({ page }) => {
  let upsertCalled = false;
  await page.route('**/api/portfolio/positions/**', async (route) => {
    if (route.request().method() === 'PUT') {
      upsertCalled = true;
      return json(route, { success: true });
    }
    return route.fallback();
  });

  await page.goto('/portfolio');

  await page.getByRole('button', { name: '编辑', exact: true }).click();
  // 编辑区第一个数字输入即股数（editForm.shares，回填为持仓的 1 股），清空它
  await page.locator('.edit-grid input[type="number"]').first().fill('');
  await page.getByRole('button', { name: '保存', exact: true }).click();

  await expect(page.getByText('股数须为非负数')).toBeVisible();

  await page.waitForTimeout(300);
  expect(upsertCalled, '清空股数不应发起 upsert 请求').toBe(false);
});
