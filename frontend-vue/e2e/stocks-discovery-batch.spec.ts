import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

const SCREENER = {
  success: true,
  market: 'US',
  count: 2,
  source: 'mock',
  as_of: '2026-06-17T10:00:00Z',
  items: [
    { symbol: 'AAA', name: 'Alpha Inc', sector: 'Tech', price: 12.3, market_cap: 1e9, volume: 5e6, change_percent: 1.2 },
    { symbol: 'BBB', name: 'Beta Inc', sector: 'Tech', price: 45.6, market_cap: 2e9, volume: 6e6, change_percent: -0.8 },
  ],
};

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
  await page.route('**/api/screener/filters/meta', (route) =>
    json(route, { success: true, markets: ['US', 'CN', 'HK'], sort_by: ['market_cap'], sort_order: ['asc', 'desc'], sectors: [], exchanges: [] }));
  await page.route('**/api/screener/run', (route) => json(route, SCREENER));
  // 自选加入始终成功，把失败面收敛到 createNote，专测“笔记全失败仍报成功”。
  await page.route('**/api/user/watchlist/add', (route) => json(route, { success: true }));
});

// MEDIUM：addWatchlistAndNote 自吞异常，batchCreateNotes 之前无视真实成功数，
// 即便每个 createNote 都失败也会显示“已为 N 个候选标的创建初始研究笔记”的假成功。
test('批量创建初始笔记：createNote 全部失败时不显示假成功提示', async ({ page }) => {
  await page.route('**/api/research-notes', (route) =>
    json(route, { success: false, error: '后端笔记服务不可用' }, 500));

  await page.goto('/stocks');
  await expect(page.locator('.notice.success')).toHaveCount(0);
  // 等候选卡片渲染出来
  await expect(page.getByText('Alpha Inc')).toBeVisible();

  await page.getByRole('button', { name: '批量创建初始笔记' }).click();

  // 全失败：不得出现“已为 N 个候选标的创建初始研究笔记”成功横幅
  await expect.poll(async () =>
    (await page.locator('.notice.success').allTextContents()).join(' '),
  { timeout: 4000 }).not.toContain('创建初始研究笔记');
});
