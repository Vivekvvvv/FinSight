import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

const REPORTS = {
  success: true,
  count: 1,
  items: [
    {
      report_id: 'rep_note_001',
      session_id: SESSION_ID,
      ticker: 'AAPL',
      title: 'Apple Q3 深度报告',
      summary: '服务业务持续增长，需复查估值假设。',
      generated_at: '2026-06-16T09:00:00Z',
      confidence_score: 0.87,
      is_favorite: false,
      tags: ['tech'],
      quality_state: 'pass',
      user_note: '',
    },
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
  await page.route('**/api/reports/index**', (route) => json(route, REPORTS));
  await page.route('**/api/reports/*/viewed', (route) => json(route, { success: true }));
  await page.route('**/api/reports/replay/**', (route) => json(route, { success: true, report: null, citations: [] }));
  await page.route('**/api/research-quality**', (route) =>
    json(route, { success: true, as_of: '2026-06-17T10:00:00Z', summary: { total_reports: 1, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 1, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
});

// HIGH：备注保存是 600ms 防抖，关闭侧栏若只 clearTimeout 不 flush，会把刚敲的备注丢掉。
test('600ms 内关闭报告侧栏，仍会把未落盘的备注 flush 保存', async ({ page }) => {
  let notePatch: { reportId?: string; note?: string } | null = null;
  await page.route('**/api/reports/*/note', async (route) => {
    const url = route.request().url();
    const reportId = decodeURIComponent(url.split('/api/reports/')[1].split('/note')[0]);
    let note = '';
    try { note = (route.request().postDataJSON() as { user_note?: string }).user_note || ''; } catch { /* ignore */ }
    notePatch = { reportId, note };
    return json(route, { success: true });
  });

  await page.goto('/reports');
  await expect(page.locator('.app-shell')).toBeVisible();

  // 打开报告侧栏
  await expect(page.locator('.report-card').first()).toBeVisible();
  await page.locator('.report-card').first().click();
  const textarea = page.locator('.note-area');
  await expect(textarea).toBeVisible();

  // 输入备注后立刻关闭（远早于 600ms 防抖触发）
  await textarea.fill('复查估值假设：关注服务业务毛利');
  await page.locator('.sidebar-close').first().click();

  // flush 应已把这条备注 PATCH 出去
  await expect.poll(() => notePatch?.note, { timeout: 3000 }).toBe('复查估值假设：关注服务业务毛利');
  expect(notePatch?.reportId).toBe('rep_note_001');
});
