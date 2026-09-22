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
  // 返回 1 条持仓，避免空态里的另一个「导入 CSV」按钮造成选择器歧义
  await page.route('**/api/portfolio/summary**', (route) => json(route, {
    success: true, session_id: SESSION_ID, count: 1, total_value: 100, total_cost: 100, total_pnl: 0,
    positions: [{ ticker: 'MSFT', shares: 1, avg_cost: 100, current_price: 100, market_value: 100, cost_basis: 100, unrealized_pnl: 0, unrealized_pnl_pct: 0, name: 'Microsoft', tags: [], note: '', price_source: 'live' }],
  }));
});

// MEDIUM：Number('') === 0，CSV 股数列为空时旧代码把该行当成「0 股」静默导入，
// 掩盖了漏填股数的错误行。验证空股数行被标为错误行而非可导入行。
test('CSV 导入：股数列为空的行应判为错误行，而不是静默当成 0 股', async ({ page }) => {
  await page.goto('/portfolio');

  await page.locator('button.btn-secondary', { hasText: '导入 CSV' }).click();

  const area = page.locator('.csv-area');
  await expect(area).toBeVisible();
  // 第一行漏填股数（AAPL,,150），第二行合法（TSLA,5,220）
  await area.fill('AAPL,,150\nTSLA,5,220');

  await page.getByRole('button', { name: '解析预览' }).click();

  // 修复后：1 可导入 + 1 错误行；修复前：AAPL 被当成 0 股 → 2 可导入、0 错误
  await expect(page.locator('.preview-stat .ok')).toHaveText('1 可导入');
  const errRows = page.locator('.preview-list .row-err');
  await expect(errRows).toHaveCount(1);
  await expect(errRows.first()).toContainText('AAPL');
});
