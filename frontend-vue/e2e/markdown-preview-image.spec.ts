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
  await page.route('**/api/research-notes**', (route) => json(route, { success: true, count: 0, notes: [] }));
});

// LOW/MEDIUM：链接正则 \[..\]\(..\) 排在图片正则之前，会先吃掉 ![alt](url) 里的
// [alt](url)，导致 Markdown 预览里上传的图片永远渲染不成 <img>，只剩“!”+链接。
test('Markdown 预览：图片语法应渲染成 <img> 而不是被链接正则吃掉', async ({ page }) => {
  await page.goto('/notes');

  const editor = page.locator('.editor-textarea');
  await expect(editor).toBeVisible();
  await editor.fill('![chart](https://example.com/a.png)');

  await page.locator('button[title="预览"]').click();

  const previewImg = page.locator('.preview-pane img');
  await expect(previewImg).toHaveCount(1);
  await expect(previewImg).toHaveAttribute('src', 'https://example.com/a.png');
});
