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

// MEDIUM：resetGlobalLoading（20s 安全兜底）清零计数后，重置前在途的请求之后
// 完成时若仍减 1，会把新请求撑起的计数误减到 0，明明还在加载却把转圈藏掉。
test('resetGlobalLoading 后，重置前在途请求的完成不应误关新请求的 loading', async ({ page }) => {
  // A、B 两个可控释放的挂起请求
  let releaseA: (() => void) | null = null;
  await page.route('**/api/probe-a', async (route) => {
    await new Promise<void>((resolve) => { releaseA = resolve; });
    await json(route, { ok: true });
  });
  await page.route('**/api/probe-b', async (route) => {
    // B 永不主动释放，保持“仍在加载”
    await new Promise<void>(() => { /* hang */ });
    await json(route, { ok: true });
  });

  await page.goto('/welcome');

  // 通过 Vite 模块图导入真实 client，用真实拦截器驱动计数
  await page.evaluate(async () => {
    const mod = await import('/src/api/client.ts');
    const w = window as unknown as {
      __loadingStates: boolean[];
      __client: typeof mod;
    };
    w.__loadingStates = [];
    w.__client = mod;
    mod.onLoadingChange((loading) => { w.__loadingStates.push(loading); });
  });

  // 1) 发起请求 A（挂起）→ loading 应变 true
  await page.evaluate(() => {
    const w = window as unknown as { __client: { http: { get: (u: string) => Promise<unknown> } }; __aPromise: Promise<unknown> };
    w.__aPromise = w.__client.http.get('/api/probe-a').catch(() => undefined);
  });
  await expect.poll(async () => page.evaluate(() => (window as unknown as { __loadingStates: boolean[] }).__loadingStates.at(-1))).toBe(true);

  // 2) 触发安全兜底 reset → loading 变 false，generation 递增
  await page.evaluate(() => (window as unknown as { __client: { resetGlobalLoading: () => void } }).__client.resetGlobalLoading());
  await expect.poll(async () => page.evaluate(() => (window as unknown as { __loadingStates: boolean[] }).__loadingStates.at(-1))).toBe(false);

  // 3) 发起请求 B（挂起）→ loading 再次 true
  await page.evaluate(() => {
    const w = window as unknown as { __client: { http: { get: (u: string) => Promise<unknown> } }; __bPromise: Promise<unknown> };
    w.__bPromise = w.__client.http.get('/api/probe-b').catch(() => undefined);
  });
  await expect.poll(async () => page.evaluate(() => (window as unknown as { __loadingStates: boolean[] }).__loadingStates.at(-1))).toBe(true);

  // 4) 释放 A（属于 reset 前的旧 generation）
  releaseA?.();

  // 5) 等 A 的响应拦截器跑完，断言 loading 仍为 true（B 还在加载）
  await page.waitForTimeout(300);
  const last = await page.evaluate(() => (window as unknown as { __loadingStates: boolean[] }).__loadingStates.at(-1));
  expect(last, 'A（旧 generation）完成不应把 B 仍在加载的 loading 关掉').toBe(true);
});
