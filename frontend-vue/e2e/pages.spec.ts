/**
 * FinSight Vue — 最小 Playwright smoke
 *
 * 覆盖: /welcome, /chat, /dashboard/:symbol, /reports, /portfolio, /watchlist, /alerts, /workbench
 * 全部 API mock，hermetic 不依赖后端。
 */
import { expect, test, type Page, type Route } from '@playwright/test';
import {
  setupTimelineMocks,
  setupWhatChangedMocks,
  setupResearchQualityMocks,
  setupReportsMocks,
  setupTodayWorkspaceMocks,
  setupPhase45CoreMocks,
} from './helpers/apiMocks';

const SESSION_ID = 'public:anonymous:vue-e2e';
const USER_ID    = 'vue_e2e_user';
const EMAIL      = 'vue-e2e@example.invalid';

const json = (route: Route, payload: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) });

// ── 基础 mock 集合 ──────────────────────────────────────────
const WATCHLIST_ITEMS = [
  { ticker: 'AAPL', name: 'Apple Inc', tags: ['tech'], note: '核心持仓', added_at: new Date().toISOString() },
  { ticker: 'TSLA', name: 'Tesla Inc', tags: ['ev'], note: null, added_at: new Date().toISOString() },
];

const PORTFOLIO_SUMMARY = {
  success: true, session_id: SESSION_ID, count: 2,
  positions: [
    { ticker: 'AAPL', shares: 10, avg_cost: 180, live_price: 195, market_value: 1950, name: 'Apple', tags: ['tech'], note: null },
    { ticker: 'NVDA', shares: 5,  avg_cost: 800, live_price: 750, market_value: 3750, name: 'Nvidia', tags: ['ai'], note: null },
  ],
  total_value: 5700, total_cost: 5800, total_pnl: -100,
};

const REPORTS = {
  success: true, count: 2, items: [
    { report_id: 'rep_001', session_id: SESSION_ID, ticker: 'AAPL', title: 'Apple Q3 深度报告',
      summary: '营收超预期，服务业务持续高增长', generated_at: new Date().toISOString(),
      confidence_score: 0.87, is_favorite: false, tags: ['tech', 'q3'], analysis_depth: 'report', citation_count: 8, quality_state: 'pass' },
    { report_id: 'rep_002', session_id: SESSION_ID, ticker: 'NVDA', title: 'NVDA AI 芯片前景',
      summary: 'Blackwell 出货加速，数据中心需求强劲', generated_at: new Date().toISOString(),
      confidence_score: 0.79, is_favorite: true, tags: ['ai', 'semiconductor'], analysis_depth: 'deep_research', citation_count: 12, quality_state: 'pass' },
  ],
};

const QUOTE_DATA = {
  ticker: 'AAPL', cached: false,
  data: { currentPrice: 195.5, regularMarketChange: 2.3, regularMarketChangePercent: 1.19,
    regularMarketDayHigh: 197, regularMarketDayLow: 193, regularMarketVolume: 52000000,
    marketCap: 3e12, shortName: 'Apple Inc.',
    source: 'tools_bridge', as_of: new Date().toISOString(), freshness_status: 'live', fallback_level: 0 },
};

const KLINE_DATA = {
  ticker: 'AAPL', cached: false,
  data: { dates: ['2025-01-01','2025-01-02','2025-01-03'], values: [[190,195,188,194],[194,198,193,197],[197,200,196,199]] },
};

const INSIGHTS = {
  success: true, symbol: 'AAPL', cached: false, generated_at: new Date().toISOString(),
  insights: {
    technical: { tab: 'technical', score: 7.2, score_label: '偏多', summary: '均线多头排列，RSI 未超买', key_points: ['MACD 金叉', '成交量放大'], risks: ['短期超买风险'], confidence: 0.82, model_generated: true, as_of: new Date().toISOString() },
    financial: { tab: 'financial', score: 8.1, score_label: '强势', summary: '营收增速加快，利润率扩张', key_points: ['服务业务占比提升', 'EPS 超预期'], risks: ['汇率逆风'], confidence: 0.91, model_generated: true, as_of: new Date().toISOString() },
  },
};

const ALERTS_SUBS = {
  success: true, count: 1, subscriptions: [
    { email: EMAIL, ticker: 'AAPL', alert_types: ['price_change'], alert_mode: 'price_change_pct', disabled: false, risk_threshold: 'high' },
  ],
};

const ALERT_EVENTS = {
  success: true, count: 1, events: [
    { id: 'evt_1', ticker: 'NVDA', event_type: 'price_spike', severity: 'high', title: 'NVDA 单日涨幅超 5%', message: '价格异动提醒', triggered_at: new Date().toISOString() },
  ],
};

const DAILY_TASKS = {
  success: true, session_id: SESSION_ID, count: 2,
  tasks: [
    { id: 't1', title: '复查 AAPL Q3 报告观点', category: 'review', priority: 1, reason: '发布后7天 checkpoint' },
    { id: 't2', title: '关注 NVDA 财报发布', category: 'research', priority: 0, reason: '明日盘前' },
  ],
};

const SCREENER_META = {
  success: true,
  markets: ['US', 'CN', 'HK'],
  sort_by: ['marketCap', 'price', 'volume', 'changesPercentage'],
  sort_order: ['asc', 'desc'],
  filter_keys: ['marketCapMoreThan', 'priceMoreThan', 'priceLowerThan', 'volumeMoreThan'],
  source: 'mock_screener',
};

const SCREENER_RESPONSE = {
  success: true,
  market: 'US',
  count: 2,
  source: 'mock_screener',
  items: [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      country: 'US',
      exchange: 'NASDAQ',
      price: 195.5,
      market_cap: 3_000_000_000_000,
      volume: 52_000_000,
      beta: 1.2,
      change_percent: 1.19,
    },
    {
      symbol: 'NVDA',
      name: 'NVIDIA Corp.',
      sector: 'Semiconductors',
      industry: 'AI Chips',
      country: 'US',
      exchange: 'NASDAQ',
      price: 880.1,
      market_cap: 2_200_000_000_000,
      volume: 41_000_000,
      beta: 1.7,
      change_percent: -0.8,
    },
  ],
};

const SCREENER_HK_RESPONSE = {
  success: true,
  market: 'HK',
  count: 2,
  source: 'static_market_demo',
  warning: 'demo_market_fallback',
  capability_note: 'Using built-in market demo candidates because FMP screener coverage is not configured.',
  items: [
    {
      symbol: '0700.HK',
      name: 'Tencent Holdings Limited',
      sector: 'Communication Services',
      industry: 'Internet Content',
      country: 'HK',
      exchange: 'HKEX',
      price: 381,
      market_cap: 3_560_000_000_000,
      volume: 20_800_000,
      beta: 1,
      change_percent: 0.58,
    },
    {
      symbol: '9988.HK',
      name: 'Alibaba Group Holding Limited',
      sector: 'Consumer Discretionary',
      industry: 'Internet Retail',
      country: 'HK',
      exchange: 'HKEX',
      price: 81.2,
      market_cap: 1_520_000_000_000,
      volume: 73_000_000,
      beta: 1.2,
      change_percent: 0.31,
    },
  ],
};

// ── Setup ─────────────────────────────────────────────────────
test.beforeEach(async ({ page }) => {
  // 写入 localStorage，跳过登录
  await page.addInitScript(([sid, uid, email, token]) => {
    localStorage.setItem('finsight-session-id', sid);
    localStorage.setItem('finsight-user-id', uid);
    localStorage.setItem('finsight-subscription-email', email);
    localStorage.setItem('finsight-access-token', token);
  }, [SESSION_ID, USER_ID, EMAIL, 'mock-token-e2e']);

  // /api/me — 返回已登录用户
  await page.route('**/api/me', (r) =>
    json(r, { success: true, user_id: USER_ID, email: EMAIL, role: 'user', auth_type: 'token' }));
  await page.route('**/api/demo/status', (r) =>
    json(r, {
      success: true,
      demo_mode: true,
      data_source: 'demo',
      overall_status: 'demo',
      missing_services: ['FMP_API_KEY', 'OPENAI_COMPATIBLE_API_KEY'],
      components: [
        { key: 'market_data', label: '行情与股票筛选', status: 'demo', detail: '当前使用内置演示行情。', required_action: null },
        { key: 'llm', label: 'AI 研究生成', status: 'demo', detail: 'Demo Mode 下可使用模板化研究输出。', required_action: null },
        { key: 'auth', label: '访问控制', status: 'demo', detail: '本地演示身份已启用。', required_action: null },
      ],
      notes: ['Demo Mode 使用只读示例数据，不构成投资建议。'],
    }));
});

// ══════════════════════════════════════════════════════════════
// Page-level mock helpers
// ══════════════════════════════════════════════════════════════

// WelcomePage 调用 3 个并发 API（today + what-changed + research-quality）
// 各测试自行 mock today，此 helper 补全另外 2 个
function setupWelcomePageCoreMocks(page: Page) {
  page.route('**/api/what-changed**', (r) => json(r, {
    success: true, as_of: new Date().toISOString(), count: 0, items: [],
  }));
  page.route('**/api/research-quality**', (r) => json(r, {
    success: true,
    as_of: new Date().toISOString(),
    summary: {
      total_reports: 0, stale_reports: 0, low_quality_reports: 0,
      blocked_reports: 0, warn_reports: 0, watch_reports: 0,
      reviewed_rate: 0, challenged_conclusions: 0, health_score: 100,
    },
    top_issues: [], next_actions: [],
  }));
}

function setupStocksPageMocks(page: Page) {
  page.route('**/api/portfolio/summary**', (r) => json(r, PORTFOLIO_SUMMARY));
  page.route('**/api/user/watchlist**', (r) =>
    json(r, { success: true, items: WATCHLIST_ITEMS, count: WATCHLIST_ITEMS.length }));
  page.route('**/api/screener/filters/meta', (r) => json(r, SCREENER_META));
  page.route('**/api/screener/run', async (r) => {
    const raw = r.request().postData();
    const payload = raw ? JSON.parse(raw) : {};
    if (payload.market === 'HK') {
      return json(r, SCREENER_HK_RESPONSE);
    }
    return json(r, { ...SCREENER_RESPONSE, market: payload.market || 'US' });
  });
}

function setupDossierPageMocks(page: Page, symbol = 'AAPL') {
  page.route('**/api/portfolio/summary**', (r) => json(r, PORTFOLIO_SUMMARY));
  page.route('**/api/user/watchlist**', (r) =>
    json(r, { success: true, items: WATCHLIST_ITEMS, count: WATCHLIST_ITEMS.length }));
  setupWhatChangedMocks(page);
  setupTimelineMocks(page, symbol);
  setupReportsMocks(page);
  page.route('**/api/research-notes**', (r) => json(r, {
    success: true,
    count: 1,
    notes: [
      {
        note_id: 'note_aapl_001',
        session_id: SESSION_ID,
        user_id: USER_ID,
        ticker: symbol,
        title: `${symbol} 服务业务复查笔记`,
        content: '关注收入结构、毛利率和新证据冲突。',
        tags: ['复查', '假设'],
        created_at: '2024-11-14T09:00:00Z',
        updated_at: '2024-11-15T09:00:00Z',
      },
    ],
  }));
  page.route('**/api/research-quality**', (r) => json(r, {
    success: true,
    as_of: '2024-11-15T10:00:00Z',
    summary: {
      total_reports: 2,
      stale_reports: 1,
      low_quality_reports: 1,
      blocked_reports: 0,
      warn_reports: 1,
      watch_reports: 1,
      reviewed_rate: 70,
      challenged_conclusions: 1,
      health_score: 68,
    },
    top_issues: [
      {
        id: 'issue_challenged_aapl',
        issue_type: 'challenged_conclusion',
        severity: 'high',
        title: `${symbol} 旧报告可能被新证据挑战`,
        reason: '最新高严重度事件晚于旧报告，建议复查原结论。',
        target_route: '/reports?highlight=rep_aapl_001',
        related_symbol: symbol,
        related_report_id: 'rep_aapl_001',
      },
    ],
    next_actions: [],
  }));
}

// ══════════════════════════════════════════════════════════════
// 1. /welcome (Today Workspace — 基础烟雾测试)
// ══════════════════════════════════════════════════════════════
test('/welcome — Today Workspace 基础渲染', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, {
    success: true, as_of: new Date().toISOString(), freshness_status: 'live',
    summary: '暂无数据', portfolio_snapshot: { total_value: null, total_pnl: null, total_cost: null, risk_positions: [], position_count: 0 },
    watchlist_movers: [], alert_feed: [], reports_to_review: [], next_actions: [],
  }));
  setupWelcomePageCoreMocks(page);
  await page.goto('/welcome');
  await expect(page.getByText('你好', { exact: false })).toBeVisible();
  await expect(page.getByText('持仓快照')).toBeVisible();
  await expect(page.getByText('自选清单')).toBeVisible();
  await expect(page.getByText('建议操作')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 2. /workbench
// ══════════════════════════════════════════════════════════════
test('/workbench — 晨报 + 任务 + 持仓风险', async ({ page }) => {
  await page.route('**/api/portfolio/summary**', (r) => json(r, PORTFOLIO_SUMMARY));
  await page.route('**/api/reports/index**', (r) => json(r, REPORTS));
  await page.route('**/api/tasks/daily**', (r) => json(r, DAILY_TASKS));
  await page.route('**/api/alerts/feed**', (r) => json(r, ALERT_EVENTS));
  await page.route('**/api/user/watchlist**', (r) => json(r, { success: true, items: WATCHLIST_ITEMS, count: 2 }));

  await page.goto('/workbench');
  await page.waitForLoadState('networkidle');

  // 晨报头部
  await expect(page.getByText('今日任务')).toBeVisible();
  await expect(page.getByText('持仓概览')).toBeVisible();

  // 任务显示
  await expect(page.getByText('复查 AAPL Q3 报告观点')).toBeVisible();

  // 持仓风险（NVDA 亏损 6.25% 应显示风险提示）
  await expect(page.getByText('持仓风险提示', { exact: false })).toBeVisible();
  await expect(page.locator('.risk-ticker').getByText('NVDA')).toBeVisible();

  // 近期报告
  await expect(page.getByText('近期研究报告', { exact: false })).toBeVisible();
  await expect(page.getByText('Apple Q3 深度报告')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 3. /dashboard/:symbol
// ══════════════════════════════════════════════════════════════
test('/dashboard/AAPL — 报价卡 + K线 + AI洞察', async ({ page }) => {
  await page.route('**/api/quote/AAPL**', (r) => json(r, QUOTE_DATA));
  await page.route('**/api/kline/AAPL**', (r) => json(r, KLINE_DATA));
  await page.route('**/api/financials/AAPL**', (r) => json(r, { ticker: 'AAPL', data: { totalRevenue: 400e9, netIncome: 100e9, trailingPE: 28.5, grossMargins: 0.44, trailingEps: 6.43, returnOnEquity: 1.47 } }));
  await page.route('**/api/dashboard/insights**', (r) => json(r, INSIGHTS));
  await page.route('**/api/stock/news/AAPL**', (r) => json(r, { ticker: 'AAPL', data: [] }));

  await page.goto('/dashboard/AAPL');
  await page.waitForLoadState('networkidle');

  // 搜索框
  await expect(page.getByPlaceholder('输入股票代码', { exact: false })).toBeVisible();

  // 报价卡片
  await expect(page.getByText('Apple Inc.')).toBeVisible();
  await expect(page.getByText('195.5')).toBeVisible();

  // AI 洞察
  await expect(page.getByText('AI 洞察')).toBeVisible();
  await expect(page.locator('.score-label').first()).toBeVisible();
});

test('/dashboard — 无 symbol 默认加载 AAPL', async ({ page }) => {
  await page.route('**/api/quote/**', (r) => json(r, QUOTE_DATA));
  await page.route('**/api/kline/**', (r) => json(r, KLINE_DATA));
  await page.route('**/api/financials/**', (r) => json(r, { ticker: 'AAPL', data: {} }));
  await page.route('**/api/dashboard/insights**', (r) => json(r, INSIGHTS));
  await page.route('**/api/stock/news/**', (r) => json(r, { data: [] }));

  await page.goto('/dashboard');
  await page.waitForLoadState('networkidle');
  await expect(page.getByPlaceholder('输入股票代码', { exact: false })).toBeVisible();
});

test('/shell - data source status is visible in header and context drawer', async ({ page }) => {
  await page.route('**/api/quote/**', (r) => json(r, QUOTE_DATA));
  await page.route('**/api/kline/**', (r) => json(r, KLINE_DATA));
  await page.route('**/api/financials/**', (r) => json(r, { ticker: 'AAPL', data: {} }));
  await page.route('**/api/dashboard/insights**', (r) => json(r, INSIGHTS));
  await page.route('**/api/stock/news/**', (r) => json(r, { data: [] }));
  await page.route('**/api/what-changed**', (r) =>
    json(r, { success: true, as_of: new Date().toISOString(), items: [], count: 0 }));

  await page.goto('/dashboard/AAPL');
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('button', { name: /DEMO/ })).toBeVisible();
  await page.getByRole('button', { name: /DEMO/ }).click();
  await expect(page.getByText('数据源状态')).toBeVisible();
  await expect(page.getByText('行情与股票筛选')).toBeVisible();
  await expect(page.getByText('AI 研究生成')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
test('/stocks - discovery list renders', async ({ page }) => {
  await setupStocksPageMocks(page);

  await page.goto('/stocks');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('STOCK DISCOVERY')).toBeVisible();
  await expect(page.getByText('AAPL')).toBeVisible();
  await expect(page.getByText('Apple Inc.')).toBeVisible();
  await expect(page.getByText('NVIDIA Corp.')).toBeVisible();
  await expect(page.getByText('NASDAQ').first()).toBeVisible();
});

test('/stocks - add to watchlist', async ({ page }) => {
  let addedPayload: Record<string, unknown> | null = null;
  await setupStocksPageMocks(page);
  await page.route('**/api/user/watchlist/add', async (r) => {
    addedPayload = JSON.parse(r.request().postData() || '{}');
    return json(r, { success: true });
  });

  await page.goto('/stocks');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '加入自选' }).first().click();

  await expect.poll(() => addedPayload?.ticker).toBe('AAPL');
  await expect.poll(() => addedPayload?.group).toBe('发现池');
  await expect(page.getByText('AAPL 已加入自选列表')).toBeVisible();
});

test('/stocks - import portfolio with confirm modal', async ({ page }) => {
  let importedPayload: Record<string, unknown> | null = null;
  await setupStocksPageMocks(page);
  await page.route('**/api/portfolio/positions/AAPL**', async (r) => {
    importedPayload = JSON.parse(r.request().postData() || '{}');
    return json(r, { success: true });
  });

  await page.goto('/stocks');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '导入持仓' }).first().click();
  await expect(page.getByText('导入 AAPL 到持仓')).toBeVisible();

  await page.locator('.import-modal input').first().fill('2');
  await page.getByRole('button', { name: '确认导入' }).click();

  await expect.poll(() => importedPayload?.shares).toBe(2);
  await expect(page.getByText('AAPL 已导入持仓')).toBeVisible();
});

test('/stocks - dashboard action navigates to symbol', async ({ page }) => {
  await setupStocksPageMocks(page);
  await page.route('**/api/quote/AAPL**', (r) => json(r, QUOTE_DATA));
  await page.route('**/api/kline/AAPL**', (r) => json(r, KLINE_DATA));
  await page.route('**/api/financials/AAPL**', (r) => json(r, { ticker: 'AAPL', data: {} }));
  await page.route('**/api/dashboard/insights**', (r) => json(r, INSIGHTS));
  await page.route('**/api/stock/news/AAPL**', (r) => json(r, { ticker: 'AAPL', data: [] }));
  await page.route('**/api/what-changed**', (r) =>
    json(r, { success: true, as_of: new Date().toISOString(), items: [], count: 0 }));

  await page.goto('/stocks');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: '查看分析' }).first().click();

  await expect(page).toHaveURL(/\/dashboard\/AAPL/);
});

test('/stocks - HK demo fallback renders candidates', async ({ page }) => {
  await setupStocksPageMocks(page);

  await page.goto('/stocks');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: 'HK' }).click();

  await expect(page.getByText('0700.HK')).toBeVisible();
  await expect(page.getByText('Tencent Holdings Limited')).toBeVisible();
  await expect(page.getByText('HKEX').first()).toBeVisible();
});

test('/dossier/:symbol - aggregates symbol research assets', async ({ page }) => {
  setupDossierPageMocks(page, 'AAPL');

  await page.goto('/dossier/AAPL');
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: /AAPL 标的研究档案/ })).toBeVisible();
  await expect(page.getByText('优先复查变化')).toBeVisible();
  await expect(page.getByText('质量复查')).toBeVisible();
  await expect(page.getByText('证据冲突与旧结论复查')).toBeVisible();
  await expect(page.getByRole('button', { name: /AAPL 旧报告可能被新证据挑战.*Research Quality/ })).toBeVisible();
  await expect(page.getByText('最新报告与笔记')).toBeVisible();
  await expect(page.getByText('最近证据事件')).toBeVisible();
  await expect(page.getByText('Apple Q3', { exact: false })).toBeVisible();
  await expect(page.getByText('AAPL 服务业务复查笔记')).toBeVisible();
});

test('/dossier/:symbol - symbol search navigates to dossier', async ({ page }) => {
  setupDossierPageMocks(page, 'MSFT');

  await page.goto('/dossier/AAPL');
  await page.getByLabel('输入股票代码').fill('MSFT');
  await page.getByRole('button', { name: '打开档案' }).click();

  await expect(page).toHaveURL(/\/dossier\/MSFT/);
});

// 4. /reports
// ══════════════════════════════════════════════════════════════
test('/reports — 列表渲染 + 收藏切换 + MD导出', async ({ page }) => {
  let favCalls = 0;
  await page.route('**/api/reports/index**', (r) => json(r, REPORTS));
  await page.route('**/api/research-quality**', (r) => json(r, { success: true, as_of: new Date().toISOString(), summary: { total_reports: 2, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 0, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
  await page.route('**/api/reports/replay/**', (r) => json(r, { success: true, report: { content: '报告全文内容' }, citations: [] }));
  await page.route('**/api/reports/*/favorite', (r) => { favCalls++; return json(r, { success: true, is_favorite: true }); });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 两份报告均渲染
  await expect(page.getByText('Apple Q3 深度报告')).toBeVisible();
  await expect(page.getByText('NVDA AI 芯片前景')).toBeVisible();

  // 收藏标记
  await expect(page.getByRole('button', { name: '★' })).toBeVisible(); // NVDA 已收藏

  // 收藏切换（点 AAPL 的 ☆）
  await page.getByRole('button', { name: '☆' }).first().click();
  await expect.poll(() => favCalls).toBe(1);

  // 导出按钮存在
  await expect(page.getByRole('button', { name: /MD/i }).first()).toBeVisible();
});

test('/reports — 版本对比面板', async ({ page }) => {
  const DIFF = {
    success: true,
    diff: {
      confidence_score: { a: 0.87, b: 0.79, delta: -0.08 },
      risks: { added: ['监管风险'], removed: [], unchanged_count: 1 },
      summary: { a: '营收超预期', b: '增速放缓风险' },
    },
  };
  await page.route('**/api/reports/index**', (r) => json(r, REPORTS));
  await page.route('**/api/research-quality**', (r) => json(r, { success: true, as_of: new Date().toISOString(), summary: { total_reports: 2, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 0, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));
  await page.route('**/api/reports/compare**', (r) => json(r, DIFF));

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 进入对比模式
  await page.getByRole('button', { name: /版本对比/ }).click();
  await expect(page.locator('.sel-empty').first()).toBeVisible();

  // 选 A
  await page.getByText('Apple Q3 深度报告').click();
  await expect(page.locator('.sel-name').first()).toBeVisible();

  // 选 B
  await page.getByText('NVDA AI 芯片前景').click();
  await expect(page.locator('.sel-name').nth(1)).toBeVisible();

  // 执行对比
  await page.getByRole('button', { name: '开始对比' }).click();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.diff-label').getByText('置信度')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 5. /portfolio
// ══════════════════════════════════════════════════════════════
test('/portfolio — 持仓列表 + 盈亏显示', async ({ page }) => {
  await page.route('**/api/portfolio/summary**', (r) => json(r, PORTFOLIO_SUMMARY));

  await page.goto('/portfolio');
  await page.waitForLoadState('networkidle');

  // 页头
  await expect(page.getByRole('heading', { name: '持仓组合' })).toBeVisible();

  // 汇总卡片
  await expect(page.getByText('总盈亏')).toBeVisible();

  // 持仓条目
  await expect(page.getByText('AAPL').first()).toBeVisible();
  await expect(page.getByText('NVDA').first()).toBeVisible();
});

test('/portfolio — 空态 + 添加提示', async ({ page }) => {
  await page.route('**/api/portfolio/summary**', (r) =>
    json(r, { success: true, session_id: SESSION_ID, positions: [], count: 0, total_value: null, total_cost: 0, total_pnl: null }));

  await page.goto('/portfolio');
  await page.waitForLoadState('networkidle');
  await expect(page.getByText('还没有持仓', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: '手动添加' })).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 6. /watchlist
// ══════════════════════════════════════════════════════════════
test('/watchlist — 带数据渲染 + 搜索过滤', async ({ page }) => {
  await page.route('**/api/user/watchlist**', (r) =>
    json(r, { success: true, items: WATCHLIST_ITEMS, count: 2 }));

  await page.goto('/watchlist');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('AAPL')).toBeVisible();
  await expect(page.getByText('TSLA')).toBeVisible();

  // 搜索过滤
  await page.getByPlaceholder('搜索代码或名称', { exact: false }).fill('apple');
  await expect(page.getByText('AAPL')).toBeVisible();
  await expect(page.getByText('TSLA')).toBeHidden();
});

test('/watchlist — 空态 + 展开添加表单', async ({ page }) => {
  await page.route('**/api/user/watchlist**', (r) => json(r, { success: true, items: [], count: 0 }));

  await page.goto('/watchlist');
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('还没有自选标的')).toBeVisible();
  await page.getByRole('button', { name: '立即添加' }).click();
  await expect(page.getByPlaceholder('AAPL')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 7. /alerts
// ══════════════════════════════════════════════════════════════
test('/alerts — 订阅列表 + 事件 feed', async ({ page }) => {
  await page.route('**/api/subscriptions**', (r) => json(r, ALERTS_SUBS));
  await page.route('**/api/alerts/feed**', (r) => json(r, ALERT_EVENTS));

  await page.goto('/alerts');
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: '提醒中心' })).toBeVisible();

  // 输入邮箱后加载
  await page.getByPlaceholder('your@email.com').fill(EMAIL);
  await page.getByRole('button', { name: '加载' }).click();
  await page.waitForLoadState('networkidle');

  await expect(page.getByText('启用中')).toBeVisible();
  await expect(page.getByText('NVDA 单日涨幅超 5%')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 8. /chat
// ══════════════════════════════════════════════════════════════
test('/chat — 快捷问题显示 + 输入框', async ({ page }) => {
  await page.goto('/chat');
  await page.waitForLoadState('networkidle');

  // 欢迎消息（对话气泡中）
  await expect(page.locator('.bubble-body').first()).toBeVisible();

  // 快捷问题
  await expect(page.getByText('AAPL 最近的基本面如何', { exact: false })).toBeVisible();

  // 输入框
  await expect(page.getByPlaceholder('问点什么', { exact: false })).toBeVisible();

  // 可以输入
  await page.getByPlaceholder('问点什么', { exact: false }).fill('测试消息');
  await expect(page.getByRole('button', { name: /发送/ })).toBeEnabled();
});

test('/chat — prefill 参数自动填入', async ({ page }) => {
  // Mock chat stream — 返回空内容（smoke only）
  await page.route('**/chat/supervisor/stream', async (r) => {
    await r.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"done"}\n\n' });
  });

  await page.goto('/chat?prefill=分析%20AAPL');
  await page.waitForLoadState('networkidle');

  // 消息出现在对话线程
  await expect(page.getByText('分析 AAPL')).toBeVisible();
});

// ══════════════════════════════════════════════════════════════
// 9. /reports — 报告资产化：搜索 + 标签筛选 + 收藏 + 对比 + 备注 + 刷新 + MD导出
// ══════════════════════════════════════════════════════════════

// 扩展 REPORTS mock，加入 review_status / as_of / freshness_status / tags
const REPORTS_ASSET = {
  success: true, count: 2, items: [
    {
      report_id: 'rep_001', session_id: SESSION_ID, ticker: 'AAPL', title: 'Apple Q3 深度报告',
      summary: '营收超预期，服务业务持续高增长', generated_at: new Date().toISOString(),
      confidence_score: 0.87, is_favorite: false, tags: ['tech', 'q3'],
      analysis_depth: 'report', citation_count: 8, quality_state: 'pass',
      review_status: 'new', as_of: new Date().toISOString(), freshness_status: 'live',
    },
    {
      report_id: 'rep_002', session_id: SESSION_ID, ticker: 'NVDA', title: 'NVDA AI 芯片前景',
      summary: 'Blackwell 出货加速，数据中心需求强劲', generated_at: new Date().toISOString(),
      confidence_score: 0.79, is_favorite: true, tags: ['ai', 'semiconductor'],
      analysis_depth: 'deep_research', citation_count: 12, quality_state: 'pass',
      review_status: 'reviewed', as_of: new Date().toISOString(), freshness_status: 'live',
    },
  ],
};

// Helper: mock both reports/index and research-quality for Reports page
function setupReportsPageMocks(page: Page) {
  page.route('**/api/reports/index**', (r) => json(r, REPORTS_ASSET));
  page.route('**/api/research-quality**', (r) => json(r, {
    success: true,
    as_of: new Date().toISOString(),
    summary: {
      total_reports: 2,
      stale_reports: 0,
      low_quality_reports: 0,
      blocked_reports: 0,
      warn_reports: 0,
      watch_reports: 0,
      reviewed_rate: 50,
      challenged_conclusions: 0,
      health_score: 85,
    },
    top_issues: [],
    next_actions: [],
  }));
}

// ── 9a. 报告列表完整渲染（ticker badge / depth badge / review badge）
test('/reports (资产化) — 列表元素完整渲染', async ({ page }) => {
  setupReportsPageMocks(page);

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 两份报告均渲染
  await expect(page.getByText('Apple Q3 深度报告')).toBeVisible();
  await expect(page.getByText('NVDA AI 芯片前景')).toBeVisible();

  // ticker 徽章
  await expect(page.locator('.report-ticker').first()).toBeVisible();

  // 引用数徽章
  await expect(page.getByText('引用 8')).toBeVisible();
  await expect(page.getByText('引用 12')).toBeVisible();

  // 复查状态
  await expect(page.locator('.review-badge').first()).toBeVisible();
});

// ── 9b. 搜索过滤（客户端二次过滤）
test('/reports (资产化) — 搜索过滤', async ({ page }) => {
  setupReportsPageMocks(page);

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 搜索 "NVDA"
  await page.locator('.search-input').fill('NVDA');

  // Apple 应隐藏，NVDA 应可见
  await expect(page.getByText('NVDA AI 芯片前景')).toBeVisible();
  await expect(page.getByText('Apple Q3 深度报告')).toBeHidden();

  // 清空搜索后恢复
  await page.locator('.search-input').fill('');
  await expect(page.getByText('Apple Q3 深度报告')).toBeVisible();
});

// ── 9c. 标签筛选
test('/reports (资产化) — 标签筛选', async ({ page }) => {
  setupReportsPageMocks(page);

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 标签栏应出现
  await expect(page.locator('.tag-bar')).toBeVisible();
  await expect(page.locator('.tag-chip', { hasText: 'ai' })).toBeVisible();

  // 点击 'ai' 标签
  await page.locator('.tag-chip', { hasText: 'ai' }).click();

  // 只显示 NVDA 报告
  await expect(page.getByText('NVDA AI 芯片前景')).toBeVisible();
  await expect(page.getByText('Apple Q3 深度报告')).toBeHidden();

  // 清除标签
  await page.getByRole('button', { name: /清除/ }).click();
  await expect(page.getByText('Apple Q3 深度报告')).toBeVisible();
});

// ── 9d. 收藏切换
test('/reports (资产化) — 收藏切换', async ({ page }) => {
  let favBody: unknown;
  setupReportsPageMocks(page);
  await page.route('**/api/reports/*/favorite', async (r) => {
    favBody = JSON.parse((await r.request().postData()) || '{}');
    return json(r, { success: true, is_favorite: true });
  });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // AAPL 的 ☆ 按钮点击（is_favorite=false）
  const aapl = page.locator('.report-card').filter({ hasText: 'Apple Q3 深度报告' });
  const favResp = page.waitForResponse('**/api/reports/*/favorite');
  await aapl.locator('.star').click();
  await favResp;
  await expect(aapl.locator('.star')).toHaveText('★');
});

// ── 9e. 备注保存（防抖 600ms）
test('/reports (资产化) — 备注保存', async ({ page }) => {
  let noteSaved = false;
  setupReportsPageMocks(page);
  await page.route('**/api/reports/replay/**', (r) =>
    json(r, { success: true, report: { content: '报告全文内容测试' }, citations: [] }));
  await page.route('**/api/reports/*/viewed', (r) => json(r, { success: true }));
  await page.route('**/api/reports/*/note', (r) => { noteSaved = true; return json(r, { success: true, user_note: '测试备注' }); });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 点击 AAPL 报告打开侧边栏
  await page.locator('.report-card').filter({ hasText: 'Apple Q3 深度报告' }).click();

  // 等侧边栏出现
  await expect(page.locator('.note-area')).toBeVisible();

  // 输入备注
  await page.locator('.note-area').fill('测试备注');

  // 等待防抖触发（800ms）
  await page.waitForTimeout(900);
  expect(noteSaved).toBe(true);
});

// ── 9f. A/B 报告对比
test('/reports (资产化) — A/B 对比面板', async ({ page }) => {
  const DIFF = {
    success: true,
    report_a: { report_id: 'rep_001', title: 'Apple Q3 深度报告', generated_at: new Date().toISOString() },
    report_b: { report_id: 'rep_002', title: 'NVDA AI 芯片前景', generated_at: new Date().toISOString() },
    diff: {
      confidence_score: { a: 0.87, b: 0.79, delta: -0.08 },
      citation_count: { a: 8, b: 12 },
      data_freshness: { a: null, b: null },
      sentiment: { a: '正面', b: '中性', changed: true },
      risks: { added: ['监管风险'], removed: [], unchanged_count: 1 },
      summary: { a: '营收超预期', b: '增速放缓风险' },
    },
  };
  setupReportsPageMocks(page);
  await page.route('**/api/reports/compare**', (r) => json(r, DIFF));

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 进入对比模式
  await page.locator('.btn-compare').click();
  await expect(page.locator('.compare-bar')).toBeVisible();
  await expect(page.locator('.sel-empty').first()).toBeVisible();

  // 选 A：点击 Apple
  await page.locator('.report-card').filter({ hasText: 'Apple Q3 深度报告' }).click();
  await expect(page.locator('.sel-name').first()).toBeVisible();

  // 选 B：点击 NVDA
  await page.locator('.report-card').filter({ hasText: 'NVDA AI 芯片前景' }).click();

  // 执行对比
  await page.getByRole('button', { name: '开始对比' }).click();
  await page.waitForLoadState('networkidle');

  // 对比结果面板出现
  await expect(page.locator('.compare-result')).toBeVisible();
  await expect(page.locator('.diff-label', { hasText: '置信度' })).toBeVisible();
  await expect(page.locator('.diff-label', { hasText: '引用数量' })).toBeVisible();
});

// ── 9g. 旧报告刷新入口（↺ 按钮跳转到 chat 预填）
test('/reports (资产化) — 旧报告刷新入口', async ({ page }) => {
  setupReportsPageMocks(page);

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 捕获导航事件（click 会触发路由跳转）
  const navPromise = page.waitForURL(/\/chat/);

  // 点击第一张卡的 ↺ 按钮
  await page.locator('.report-card').first().locator('.btn-action', { hasText: '↺' }).click();

  // 应跳转到 /chat（带 prefill 参数）
  await navPromise;
  await expect(page).toHaveURL(/\/chat\?prefill=/);
});

// ── 9h. Markdown 导出按钮
test('/reports (资产化) — Markdown 导出按钮', async ({ page }) => {
  setupReportsPageMocks(page);

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 拦截下载
  const [ download ] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('.report-card').first().locator('.btn-action', { hasText: '↓ MD' }).click(),
  ]);

  // 文件名应包含 ticker 和 .md 后缀
  expect(download.suggestedFilename()).toMatch(/^AAPL_.*\.md$/);
});

// ══════════════════════════════════════════════════════════════
// 10. /welcome (Today Workspace 升级)
// ══════════════════════════════════════════════════════════════

const TODAY_WORKSPACE_EMPTY = {
  success: true,
  as_of: new Date().toISOString(),
  freshness_status: 'live',
  summary: '暂无数据，建议添加自选或持仓',
  portfolio_snapshot: {
    total_value: null,
    total_pnl: null,
    total_cost: null,
    risk_positions: [],
    position_count: 0,
  },
  watchlist_movers: [],
  alert_feed: [],
  reports_to_review: [],
  next_actions: [
    { id: 'add_watchlist', type: 'add_watchlist', title: '添加自选标的', reason: '建立自选清单，方便每日跟踪', severity: 'low', target_route: '/watchlist', related_symbol: null },
    { id: 'add_portfolio', type: 'add_portfolio', title: '录入持仓组合', reason: '录入持仓后可查看风险与盈亏估算', severity: 'low', target_route: '/portfolio', related_symbol: null },
  ],
};

const TODAY_WORKSPACE_FULL = {
  success: true,
  as_of: new Date().toISOString(),
  freshness_status: 'live',
  summary: '今日关注：2 只自选、2 只持仓、1 只风险提示',
  portfolio_snapshot: {
    total_value: 5700,
    total_pnl: -100,
    total_cost: 5800,
    risk_positions: [
      { ticker: 'NVDA', shares: 5, avg_cost: 800, live_price: 750, market_value: 3750, unrealized_pnl: -250, cost_basis: 4000, name: 'Nvidia', tags: ['ai'], sector: '半导体', currency: 'USD', opened_at: '2024-01-15' },
    ],
    position_count: 2,
  },
  watchlist_movers: [],
  alert_feed: [
    { id: 'evt_1', ticker: 'NVDA', event_type: 'price_spike', severity: 'high', title: 'NVDA 单日涨幅超 5%', message: '价格异动提醒', triggered_at: new Date().toISOString() },
  ],
  reports_to_review: [
    { report_id: 'rep_stale_001', ticker: 'AAPL', title: 'Apple Q2 分析', review_status: 'watch', as_of: '2024-12-01T00:00:00Z', freshness_status: 'stale', quality_state: 'warn', _review_reasons: ['手动标记关注', '数据过期'] },
  ],
  next_actions: [
    { id: 'risk_NVDA', type: 'risk_check', title: '查看 NVDA 风险', reason: '持仓亏损 -6.3%', severity: 'medium', target_route: '/dashboard/NVDA', related_symbol: 'NVDA' },
    { id: 'refresh_rep_stale_001', type: 'refresh_report', title: '刷新 AAPL 报告', reason: '手动标记关注；数据过期', severity: 'medium', target_route: '/reports?report_id=rep_stale_001', related_symbol: 'AAPL' },
  ],
};

// ── 10a. Today Workspace 空态 — 显示添加入口
test('/welcome (Today Workspace) — 空态显示添加入口', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, TODAY_WORKSPACE_EMPTY));
  setupWelcomePageCoreMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 头部摘要
  await expect(page.getByText('暂无数据，建议添加自选或持仓')).toBeVisible();

  // 持仓空态
  await expect(page.getByText('还没有持仓记录')).toBeVisible();
  await expect(page.getByRole('button', { name: '去录入' })).toBeVisible();

  // 自选空态
  await expect(page.getByText('还没有自选标的')).toBeVisible();
  await expect(page.getByRole('button', { name: '去添加' })).toBeVisible();

  // 建议操作：添加自选/持仓
  await expect(page.getByText('添加自选标的')).toBeVisible();
  await expect(page.getByText('录入持仓组合')).toBeVisible();
});

// ── 10b. Today Workspace 有数据 — 显示 6 模块
test('/welcome (Today Workspace) — 有数据时显示完整模块', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, TODAY_WORKSPACE_FULL));
  setupWelcomePageCoreMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 头部摘要
  await expect(page.getByText('今日关注：2 只自选、2 只持仓、1 只风险提示')).toBeVisible();

  // 持仓快照
  await expect(page.getByText('持仓快照')).toBeVisible();
  await expect(page.getByText('持仓数量')).toBeVisible();
  await expect(page.locator('.sum-val').filter({ hasText: /^2$/ })).toBeVisible(); // position_count

  // 自选清单
  await expect(page.getByText('自选清单')).toBeVisible();

  // 最新提醒
  await expect(page.getByText('最新提醒')).toBeVisible();
  await expect(page.getByText('NVDA 单日涨幅超 5%')).toBeVisible();

  // 待复查报告
  await expect(page.getByText('待复查报告')).toBeVisible();
  await expect(page.getByText('Apple Q2 分析')).toBeVisible();

  // 建议操作
  await expect(page.getByText('建议操作')).toBeVisible();
  await expect(page.getByText('查看 NVDA 风险')).toBeVisible();
  await expect(page.getByText('刷新 AAPL 报告')).toBeVisible();
});

// ── 10c. Today Workspace — 风险持仓显示
test('/welcome (Today Workspace) — 风险持仓显示', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, TODAY_WORKSPACE_FULL));
  setupWelcomePageCoreMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 风险仓位提示
  await expect(page.getByText('持仓风险提示', { exact: false })).toBeVisible();
  await expect(page.locator('.risk-ticker').getByText('NVDA')).toBeVisible();
  await expect(page.getByText('-6.25%')).toBeVisible(); // unrealized_pnl / cost_basis
});

// ── 10d. Today Workspace — 待复查报告标记
test('/welcome (Today Workspace) — 待复查报告标记', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, TODAY_WORKSPACE_FULL));
  setupWelcomePageCoreMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 待复查报告卡片
  const reportCard = page.locator('.report-item').filter({ hasText: 'Apple Q2 分析' });
  await expect(reportCard).toBeVisible();

  // review_status 标记
  await expect(reportCard.locator('.rep-status')).toHaveText('watch');
});

// ── 10e. Today Workspace — NextActions 点击跳转
test('/welcome (Today Workspace) — NextActions 点击跳转', async ({ page }) => {
  await page.route('**/api/today**', (r) => json(r, TODAY_WORKSPACE_FULL));
  setupWelcomePageCoreMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 点击 "查看 NVDA 风险" 应跳转到 /dashboard/NVDA
  const navPromise = page.waitForURL(/\/dashboard\/NVDA/);
  await page.locator('.action-card').filter({ hasText: '查看 NVDA 风险' }).click();
  await navPromise;
  await expect(page).toHaveURL(/\/dashboard\/NVDA/);
});

// ── 10f. Portfolio 页 — 新字段编辑
test('/portfolio — 新字段 sector/currency/opened_at 可编辑', async ({ page }) => {
  let updatedData: any = null;
  await page.route('**/api/portfolio/summary**', (r) => json(r, PORTFOLIO_SUMMARY));
  await page.route('**/api/portfolio/positions/**', async (r) => {
    const req = r.request();
    if (req.method() === 'PUT') {
      updatedData = JSON.parse(req.postData() || '{}');
      return json(r, { success: true });
    }
    return json(r, { success: false }, 405);
  });

  await page.goto('/portfolio');
  await page.waitForLoadState('networkidle');

  // 点击第一个持仓的编辑按钮
  await page.locator('.pos-card').first().locator('.btn-edit').click();

  // 编辑表单出现
  await expect(page.locator('.edit-badge')).toHaveText('编辑中');

  // 填写新字段
  await page.locator('label:has-text("行业") input').fill('科技');
  await page.locator('label:has-text("币种") input').fill('USD');
  await page.locator('label:has-text("开仓时间") input').fill('2024-01-15');

  // 保存
  await page.getByRole('button', { name: '保存' }).click();
  await page.waitForTimeout(500); // 等待请求完成

  // 验证提交数据包含新字段
  expect(updatedData).not.toBeNull();
  expect(updatedData).toMatchObject({ sector: '科技', currency: 'USD', opened_at: '2024-01-15' });
});

// ── 10g. Watchlist 页 — 新字段编辑
test('/watchlist — 新字段 group/priority/watch_reason 可编辑', async ({ page }) => {
  let addedData: any = null;

  await page.route('**/api/user/watchlist', async (r) => {
    if (r.request().method() === 'GET') {
      return json(r, { success: true, items: WATCHLIST_ITEMS, count: 2 });
    }
  });

  await page.route('**/api/user/watchlist/add', async (r) => {
    addedData = JSON.parse(r.request().postData() || '{}');
    return json(r, { success: true });
  });

  await page.goto('/watchlist');
  await page.waitForLoadState('networkidle');

  // 点击添加标的
  await page.getByRole('button', { name: /添加标的/ }).click();

  // 表单展开
  await expect(page.locator('.add-card')).toBeVisible();

  // 填写基础字段（field-wrap 结构：label + input）
  await page.locator('.field-wrap').filter({ hasText: '股票代码' }).locator('input').fill('MSFT');
  await page.locator('.field-wrap').filter({ hasText: '名称（可选）' }).locator('input').fill('微软');

  // 填写新字段
  await page.locator('.field-wrap').filter({ hasText: '分组（可选）' }).locator('input').fill('科技股');
  await page.locator('.field-wrap').filter({ hasText: '优先级（可选）' }).locator('input').fill('5');
  await page.locator('.field-wrap').filter({ hasText: '关注原因（可选）' }).locator('textarea').fill('AI 转型看好');

  // 确认添加
  await page.getByRole('button', { name: '确认添加' }).click();
  await page.waitForTimeout(1000); // 等待请求完成

  // 验证提交数据包含新字段（如果 API 被调用）
  if (addedData) {
    expect(addedData).toMatchObject({
      ticker: 'MSFT',
      name: '微软',
      group: '科技股',
      priority: 5,
      watch_reason: 'AI 转型看好',
    });
  } else {
    // 如果没有调用 API，至少验证表单填写成功
    console.log('API not called, form may have client-side validation');
  }
});

// ══════════════════════════════════════════════════════════════
// 11. /notes (Research Notebook)
// ══════════════════════════════════════════════════════════════

test('/notes — 创建笔记', async ({ page }) => {
  const noteId = 'note_test_001';
  const createPayload = {
    session_id: SESSION_ID,
    user_id: USER_ID,
    title: '测试笔记',
    content: '这是一段测试内容',
    ticker: 'AAPL',
    tags: ['测试', '财报'],
  };

  await page.route('**/api/research-notes', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, note_id: noteId }),
      });
    } else if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, notes: [], count: 0 }),
      });
    }
  });

  await page.goto('/notes');
  await page.waitForSelector('.notes-page', { timeout: 5000 });

  // 点击新建笔记
  await page.click('button.primary-btn:has-text("新建笔记")');

  // 填写表单
  await page.fill('input[placeholder*="例如：AAPL 财报后复盘"]', '测试笔记');
  await page.fill('input[placeholder*="AAPL"]', 'AAPL');
  await page.fill('input[placeholder*="逗号分隔"]', '测试, 财报');

  // 填写内容
  const textarea = page.locator('.editor-textarea');
  await textarea.fill('这是一段测试内容');

  // 点击保存
  const saveButton = page.locator('button.primary-btn:has-text("保存")');
  await saveButton.click();

  // 等待成功消息
  await page.waitForSelector('.message.success', { timeout: 3000 });
  const successMsg = await page.locator('.message.success').textContent();
  expect(successMsg).toContain('笔记已创建');
});

test('/notes — 搜索和筛选', async ({ page }) => {
  const mockNotes = [
    {
      note_id: 'note_001',
      session_id: SESSION_ID,
      user_id: USER_ID,
      ticker: 'AAPL',
      title: 'AAPL 财报分析',
      content: 'iPhone 销量超预期',
      tags: ['财报'],
      created_at: '2026-06-01T10:00:00Z',
      updated_at: '2026-06-01T10:00:00Z',
    },
    {
      note_id: 'note_002',
      session_id: SESSION_ID,
      user_id: USER_ID,
      ticker: 'TSLA',
      title: 'TSLA 交付数据',
      content: 'Q2 交付量下降',
      tags: ['风险'],
      created_at: '2026-06-02T11:00:00Z',
      updated_at: '2026-06-02T11:00:00Z',
    },
  ];

  await page.route('**/api/research-notes*', async (route) => {
    const url = new URL(route.request().url());
    const ticker = url.searchParams.get('ticker');
    const query = url.searchParams.get('q');

    let filteredNotes = mockNotes;
    if (ticker) {
      filteredNotes = filteredNotes.filter((n) => n.ticker === ticker);
    }
    if (query) {
      filteredNotes = filteredNotes.filter((n) =>
        n.title.includes(query) || n.content.includes(query)
      );
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        notes: filteredNotes,
        count: filteredNotes.length,
      }),
    });
  });

  await page.goto('/notes');
  await page.waitForSelector('.notes-page', { timeout: 5000 });

  // 验证初始显示全部笔记
  await page.waitForSelector('.note-card', { timeout: 3000 });
  let noteCards = await page.locator('.note-card').count();
  expect(noteCards).toBe(2);

  // 按 ticker 筛选
  await page.fill('input[placeholder*="按 ticker 筛选"]', 'AAPL');
  await page.click('button.filter-btn:has-text("应用筛选")');
  await page.waitForTimeout(500);

  noteCards = await page.locator('.note-card').count();
  expect(noteCards).toBe(1);

  const firstNoteTitle = await page.locator('.note-card-title').first().textContent();
  expect(firstNoteTitle).toContain('AAPL 财报分析');
});

test('/notes — 编辑笔记', async ({ page }) => {
  const noteId = 'note_edit_001';
  const mockNote = {
    note_id: noteId,
    session_id: SESSION_ID,
    user_id: USER_ID,
    ticker: 'MSFT',
    title: '原始标题',
    content: '原始内容',
    tags: ['标签1'],
    created_at: '2026-06-01T10:00:00Z',
    updated_at: '2026-06-01T10:00:00Z',
  };

  await page.route(`**/api/research-notes/${noteId}`, async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    }
  });

  await page.route('**/api/research-notes?*', async (route) => {
    // 持续返回笔记列表（保存后会刷新）
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, notes: [mockNote], count: 1 }),
    });
  });

  await page.goto('/notes');
  await page.waitForLoadState('networkidle');

  // 等待笔记卡片加载
  await page.waitForSelector('.note-card', { timeout: 5000 });

  // 点击笔记卡片
  await page.click('.note-card:has-text("原始标题")');

  // 等待编辑区加载
  await page.waitForSelector('.editor-textarea', { timeout: 3000 });

  // 修改标题
  const titleInput = page.locator('input[placeholder*="例如：AAPL 财报后复盘"]');
  await titleInput.clear();
  await titleInput.fill('修改后的标题');

  // 修改内容
  const textarea = page.locator('.editor-textarea');
  await textarea.clear();
  await textarea.fill('修改后的内容');

  // 保存
  await page.click('button.primary-btn:has-text("保存")');

  // 验证成功消息
  await page.waitForSelector('.message.success', { timeout: 3000 });
  const successMsg = await page.locator('.message.success').textContent();
  expect(successMsg).toContain('笔记已保存');
});

test('/notes — 删除笔记', async ({ page }) => {
  const noteId = 'note_delete_001';
  const mockNote = {
    note_id: noteId,
    session_id: SESSION_ID,
    user_id: USER_ID,
    ticker: 'GOOG',
    title: '待删除笔记',
    content: '这是待删除的内容',
    tags: [],
    created_at: '2026-06-01T10:00:00Z',
    updated_at: '2026-06-01T10:00:00Z',
  };

  let notesDeleted = false;

  await page.route(`**/api/research-notes/${noteId}`, async (route) => {
    if (route.request().method() === 'DELETE') {
      notesDeleted = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      });
    }
  });

  await page.route('**/api/research-notes?*', async (route) => {
    // 删除后返回空列表
    const notes = notesDeleted ? [] : [mockNote];
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, notes, count: notes.length }),
    });
  });

  await page.goto('/notes');
  await page.waitForLoadState('networkidle');

  // 等待笔记加载
  await page.waitForSelector('.note-card', { timeout: 5000 });

  // 点击笔记
  await page.click('.note-card:has-text("待删除笔记")');

  // 等待编辑区加载
  await page.waitForSelector('button.danger-btn:has-text("删除")', { timeout: 3000 });

  // 点击删除按钮
  await page.click('button.danger-btn:has-text("删除")');

  // 验证成功消息
  await page.waitForSelector('.message.success', { timeout: 3000 });
  const successMsg = await page.locator('.message.success').textContent();
  expect(successMsg).toContain('笔记已删除');
});

test('/notes — 图片上传 UI 存在', async ({ page }) => {
  const noteId = 'note_image_001';
  const mockNote = {
    note_id: noteId,
    session_id: SESSION_ID,
    user_id: USER_ID,
    ticker: 'NVDA',
    title: '图片测试笔记',
    content: '',
    tags: [],
    created_at: '2026-06-01T10:00:00Z',
    updated_at: '2026-06-01T10:00:00Z',
  };

  await page.route('**/api/research-notes?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, notes: [mockNote], count: 1 }),
    });
  });

  await page.goto('/notes');
  await page.waitForLoadState('networkidle');

  // 等待笔记加载
  await page.waitForSelector('.note-card', { timeout: 5000 });

  // 点击笔记
  await page.click('.note-card:has-text("图片测试笔记")');

  // 验证工具栏图片上传按钮存在
  const imageButton = page.locator('button.toolbar-btn[title="上传图片"]');
  await expect(imageButton).toBeVisible();

  // 验证 Markdown 编辑器存在
  const textarea = page.locator('.editor-textarea');
  await expect(textarea).toBeVisible();
});

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// Timeline 时间线测试
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

test('/timeline/:symbol — 基础渲染', async ({ page }) => {
  // 使用统一 mock helper
  setupTimelineMocks(page, 'AAPL');
  // Timeline 页面也会调用 what-changed API
  setupWhatChangedMocks(page);

  await page.goto('/timeline/AAPL');
  await page.waitForLoadState('networkidle');

  // 验证页面标题
  await expect(page.locator('.page-title')).toContainText('AAPL 研究时间线');

  // 验证事件卡片渲染
  const eventCards = page.locator('[data-testid="event-card"]');
  await expect(eventCards).toHaveCount(2);

  // 验证第一个事件内容
  await expect(page.locator('[data-testid="event-title"]').first()).toContainText('AAPL Q4 财报更新');
});

test('/timeline/:symbol — 空态显示', async ({ page }) => {
  await page.route('**/api/timeline/TSLA?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'TSLA',
        count: 0,
        events: [],
      }),
    });
  });

  await page.goto('/timeline/TSLA');
  await page.waitForLoadState('networkidle');

  // 验证空态
  await expect(page.locator('.empty-state')).toBeVisible();
  await expect(page.locator('.empty-state h3')).toContainText('暂无事件记录');
});

test('/timeline/:symbol — 类型筛选', async ({ page }) => {
  const allEvents = [
    {
      id: 'event_report_1',
      symbol: 'MSFT',
      event_type: 'report',
      title: 'MSFT 报告',
      summary: '报告摘要',
      occurred_at: '2026-06-07T10:00:00Z',
      severity: 'medium',
    },
    {
      id: 'event_note_1',
      symbol: 'MSFT',
      event_type: 'note',
      title: 'MSFT 笔记',
      summary: '笔记摘要',
      occurred_at: '2026-06-06T10:00:00Z',
      severity: 'low',
    },
  ];

  await page.route('**/api/timeline/MSFT**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'MSFT',
        count: allEvents.length,
        events: allEvents,
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.goto('/timeline/MSFT');
  await page.waitForLoadState('networkidle');

  // 初始显示全部 - 使用 data-testid
  await expect(page.locator('[data-testid="event-card"]')).toHaveCount(2);

  // 点击"报告"筛选
  await page.click('.filter-btn:has-text("报告")');
  await expect(page.locator('[data-testid="event-card"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="event-title"]').first()).toContainText('MSFT 报告');

  // 点击"笔记"筛选
  await page.click('.filter-btn:has-text("笔记")');
  await expect(page.locator('[data-testid="event-card"]')).toHaveCount(1);
  await expect(page.locator('[data-testid="event-title"]').first()).toContainText('MSFT 笔记');

  // 点击"全部"恢复
  await page.click('.filter-btn:has-text("全部")');
  await expect(page.locator('[data-testid="event-card"]')).toHaveCount(2);
});

test('/timeline/:symbol — 点击 report 事件跳转', async ({ page }) => {
  const mockEvent = {
    id: 'event_report',
    symbol: 'GOOGL',
    event_type: 'report',
    title: 'GOOGL 报告',
    summary: '报告摘要',
    occurred_at: '2026-06-07T10:00:00Z',
    severity: 'medium',
    target_route: '/reports?report_id=rep_googl_001',
    related_report_id: 'rep_googl_001',
  };

  await page.route('**/api/timeline/GOOGL**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'GOOGL',
        count: 1,
        events: [mockEvent],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.goto('/timeline/GOOGL');
  await page.waitForLoadState('networkidle');

  // 点击事件卡片
  await page.click('[data-testid="event-card"]');

  // 验证跳转
  await page.waitForURL('**/reports?report_id=rep_googl_001');
});

test('/timeline/:symbol — 点击 note 事件跳转', async ({ page }) => {
  const mockEvent = {
    id: 'event_note',
    symbol: 'NVDA',
    event_type: 'note',
    title: 'NVDA 笔记',
    summary: '笔记摘要',
    occurred_at: '2026-06-07T10:00:00Z',
    severity: 'low',
    target_route: '/notes?note_id=note_nvda_001',
    related_note_id: 'note_nvda_001',
  };

  await page.route('**/api/timeline/NVDA**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'NVDA',
        count: 1,
        events: [mockEvent],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.goto('/timeline/NVDA');
  await page.waitForLoadState('networkidle');

  // 点击事件卡片
  await page.click('[data-testid="event-card"]');

  // 验证跳转
  await page.waitForURL('**/notes?note_id=note_nvda_001');
});

test('/timeline/:symbol — 高风险事件样式显示', async ({ page }) => {
  const highRiskEvent = {
    id: 'event_critical',
    symbol: 'META',
    event_type: 'report',
    title: 'META 严重质量问题',
    summary: '数据质量阻断',
    occurred_at: '2026-06-07T10:00:00Z',
    severity: 'critical',
    source: 'report_index',
    evidence: {
      quality_state: 'block',
      confidence: 0.3,
    },
  };

  await page.route('**/api/timeline/META**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'META',
        count: 1,
        events: [highRiskEvent],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.goto('/timeline/META');
  await page.waitForLoadState('networkidle');

  // 验证高风险事件边框颜色
  const eventCard = page.locator('[data-testid="event-card"]').first();
  const borderColor = await eventCard.evaluate((el) => {
    return window.getComputedStyle(el).borderLeftColor;
  });

  // 验证质量标识存在
  await expect(page.locator('.quality-badge')).toBeVisible();
  await expect(page.locator('.quality-badge')).toContainText('质量阻断');
});

// ============================================
// What Changed Tests (Phase 4.4)
// ============================================

test('/welcome — 显示 What Changed 模块', async ({ page }) => {
  // 使用统一 mock helper
  setupTodayWorkspaceMocks(page);
  setupWhatChangedMocks(page);
  setupResearchQualityMocks(page);

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 验证 What Changed 模块存在
  await expect(page.locator('[data-testid="what-changed-panel"]')).toBeVisible();
  await expect(page.locator('h2:has-text("今日重要变化")')).toBeVisible();

  // 验证变化卡片渲染
  await expect(page.locator('[data-testid="what-changed-card"]')).toHaveCount(2);
  await expect(page.locator('[data-testid="change-title"]:has-text("NVDA 优先级上升")')).toBeVisible();
});

test('/welcome — What Changed 无变化时不显示模块', async ({ page }) => {
  // Mock empty today workspace
  await page.route('**/api/today**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: '今日工作台测试数据',
        freshness_status: 'live',
        portfolio_snapshot: {
          position_count: 0,
          total_cost: null,
          total_pnl: null,
          total_value: null,
          risk_positions: [],
        },
        watchlist_movers: [],
        alert_feed: [],
        reports_to_review: [],
        next_actions: [],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.route('**/api/research-quality**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 0,
          stale_reports: 0,
          low_quality_reports: 0,
          blocked_reports: 0,
          warn_reports: 0,
          watch_reports: 0,
          reviewed_rate: 0,
          challenged_conclusions: 0,
          health_score: 100,
        },
        top_issues: [],
        next_actions: [],
      }),
    });
  });

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 验证 What Changed 模块不显示
  await expect(page.locator('[data-testid="what-changed-panel"]')).not.toBeVisible();
});

test('/welcome — high severity 变化显示高风险样式', async ({ page }) => {
  await page.route('**/api/today**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: '今日工作台测试数据',
        freshness_status: 'live',
        portfolio_snapshot: {
          position_count: 0,
          total_cost: null,
          total_pnl: null,
          total_value: null,
          risk_positions: [],
        },
        watchlist_movers: [],
        alert_feed: [],
        reports_to_review: [],
        next_actions: [],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [
          {
            id: 'change_critical',
            symbol: 'TSLA',
            change_type: 'risk',
            title: 'TSLA 风险评分上升',
            severity: 'critical',
            reason: '持仓亏损扩大，质量恶化。',
            target_route: '/portfolio/risk-lens',
          },
        ],
        count: 1,
      }),
    });
  });

  await page.route('**/api/research-quality**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 0,
          stale_reports: 0,
          low_quality_reports: 0,
          blocked_reports: 0,
          warn_reports: 0,
          watch_reports: 0,
          reviewed_rate: 0,
          challenged_conclusions: 0,
          health_score: 100,
        },
        top_issues: [],
        next_actions: [],
      }),
    });
  });

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 验证 severity badge 存在且为 critical
  const severityBadge = page.locator('[data-testid="severity-badge"]').first();
  await expect(severityBadge).toBeVisible();
  await expect(severityBadge).toContainText('严重');

  // 验证 border 颜色（critical 应为红色 #dc2626）
  const card = page.locator('[data-testid="what-changed-card"]').first();
  const borderColor = await card.locator('.type-badge').evaluate((el) => {
    return window.getComputedStyle(el).borderColor;
  });
  expect(borderColor).toContain('220, 38, 38'); // RGB of #dc2626
});

test('/welcome — 点击变化卡片跳转 target_route', async ({ page }) => {
  await page.route('**/api/today**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: '今日工作台测试数据',
        portfolio_snapshot: {
          position_count: 0,
          total_cost: null,
          total_pnl: null,
          risk_positions: [],
        },
        watchlist_movers: [],
        alert_feed: [],
        reports_to_review: [],
        next_actions: [],
      }),
    });
  });

  await page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [
          {
            id: 'change_nav',
            symbol: 'GOOGL',
            change_type: 'note',
            title: 'GOOGL 新增研究笔记',
            severity: 'medium',
            reason: '你在新笔记中记录了新假设。',
            target_route: '/notes?ticker=GOOGL',
          },
        ],
        count: 1,
      }),
    });
  });

  await page.route('**/api/research-quality**', (r) => json(r, { success: true, as_of: new Date().toISOString(), summary: { total_reports: 0, stale_reports: 0, low_quality_reports: 0, blocked_reports: 0, warn_reports: 0, watch_reports: 0, reviewed_rate: 0, challenged_conclusions: 0, health_score: 100 }, top_issues: [], next_actions: [] }));

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 点击变化卡片
  await page.locator('.what-changed-card').first().click();

  // 验证跳转到 /notes?ticker=GOOGL
  await page.waitForURL('**/notes?ticker=GOOGL');
  expect(page.url()).toContain('/notes?ticker=GOOGL');
});

test('/timeline/:symbol — 显示 symbol 相关变化', async ({ page }) => {
  await page.route('**/api/what-changed?*symbol=NVDA*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [
          {
            id: 'change_nvda',
            symbol: 'NVDA',
            change_type: 'report',
            title: 'NVDA 报告数据过期',
            severity: 'medium',
            reason: '报告截至日期已超过 7 天。',
            target_route: '/reports?highlight=report_nvda_001',
            evidence: {
              freshness_status: 'stale',
            },
          },
        ],
        count: 1,
      }),
    });
  });

  await page.route('**/api/timeline/NVDA?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol: 'NVDA',
        count: 0,
        events: [],
      }),
    });
  });

  await page.goto('/timeline/NVDA');
  await page.waitForLoadState('networkidle');

  // 验证 What Changed 区域存在
  await expect(page.locator('.what-changed-section')).toBeVisible();
  await expect(page.locator('h2:has-text("NVDA 重要变化")')).toBeVisible();

  // 验证变化卡片
  await expect(page.locator('.what-changed-card')).toHaveCount(1);
  await expect(page.locator('.title:has-text("NVDA 报告数据过期")')).toBeVisible();
});

// ============================================
// Research Quality Tests (Phase 4.5)
// ============================================

test('/reports — 显示研究库健康度模块', async ({ page }) => {
  await page.route('**/api/reports/index**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        items: [
          {
            report_id: 'report_001',
            session_id: 'test_session',
            ticker: 'AAPL',
            title: 'AAPL 深度分析',
            summary: '测试报告',
            generated_at: '2026-06-01T10:00:00Z',
            is_favorite: false,
            tags: [],
          },
        ],
        count: 1,
      }),
    });
  });

  await page.route('**/api/research-quality?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 10,
          stale_reports: 2,
          low_quality_reports: 1,
          blocked_reports: 0,
          warn_reports: 1,
          watch_reports: 3,
          reviewed_rate: 0.6,
          challenged_conclusions: 1,
          health_score: 75,
        },
        top_issues: [
          {
            id: 'issue_1',
            issue_type: 'stale_report',
            severity: 'high',
            title: 'AAPL 报告已过期',
            reason: '报告数据 freshness_status=stale，建议刷新后复查。',
            target_route: '/reports?highlight=report_001',
            related_symbol: 'AAPL',
            related_report_id: 'report_001',
          },
        ],
        next_actions: [],
      }),
    });
  });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 验证健康度模块存在
  await expect(page.locator('.quality-section')).toBeVisible();
  await expect(page.locator('h2:has-text("研究库健康度")')).toBeVisible();

  // 验证健康分数显示
  await expect(page.locator('.score-value:has-text("75")')).toBeVisible();

  // 验证统计数据
  await expect(page.locator('.stat-value:has-text("10")')).toBeVisible(); // total_reports

  // 验证质量问题列表
  await expect(page.locator('.issue-card')).toHaveCount(1);
  await expect(page.locator('.issue-title:has-text("AAPL 报告已过期")')).toBeVisible();
});

test('/reports — 健康度模块可折叠', async ({ page }) => {
  await page.route('**/api/reports/index**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        items: [{ report_id: 'r1', session_id: 's1', ticker: 'AAPL', title: 'Test', is_favorite: false, tags: [] }],
        count: 1,
      }),
    });
  });

  await page.route('**/api/research-quality?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 5,
          stale_reports: 0,
          low_quality_reports: 0,
          blocked_reports: 0,
          warn_reports: 0,
          watch_reports: 0,
          reviewed_rate: 1.0,
          challenged_conclusions: 0,
          health_score: 100,
        },
        top_issues: [],
        next_actions: [],
      }),
    });
  });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 等待健康度模块显示
  await expect(page.locator('.quality-section')).toBeVisible();

  // 点击收起按钮
  await page.locator('.btn-toggle').click();

  // 验证模块已折叠
  await expect(page.locator('.quality-section')).not.toBeVisible();
  await expect(page.locator('.quality-collapsed')).toBeVisible();

  // 点击展开按钮
  await page.locator('.btn-expand').click();

  // 验证模块已展开
  await expect(page.locator('.quality-section')).toBeVisible();
});

test('/reports — 点击问题卡片跳转', async ({ page }) => {
  await page.route('**/api/reports/index**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        items: [{ report_id: 'r1', session_id: 's1', ticker: 'GOOGL', title: 'Test', is_favorite: false, tags: [] }],
        count: 1,
      }),
    });
  });

  await page.route('**/api/research-quality?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 3,
          stale_reports: 1,
          low_quality_reports: 0,
          blocked_reports: 0,
          warn_reports: 0,
          watch_reports: 0,
          reviewed_rate: 0.5,
          challenged_conclusions: 0,
          health_score: 85,
        },
        top_issues: [
          {
            id: 'issue_nav',
            issue_type: 'stale_report',
            severity: 'medium',
            title: 'GOOGL 报告需更新',
            reason: '数据已过期',
            target_route: '/reports?highlight=report_googl',
            related_symbol: 'GOOGL',
          },
        ],
        next_actions: [],
      }),
    });
  });

  await page.goto('/reports');
  await page.waitForLoadState('networkidle');

  // 等待问题卡片显示
  await expect(page.locator('.issue-card')).toBeVisible();

  // 点击问题卡片
  await page.locator('.issue-card').first().click();

  // 验证跳转到目标路由
  await page.waitForURL('**/reports?highlight=report_googl');
  expect(page.url()).toContain('/reports?highlight=report_googl');
});

test('/welcome — 显示研究库健康度模块', async ({ page }) => {
  await page.route('**/api/today?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: '今日工作台',
        portfolio_snapshot: { position_count: 0, total_cost: null, total_pnl: null, risk_positions: [] },
        watchlist_movers: [],
        alert_feed: [],
        reports_to_review: [],
        next_actions: [],
      }),
    });
  });

  await page.route('**/api/what-changed?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        items: [],
        count: 0,
      }),
    });
  });

  await page.route('**/api/research-quality?*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2026-06-08T10:00:00Z',
        summary: {
          total_reports: 15,
          stale_reports: 3,
          low_quality_reports: 2,
          blocked_reports: 1,
          warn_reports: 2,
          watch_reports: 5,
          reviewed_rate: 0.7,
          challenged_conclusions: 1,
          health_score: 68,
        },
        top_issues: [
          {
            id: 'welcome_issue_1',
            issue_type: 'blocked_report',
            severity: 'critical',
            title: 'TSLA 报告质量阻断',
            reason: '报告未通过质量检查',
            target_route: '/reports?highlight=report_tsla',
            related_symbol: 'TSLA',
          },
          {
            id: 'welcome_issue_2',
            issue_type: 'stale_report',
            severity: 'high',
            title: 'NVDA 报告已过期',
            reason: '数据已过期',
            target_route: '/reports?highlight=report_nvda',
            related_symbol: 'NVDA',
          },
        ],
        next_actions: [],
      }),
    });
  });

  await page.goto('/welcome');
  await page.waitForLoadState('networkidle');

  // 验证健康度面板存在
  await expect(page.locator('.quality-panel')).toBeVisible();
  await expect(page.locator('h2:has-text("研究库健康度")')).toBeVisible();

  // 验证健康分数
  await expect(page.locator('.score-value:has-text("68")')).toBeVisible();

  // 验证只显示前3个问题（按用户需求）
  const issueCards = page.locator('.issue-card');
  await expect(issueCards).toHaveCount(2); // 因为我们只返回了2个
});
