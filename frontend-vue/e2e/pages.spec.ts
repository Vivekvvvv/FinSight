import { expect, test, type Page, type Route } from '@playwright/test';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID = 'vue_e2e_user';
const EMAIL = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

const PORTFOLIO_SUMMARY = {
  success: true,
  session_id: SESSION_ID,
  count: 2,
  positions: [
    { ticker: 'AAPL', shares: 10, avg_cost: 180, live_price: 195, market_value: 1950, name: 'Apple', tags: ['tech'], note: null, price_source: 'mock', updated_at: '2026-06-17T10:00:00Z' },
    { ticker: 'NVDA', shares: 5, avg_cost: 800, live_price: 750, market_value: 3750, name: 'Nvidia', tags: ['ai'], note: null, price_source: 'avg_cost_fallback', updated_at: '2026-06-17T10:00:00Z' },
  ],
  total_value: 5700,
  total_cost: 5800,
  total_pnl: -100,
};

const WATCHLIST = {
  success: true,
  count: 2,
  items: [
    { ticker: 'AAPL', name: 'Apple Inc', tags: ['tech'], watch_reason: '核心持仓' },
    { ticker: 'NVDA', name: 'NVIDIA Corp', tags: ['ai'], watch_reason: 'AI 芯片' },
  ],
};

const DAILY_TASKS = {
  success: true,
  session_id: SESSION_ID,
  count: 2,
  tasks: [
    { id: 't1', title: '复查 AAPL Q3 报告观点', category: 'review', priority: 1, reason: '发布后 7 天 checkpoint' },
    { id: 't2', title: '关注 NVDA 财报发布', category: 'research', priority: 0, reason: '明日盘前' },
  ],
};

const TODAY = {
  success: true,
  as_of: '2026-06-17T10:00:00Z',
  freshness_status: 'live',
  summary: '今日优先复查持仓风险、最新报告和自选异动。',
  portfolio_snapshot: {
    position_count: 2,
    total_cost: 5800,
    total_value: 5700,
    total_pnl: -100,
    risk_positions: [PORTFOLIO_SUMMARY.positions[1]],
  },
  watchlist_movers: [{ ticker: 'AAPL', name: 'Apple Inc', change: 1.2 }],
  alert_feed: [{ id: 'evt_1', ticker: 'NVDA', event_type: 'price_spike', severity: 'high', title: 'NVDA 单日涨幅超 5%', message: '价格异动提醒', triggered_at: '2026-06-17T09:30:00Z' }],
  reports_to_review: [{ report_id: 'rep_001', session_id: SESSION_ID, ticker: 'AAPL', title: 'Apple Q3 深度报告', generated_at: '2026-06-16T09:00:00Z', is_favorite: false, tags: [] }],
  next_actions: [{ id: 'a1', type: 'risk', title: '复查 NVDA 风险', reason: '亏损超过阈值', severity: 'high', target_route: '/portfolio/risk-lens', related_symbol: 'NVDA' }],
};

const QUOTE = {
  ticker: 'AAPL',
  data: {
    currentPrice: 195.5,
    regularMarketChange: 2.3,
    regularMarketChangePercent: 1.19,
    regularMarketVolume: 52_000_000,
    marketCap: 3_000_000_000_000,
    shortName: 'Apple Inc.',
    freshness_status: 'live',
  },
};

const REPORTS = {
  success: true,
  count: 1,
  items: [
    {
      report_id: 'rep_001',
      session_id: SESSION_ID,
      ticker: 'AAPL',
      title: 'Apple Q3 深度报告',
      summary: '服务业务持续增长，需复查估值假设。',
      generated_at: '2026-06-16T09:00:00Z',
      confidence_score: 0.87,
      is_favorite: false,
      tags: ['tech'],
      quality_state: 'pass',
    },
  ],
};

const RESEARCH_QUALITY = {
  success: true,
  as_of: '2026-06-17T10:00:00Z',
  summary: {
    total_reports: 1,
    stale_reports: 0,
    low_quality_reports: 0,
    blocked_reports: 0,
    warn_reports: 0,
    watch_reports: 0,
    reviewed_rate: 1,
    challenged_conclusions: 0,
    health_score: 96,
  },
  top_issues: [],
  next_actions: [],
};

const TIMELINE = {
  success: true,
  symbol: 'AAPL',
  count: 1,
  events: [
    {
      id: 'timeline_1',
      symbol: 'AAPL',
      event_type: 'report',
      title: 'Apple Q3 深度报告更新',
      summary: '报告进入复查。',
      occurred_at: '2026-06-16T09:00:00Z',
      severity: 'medium',
      target_route: '/reports?highlight=rep_001',
    },
  ],
};

const NOTES = {
  success: true,
  count: 1,
  notes: [
    {
      note_id: 'note_1',
      session_id: SESSION_ID,
      user_id: USER_ID,
      ticker: 'AAPL',
      title: 'AAPL 服务业务复查笔记',
      content: '关注毛利率。',
      tags: ['复查'],
      created_at: '2026-06-15T09:00:00Z',
      updated_at: '2026-06-16T09:00:00Z',
    },
  ],
};

const SCREENER_ITEMS = Array.from({ length: 7 }, (_, index) => ({
  symbol: index === 0 ? 'AAPL' : `MOCK${index}`,
  name: index === 0 ? 'Apple Inc.' : `Mock Company ${index}`,
  sector: 'Technology',
  industry: 'Research Tools',
  exchange: 'NASDAQ',
  price: 100 + index,
  market_cap: 3_000_000_000_000 - index * 1_000_000_000,
  volume: 52_000_000 + index * 1000,
  beta: 1.1,
  change_percent: index % 2 === 0 ? 1.2 : -0.8,
}));

test.beforeEach(async ({ page }) => {
  await page.addInitScript(([sid, uid, email, token]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);
  }, [SESSION_ID, USER_ID, EMAIL, 'mock-token-e2e']);

  await page.route('**/api/me', (route) =>
    json(route, { success: true, user_id: USER_ID, email: EMAIL, role: 'user', auth_type: 'token' }));
  await page.route('**/api/demo/status', (route) =>
    json(route, dataSourceStatus()));
  await page.route('**/api/data-sources/status', (route) =>
    json(route, dataSourceStatus()));
  await page.route('**/api/portfolio/summary**', (route) => json(route, PORTFOLIO_SUMMARY));
  await page.route('**/api/user/watchlist**', (route) => json(route, WATCHLIST));
  await page.route('**/api/tasks/daily**', (route) => json(route, DAILY_TASKS));
  await page.route('**/api/today**', (route) => json(route, TODAY));
  await page.route('**/api/what-changed**', (route) => json(route, { success: true, as_of: '2026-06-17T10:00:00Z', count: 0, items: [] }));
  await page.route('**/api/research-quality**', (route) => json(route, RESEARCH_QUALITY));
  await page.route('**/api/quote/**', (route) => json(route, QUOTE));
  await page.route('**/api/timeline/**', (route) => json(route, TIMELINE));
  await page.route('**/api/reports/index**', (route) => json(route, REPORTS));
  await page.route('**/api/reports/replay/**', (route) => json(route, { citations: [] }));
  await page.route('**/api/research-notes**', (route) => json(route, NOTES));
  await page.route('**/api/chat/history**', (route) => json(route, { success: true, session_id: SESSION_ID, messages: [] }));
  await page.route('**/chat/supervisor/stream', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: [
        'data: {"type":"token","content":"已收到研究任务。"}',
        'data: {"type":"done","source":"mock","quality":{"confidence_score":0.8},"metrics":{"request_started_at":"2026-06-17T10:00:00Z"}}',
        '',
      ].join('\n'),
    }));
  await page.route('**/api/screener/filters/meta', (route) =>
    json(route, { success: true, markets: ['US', 'CN', 'HK'], sort_by: ['marketCap', 'price'], sort_order: ['asc', 'desc'], filter_keys: [], source: 'mock' }));
  await page.route('**/api/screener/run', (route) =>
    json(route, {
      success: true,
      market: 'US',
      count: SCREENER_ITEMS.length,
      source: 'mock',
      items: SCREENER_ITEMS,
    }));
  await page.route('**/api/stock/top-list/**', (route) =>
    json(route, { success: true, ticker: '600519.SS', trade_date: '2026-06-17', reason: '机构净买入', net_buy: 12345678 }));
  await page.route('**/api/market/north-flow', (route) =>
    json(route, { success: true, trade_date: '2026-06-17', north_net_inflow: 2345000000, sh_connect: 1200000000, sz_connect: 1145000000 }));
  await page.route('**/api/stock/margin/**', (route) =>
    json(route, { success: true, ticker: '600519.SS', trade_date: '2026-06-17', margin_balance: 456700000, margin_buy: 32000000, margin_repay: 28000000 }));
});

function dataSourceStatus() {
  return {
    success: true,
    demo_mode: true,
    data_source: 'demo',
    overall_status: 'demo',
    as_of: '2026-06-17T10:00:00Z',
    missing_services: ['FMP_API_KEY'],
    components: [
      { key: 'market_us', label: '美股行情', status: 'demo', detail: 'Demo Mode 使用内置行情。', required_action: null },
      { key: 'llm', label: 'AI 研究生成', status: 'demo', detail: '模板化研究输出。', required_action: null },
      { key: 'rag', label: '本地证据检索', status: 'fallback_ready', detail: 'hash fallback 可用。', required_action: null },
    ],
    notes: ['Demo Mode 使用只读示例数据。'],
  };
}

async function expectShellNav(page: Page) {
  await expect(page.locator('.nav-link')).toHaveCount(7);
  for (const label of ['今日工作台', '标的研究', '股票发现', '组合管理', '报告库', '研究笔记', 'AI 助手']) {
    await expect(page.locator('.nav-stack').getByRole('link', { name: new RegExp(label) })).toBeVisible();
  }
  for (const oldLabel of ['系统健康', '龙虎榜', '北向资金', '融资融券', '策略回测', '组合优化', '提醒中心']) {
    await expect(page.locator('.nav-stack').getByText(oldLabel, { exact: true })).toHaveCount(0);
  }
}

test('侧边栏只保留 7 个核心入口', async ({ page }) => {
  await page.goto('/welcome');
  await expectShellNav(page);
});

test('/workbench redirect 到 /welcome，今日任务与持仓风险仍可见', async ({ page }) => {
  await page.goto('/workbench');
  await page.waitForURL('**/welcome');

  await expect(page.getByText('今日任务')).toBeVisible();
  await expect(page.getByText('复查 AAPL Q3 报告观点')).toBeVisible();
  await expect(page.getByText('持仓快照')).toBeVisible();
  await expect(page.getByText('持仓风险提示', { exact: false })).toBeVisible();
});

test('/dashboard/AAPL redirect 到 /dossier/AAPL，行情与研究资产可见', async ({ page }) => {
  await page.goto('/dashboard/AAPL');
  await page.waitForURL('**/dossier/AAPL');

  await expect(page.getByText('AAPL 标的研究档案')).toBeVisible();
  await expect(page.getByTestId('market-overview')).toBeVisible();
  await expect(page.getByRole('heading', { name: '行情概览' })).toBeVisible();
  await expect(page.getByText('Apple Q3 深度报告', { exact: true })).toBeVisible();
  await expect(page.getByText('AAPL 服务业务复查笔记')).toBeVisible();
});

test('/research/qa redirect 到 /chat，智能问答模式可用', async ({ page }) => {
  await page.goto('/research/qa');
  await page.waitForURL('**/chat?mode=qa');

  await expect(page.getByText('当前模式：智能问答', { exact: false })).toBeVisible();
  await expect(page.getByPlaceholder('问点什么', { exact: false })).toBeVisible();
});

test('/portfolio/optimize 和 /backtest redirect 到 /portfolio，组合工具区域可见', async ({ page }) => {
  await page.goto('/portfolio/optimize');
  await page.waitForURL('**/portfolio?tool=optimize');
  await expect(page.getByTestId('portfolio-tools')).toBeVisible();
  await expect(page.getByText('组合优化', { exact: true })).toBeVisible();

  await page.goto('/backtest');
  await page.waitForURL('**/portfolio?tool=backtest');
  await expect(page.getByTestId('portfolio-tools')).toBeVisible();
  await expect(page.getByText('策略回测', { exact: true })).toBeVisible();
});

test('/research/report 与 /research/financials redirect 到报告库工具入口', async ({ page }) => {
  await page.goto('/research/report/AAPL');
  await page.waitForURL('**/reports?tool=generate*ticker=AAPL');
  await expect(page.getByTestId('report-tools')).toBeVisible();
  await expect(page.getByText('AI 研究报告')).toBeVisible();

  await page.goto('/research/financials');
  await page.waitForURL('**/reports?tool=financials');
  await expect(page.getByText('财务复查入口')).toBeVisible();
});

test('/data-sources 和 /system/health 不在主导航，状态抽屉显示数据源信息', async ({ page }) => {
  await page.goto('/data-sources');
  await page.waitForURL('**/welcome?drawer=data');

  await expectShellNav(page);
  const drawer = page.getByLabel('研究上下文');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText('数据源状态')).toBeVisible();
  await expect(drawer.getByText('美股行情')).toBeVisible();
  await expect(drawer.getByText('AI 研究生成')).toBeVisible();

  await page.goto('/system/health');
  await page.waitForURL('**/welcome?drawer=system');
  await expect(page.getByLabel('研究上下文')).toBeVisible();
});

test('股票发现保留 A股市场工具折叠区', async ({ page }) => {
  await page.goto('/stocks');
  await expect(page.getByText('股票发现中心')).toBeVisible();
  await expect(page.getByText('A股市场工具')).toBeVisible();
  await page.getByRole('button', { name: /A股市场工具/ }).click();
  await expect(page.getByText('龙虎榜异动')).toBeVisible();
  await expect(page.getByRole('button', { name: /北向资金作为市场情绪背景/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /融资融券用于观察杠杆变化/ })).toBeVisible();
});

test('7 个核心入口都可访问并保留主导航', async ({ page }) => {
  const entries = [
    { label: '今日工作台', url: '**/welcome' },
    { label: '标的研究', url: '**/dossier/AAPL' },
    { label: '股票发现', url: '**/stocks' },
    { label: '组合管理', url: '**/portfolio' },
    { label: '报告库', url: '**/reports' },
    { label: '研究笔记', url: '**/notes' },
    { label: 'AI 助手', url: '**/chat' },
  ];

  await page.goto('/welcome');
  for (const entry of entries) {
    await page.locator('.nav-stack').getByRole('link', { name: new RegExp(entry.label) }).click();
    await page.waitForURL(entry.url);
    await expectShellNav(page);
  }
});

test('股票发现分页和 A股工具点击都有可见反馈', async ({ page }) => {
  await page.goto('/stocks');
  await expect(page.getByText('第 1 / 2 页')).toBeVisible();
  await page.getByRole('button', { name: '下一页' }).click();
  await expect(page.getByText('第 2 / 2 页')).toBeVisible();

  await page.getByRole('button', { name: /A股市场工具/ }).click();
  await page.getByRole('button', { name: /北向资金作为市场情绪背景/ }).click();
  await expect(page.getByRole('heading', { name: '北向资金' })).toBeVisible();
  await expect(page.getByText('北向净流入')).toBeVisible();
});

test('报告库空状态给出明确入口', async ({ page }) => {
  await page.route('**/api/reports/index**', (route) => json(route, { success: true, count: 0, items: [] }));
  await page.goto('/reports');

  await expect(page.getByText('还没有研究报告')).toBeVisible();
  await expect(page.getByRole('button', { name: '前往 AI 助手' })).toBeVisible();
});

test('Markdown 预览不会执行或注入不可信内容', async ({ page }) => {
  await page.goto('/notes');

  await page.evaluate(() => {
    (window as Window & { markdownPreviewExecuted?: boolean }).markdownPreviewExecuted = false;
  });

  const payload = [
    '<script>window.markdownPreviewExecuted = true</script>',
    '<img src=x onerror="window.markdownPreviewExecuted = true">',
    '[unsafe](javascript:window.markdownPreviewExecuted=true)',
    '[quoted](https://example.com/&quot; onmouseover=&quot;window.markdownPreviewExecuted=true)',
  ].join('\n\n');

  await page.getByPlaceholder('记录你的假设、证据、反证和下一步验证动作…').fill(payload);
  await page.locator('.markdown-editor .toolbar-btn').last().click();

  const preview = page.locator('.markdown-editor .preview-pane');
  await expect(preview).toBeVisible();
  await expect(preview.locator('script')).toHaveCount(0);
  await expect(preview.locator('[onerror], [onmouseover]')).toHaveCount(0);
  await expect(preview.locator('a[href^="javascript:"]')).toHaveCount(0);
  await expect(preview.locator('a').first()).toHaveAttribute('href', '#');
  await expect.poll(() => page.evaluate(
    () => Boolean((window as Window & { markdownPreviewExecuted?: boolean }).markdownPreviewExecuted),
  )).toBe(false);
});

test('组合管理空持仓状态可直接添加或导入', async ({ page }) => {
  await page.route('**/api/portfolio/summary**', (route) =>
    json(route, { success: true, session_id: SESSION_ID, count: 0, positions: [], total_value: 0, total_cost: 0, total_pnl: 0 }));
  await page.goto('/portfolio');

  await expect(page.getByText('还没有持仓记录')).toBeVisible();
  await expect(page.getByRole('button', { name: '手动添加' })).toBeVisible();
  await expect(page.getByRole('button', { name: '导入 CSV' }).nth(1)).toBeVisible();
});

test('AI 助手发送时按钮进入 loading disabled 状态', async ({ page }) => {
  await page.route('**/chat/supervisor/stream', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 600));
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: [
        'data: {"type":"token","content":"测试回复"}',
        'data: {"type":"done","source":"mock","quality":{"confidence_score":0.8},"metrics":{"request_started_at":"2026-06-17T10:00:00Z"}}',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/chat');
  await page.getByPlaceholder('问点什么', { exact: false }).fill('AAPL 今天有什么变化');
  await page.getByRole('button', { name: '发送研究任务' }).click();

  const sendingButton = page.getByRole('button', { name: /执行中/ });
  await expect(sendingButton).toBeDisabled();
  await expect(page.locator('.bubble-body').filter({ hasText: '测试回复' })).toBeVisible();
});

test('移动端底部导航不遮挡主要操作', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/chat');

  const bottomNav = page.getByLabel('移动端导航');
  await expect(bottomNav).toBeVisible();
  const sendButton = page.getByRole('button', { name: '发送研究任务' });
  await expect(sendButton).toBeVisible();

  const navBox = await bottomNav.boundingBox();
  const buttonBox = await sendButton.boundingBox();
  expect(navBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(buttonBox!.y + buttonBox!.height).toBeLessThan(navBox!.y);
});

test('数据源状态失败时抽屉给出可操作提示', async ({ page }) => {
  await page.unroute('**/api/data-sources/status');
  await page.route('**/api/data-sources/status', (route) =>
    json(route, { success: false, detail: 'mock service unavailable' }, 503));

  await page.goto('/data-sources');
  await page.waitForURL('**/welcome?drawer=data');

  const drawer = page.getByLabel('研究上下文');
  await expect(drawer).toBeVisible();
  await expect(page.getByRole('button', { name: /状态异常|检测中|DEMO 数据/ })).toBeVisible();
  await expect(drawer.getByText('服务暂时不可用，请稍后刷新重试。')).toBeVisible();
  await expect(drawer.getByRole('button', { name: '重试' })).toBeVisible();
});

test('组合页移除持仓时按钮有 loading disabled 反馈', async ({ page }) => {
  await page.route('**/api/portfolio/positions/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 600));
    await json(route, { success: true, ticker: 'AAPL' });
  });

  await page.goto('/portfolio');
  const firstPosition = page.locator('.pos-card').filter({ hasText: 'AAPL' });
  await expect(firstPosition).toBeVisible();
  await expect(firstPosition.getByText('测试数据')).toBeVisible();
  await firstPosition.getByRole('button', { name: '移除' }).click();

  const removingButton = firstPosition.getByRole('button', { name: /移除中/ });
  await expect(removingButton).toBeDisabled();
});
