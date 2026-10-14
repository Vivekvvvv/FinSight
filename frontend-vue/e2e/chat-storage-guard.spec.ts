import { expect, test, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';
const CHAT_KEY_PREFIX = 'finsight-chat-history:';
const REMOTE_MARKER = 'REMOTE-HISTORY-LOADED-MARKER';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

test.beforeEach(async ({ page }) => {
  // 身份键先写入，再让「聊天历史」键在隐私模式下抛 SecurityError。
  // 按前缀匹配而非拼死 key：chatStorageKey() 用的是运行时 identity.sessionId。
  // theme-storage-guard.spec.ts 的 THEME_KEYS 刻意不含本前缀。
  await page.addInitScript(([sid, uid, email, token, prefix]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);

    const proto = Object.getPrototypeOf(window.localStorage) as Storage;
    const rawGet = proto.getItem.bind(window.localStorage);
    const rawSet = proto.setItem.bind(window.localStorage);
    const rawRemove = proto.removeItem.bind(window.localStorage);
    const deny = (key: string) => {
      if (key.startsWith(prefix)) throw new DOMException('denied', 'SecurityError');
    };
    window.localStorage.getItem = (key: string) => {
      deny(key);
      return rawGet(key);
    };
    window.localStorage.setItem = (key: string, value: string) => {
      deny(key);
      return rawSet(key, value);
    };
    // 真实隐私模式下 removeItem 同样被拒——读取侧 catch 体里那次 removeItem
    // 就是在这里再抛一次，异常冒出 loadLocalHistory。
    window.localStorage.removeItem = (key: string) => {
      deny(key);
      return rawRemove(key);
    };
  }, [SESSION_ID, USER_ID, EMAIL, 'mock-token-e2e', CHAT_KEY_PREFIX]);

  await page.route('**/api/me', (route) =>
    json(route, { success: true, user_id: USER_ID, email: EMAIL, role: 'user', auth_type: 'token', session_id: SESSION_ID }));
  const demo = { success: true, demo_mode: true, overall_status: 'demo', as_of: '2026-06-17T10:00:00Z', missing_services: [], components: [], notes: [] };
  await page.route('**/api/demo/status', (route) => json(route, demo));
  await page.route('**/api/data-sources/status', (route) => json(route, demo));
  await page.route('**/api/portfolio/summary**', (route) => json(route, { success: true, session_id: SESSION_ID, count: 0, positions: [], total_value: 0, total_cost: 0, total_pnl: 0 }));
  await page.route('**/api/user/watchlist**', (route) => json(route, { success: true, count: 0, items: [] }));
});

// HIGH：loadLocalHistory 的 catch 体本身未设防——隐私模式下 getItem 抛
// SecurityError 后，catch 里的 removeItem 再抛一次，异常冒出函数体，
// onMounted 在 loadLocalHistory() 这一行就中断：loadRemoteHistory() 不执行、
// hydrating 永久为 true（persistLocalHistory 从此空转，聊天再也不落盘）。
// 对照 stores/identity.ts:154-162 的逐键 try 才是本仓既有的正解。
test('聊天历史键在隐私模式下抛 SecurityError，远端历史仍应加载', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));

  let historyRequests = 0;
  await page.route('**/api/chat/history**', (route) => {
    historyRequests += 1;
    return json(route, {
      success: true,
      session_id: SESSION_ID,
      count: 1,
      messages: [
        { id: 'remote-1', role: 'assistant', content: REMOTE_MARKER, status: 'done' },
      ],
    });
  });

  await page.goto('/chat');
  await expect(page.locator('.app-shell')).toBeVisible();

  // onMounted 必须跑过 loadRemoteHistory()：请求发出 + 内容渲染。
  await expect(page.getByText(REMOTE_MARKER)).toBeVisible();
  expect(historyRequests, '远端历史请求未发出，说明 onMounted 在 loadLocalHistory 处中断').toBeGreaterThan(0);

  const securityErrors = pageErrors.filter((m) => m.includes('SecurityError'));
  expect(securityErrors, `不应有未捕获的 SecurityError：${securityErrors.join(' | ')}`).toHaveLength(0);
});
