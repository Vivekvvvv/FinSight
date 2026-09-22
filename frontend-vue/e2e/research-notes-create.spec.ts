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
});

// MEDIUM：创建成功后 refresh 带着 ticker/query 过滤条件重新拉列表，新笔记若不匹配
// 过滤（或 refresh 失败）就 find 不到，旧代码直接 setForm(null) 把用户刚写完的
// 标题/正文/标签全清空，还把 selected 置空——再保存会重复新建。
test('新建笔记成功但不在过滤后的列表里时，编辑器内容不应被清空', async ({ page }) => {
  // 列表接口永远返回空（等价于当前过滤条件把新笔记排除在外）
  let createCalls = 0;
  await page.route('**/api/research-notes**', async (route) => {
    const method = route.request().method();
    if (method === 'POST') {
      createCalls += 1;
      return json(route, { success: true, note_id: 'note-created-1' });
    }
    return json(route, { success: true, count: 0, notes: [] });
  });

  await page.goto('/notes');

  const titleInput = page.getByPlaceholder('例如：AAPL 财报后复盘');
  await expect(titleInput).toBeVisible();

  await titleInput.fill('AAPL 财报后复盘');
  await page.getByPlaceholder('AAPL', { exact: true }).fill('AAPL');
  await page.getByPlaceholder('逗号分隔，例如 财报,风险,待验证').fill('财报, 风险');
  await page.locator('.editor-textarea').fill('假设：服务业务增速见顶。');

  await page.getByRole('button', { name: '保存', exact: true }).click();

  // 服务端确实创建成功了
  await expect(page.getByText('笔记已创建')).toBeVisible();
  expect(createCalls).toBe(1);

  // 修复前：setForm(null) 会把下面这些全部清空
  await expect(titleInput).toHaveValue('AAPL 财报后复盘');
  await expect(page.locator('.editor-textarea')).toHaveValue('假设：服务业务增速见顶。');
  await expect(page.getByPlaceholder('AAPL', { exact: true })).toHaveValue('AAPL');
  // selected 应指向刚创建的笔记，而不是回到“新建笔记”状态（否则再保存会重复新建）
  await expect(page.locator('.editor-kicker')).toHaveText('编辑笔记');
});
