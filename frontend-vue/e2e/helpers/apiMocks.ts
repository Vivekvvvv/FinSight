import { Page } from '@playwright/test';

/**
 * Phase 6 E2E API Mock Helper
 *
 * 集中维护所有 E2E 测试的 API mock，确保：
 * 1. URL pattern 匹配真实 API 路径
 * 2. Response 结构符合 src/api/types.ts
 * 3. 避免在测试用例中重复写 page.route
 */

// ============================================================
// 1. Reports / 报告资产化
// ============================================================

export function setupReportsMocks(page: Page) {
  page.route('**/api/reports/index**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        count: 3,
        items: [
          {
            report_id: 'rep_aapl_001',
            session_id: 'test_session',
            ticker: 'AAPL',
            title: 'Apple Q3 深度报告',
            summary: 'Apple Q3 财报分析，营收超预期，iPhone 销量稳健。',
            generated_at: '2024-11-15T10:00:00Z',
            as_of: '2024-11-15',
            created_at: '2024-11-15T10:00:00Z',
            updated_at: '2024-11-15T10:00:00Z',
            tags: ['ai', 'earnings'],
            is_favorite: false,
            review_status: 'reviewed',
            freshness_status: 'live',
            quality_state: 'ok',
            citation_count: 12,
            citation_quality: 'high',
            confidence_score: 0.85,
            user_note: null,
            analysis_depth: 'report',
          },
          {
            report_id: 'rep_nvda_001',
            session_id: 'test_session',
            ticker: 'NVDA',
            title: 'NVDA AI 深度研究',
            summary: 'NVDA 在 AI 芯片领域的竞争优势分析。',
            generated_at: '2024-11-10T14:00:00Z',
            as_of: '2024-11-10',
            created_at: '2024-11-10T14:00:00Z',
            updated_at: '2024-11-10T14:00:00Z',
            tags: ['ai', 'hardware'],
            is_favorite: true,
            review_status: 'watch',
            freshness_status: 'live',
            quality_state: 'ok',
            citation_count: 8,
            citation_quality: 'medium',
            confidence_score: 0.78,
            user_note: '关注 AI 芯片竞争格局',
            analysis_depth: 'deep_research',
          },
          {
            report_id: 'rep_aapl_q2_old',
            session_id: 'test_session',
            ticker: 'AAPL',
            title: 'Apple Q2 陈旧',
            summary: 'Apple Q2 财报（已过期）。',
            generated_at: '2024-08-01T10:00:00Z',
            as_of: '2024-08-01',
            created_at: '2024-08-01T10:00:00Z',
            updated_at: '2024-08-01T10:00:00Z',
            tags: ['earnings'],
            is_favorite: false,
            review_status: 'watch',
            freshness_status: 'stale',
            quality_state: 'warn',
            citation_count: 3,
            citation_quality: 'low',
            confidence_score: 0.45,
            user_note: null,
            analysis_depth: 'report',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 2. Timeline / 时间线聚合
// ============================================================

export function setupTimelineMocks(page: Page, symbol: string) {
  page.route(`**/api/timeline/${symbol}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        symbol,
        count: 2,
        events: [
          {
            id: 'evt_001',
            symbol,
            event_type: 'report',
            title: `${symbol} Q4 财报更新`,
            summary: '财报已发布，营收超预期。',
            occurred_at: '2024-11-10T14:30:00Z',
            severity: 'high',
            source: 'report:rep_googl_001',
            target_route: `/reports?report_id=rep_googl_001`,
            related_report_id: 'rep_googl_001',
            evidence: {
              confidence: 0.85,
              citation_count: 10,
              freshness_status: 'live',
              quality_state: 'ok',
            },
          },
          {
            id: 'evt_002',
            symbol,
            event_type: 'note',
            title: `${symbol} 笔记摘要`,
            summary: '用户研究笔记记录。',
            occurred_at: '2024-11-09T10:00:00Z',
            severity: 'medium',
            source: 'note:note_nvda_001',
            target_route: `/notes?note_id=note_nvda_001`,
            related_note_id: 'note_nvda_001',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 3. What Changed / 今日变化
// ============================================================

export function setupWhatChangedMocks(page: Page) {
  page.route('**/api/what-changed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2024-11-15T09:00:00Z',
        count: 2,
        items: [
          {
            id: 'chg_001',
            symbol: 'NVDA',
            change_type: 'report',
            title: 'NVDA 优先级上升',
            before: '中等',
            after: '高',
            delta: '+15%',
            severity: 'high',
            reason: '新财报质量改善',
            target_route: '/dashboard/NVDA',
            occurred_at: '2024-11-15T08:00:00Z',
            evidence: {
              quality_state: 'ok',
              freshness_status: 'live',
              citation_quality: 'high',
              confidence: 0.88,
              citation_count: 12,
            },
          },
          {
            id: 'chg_002',
            symbol: 'AAPL',
            change_type: 'risk',
            title: 'AAPL 风险降低',
            before: '高',
            after: '中',
            delta: '-10%',
            severity: 'medium',
            reason: '亏损幅度收窄',
            target_route: '/dashboard/AAPL',
            occurred_at: '2024-11-15T07:30:00Z',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 4. Research Quality / 研究质量
// ============================================================

export function setupResearchQualityMocks(page: Page) {
  page.route('**/api/research-quality**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2024-11-15T10:00:00Z',
        summary: {
          total_reports: 10,
          stale_reports: 2,
          low_quality_reports: 1,
          blocked_reports: 0,
          warn_reports: 1,
          watch_reports: 3,
          reviewed_rate: 70,
          challenged_conclusions: 1,
          health_score: 75,
        },
        top_issues: [
          {
            id: 'issue_001',
            issue_type: 'stale_report',
            severity: 'high',
            title: 'Apple Q2 报告已过期',
            reason: '数据截至 2024-08-01，已超过 90 天',
            target_route: '/reports?report_id=rep_aapl_q2_old',
            related_symbol: 'AAPL',
            related_report_id: 'rep_aapl_q2_old',
          },
          {
            id: 'issue_002',
            issue_type: 'low_citation',
            severity: 'medium',
            title: 'TSLA 报告引用不足',
            reason: '仅有 2 个引用，可信度待提升',
            target_route: '/reports?report_id=rep_tsla_001',
            related_symbol: 'TSLA',
            related_report_id: 'rep_tsla_001',
          },
        ],
        next_actions: [],
      }),
    });
  });
}

// ============================================================
// 5. Research Notes / 研究笔记
// ============================================================

export function setupResearchNotesMocks(page: Page) {
  page.route('**/api/research-notes**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        count: 2,
        notes: [
          {
            note_id: 'note_nvda_001',
            session_id: 'test_session',
            user_id: 'test_user',
            ticker: 'NVDA',
            title: 'NVDA AI 芯片竞争分析',
            content: '## 核心观点\n\nNVDA 在 AI 芯片领域具有显著竞争优势。',
            tags: ['ai', 'hardware'],
            created_at: '2024-11-10T14:00:00Z',
            updated_at: '2024-11-10T14:00:00Z',
          },
          {
            note_id: 'note_aapl_001',
            session_id: 'test_session',
            user_id: 'test_user',
            ticker: 'AAPL',
            title: 'Apple 供应链风险',
            content: '## 风险点\n\n1. 对单一供应商依赖\n2. 地缘政治风险',
            tags: ['supply-chain', 'risk'],
            created_at: '2024-11-08T10:00:00Z',
            updated_at: '2024-11-08T10:00:00Z',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 6. Portfolio Risk Lens / 持仓风险透镜
// ============================================================

export function setupPortfolioRiskLensMocks(page: Page) {
  page.route('**/api/portfolio/risk-lens**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2024-11-15T10:00:00Z',
        total_value: 50000,
        total_cost: 48000,
        risk_score: 65,
        concentration_risk: [
          {
            id: 'conc_001',
            type: 'single_position',
            severity: 'high',
            title: 'AAPL 占比过高',
            reason: '单一持仓占组合 45%',
            target_route: '/portfolio',
            related_symbol: 'AAPL',
            metric_value: 45,
          },
        ],
        sector_exposure: [
          { sector: '科技', value: 35000, percentage: 70 },
          { sector: '消费', value: 15000, percentage: 30 },
        ],
        currency_exposure: [
          { currency: 'USD', value: 40000, percentage: 80 },
          { currency: 'HKD', value: 10000, percentage: 20 },
        ],
        market_exposure: [
          { market: 'US', value: 40000, percentage: 80 },
          { market: 'HK', value: 10000, percentage: 20 },
        ],
        stale_research: [],
        loss_positions: [
          {
            id: 'loss_001',
            type: 'loss_position',
            severity: 'medium',
            title: 'AAPL 亏损 5%',
            reason: '当前亏损 $1000',
            target_route: '/dashboard/AAPL',
            related_symbol: 'AAPL',
            metric_value: -5,
          },
        ],
        missing_coverage: [],
        next_actions: [
          {
            id: 'action_001',
            type: 'review_risk',
            severity: 'high',
            title: '查看 AAPL 风险',
            reason: 'AAPL 占比过高且亏损',
            target_route: '/dashboard/AAPL',
            related_symbol: 'AAPL',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 7. Today Workspace / 今日工作台
// ============================================================

export function setupTodayWorkspaceMocks(page: Page) {
  page.route('**/api/today**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        as_of: '2024-11-15T09:00:00Z',
        freshness_status: 'live',
        summary: '今日关注 2 只标的，持仓 2 只。',
        portfolio_snapshot: {
          total_value: 50000,
          total_pnl: 2000,
          total_cost: 48000,
          risk_positions: [
            {
              ticker: 'AAPL',
              shares: 100,
              avg_cost: 150,
              name: 'Apple Inc.',
              live_price: 145,
              market_value: 14500,
              cost_basis: 15000,
              unrealized_pnl: -500,
              price_source: 'mock',
            },
          ],
          position_count: 2,
        },
        watchlist_movers: [],
        alert_feed: [
          {
            id: 'alert_001',
            ticker: 'NVDA',
            event_type: 'price_alert',
            severity: 'high',
            title: 'NVDA 突破 $500',
            message: 'NVDA 股价突破设定阈值 $500',
            triggered_at: '2024-11-15T08:30:00Z',
          },
        ],
        reports_to_review: [
          {
            report_id: 'rep_aapl_q2_old',
            session_id: 'test_session',
            ticker: 'AAPL',
            title: 'Apple Q2 陈旧',
            summary: 'Apple Q2 财报（已过期）。',
            generated_at: '2024-08-01T10:00:00Z',
            as_of: '2024-08-01',
            tags: ['earnings'],
            is_favorite: false,
            review_status: 'watch',
            freshness_status: 'stale',
            quality_state: 'warn',
            citation_count: 3,
            citation_quality: 'low',
            analysis_depth: 'report',
          },
        ],
        next_actions: [
          {
            id: 'action_001',
            type: 'risk_check',
            title: '查看 NVDA 风险',
            reason: 'NVDA 优先级上升，建议复查',
            severity: 'high',
            target_route: '/dashboard/NVDA',
            related_symbol: 'NVDA',
          },
        ],
      }),
    });
  });
}

// ============================================================
// 8. Alerts Feed / 告警推送
// ============================================================

export function setupAlertsFeedMocks(page: Page) {
  page.route('**/api/alerts/feed**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        alerts: [
          {
            id: 'alert_001',
            ticker: 'NVDA',
            event_type: 'price_alert',
            severity: 'high',
            title: 'NVDA 突破 $500',
            message: 'NVDA 股价突破设定阈值 $500',
            triggered_at: '2024-11-15T08:30:00Z',
          },
          {
            id: 'alert_002',
            ticker: 'AAPL',
            event_type: 'news_alert',
            severity: 'medium',
            title: 'AAPL 新产品发布',
            message: 'Apple 发布新款 iPhone',
            triggered_at: '2024-11-15T07:00:00Z',
          },
        ],
        count: 2,
      }),
    });
  });
}

// ============================================================
// 9. Portfolio Summary / 持仓摘要
// ============================================================

export function setupPortfolioSummaryMocks(page: Page) {
  page.route('**/api/portfolio/summary**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        session_id: 'test_session',
        count: 2,
        positions: [
          {
            ticker: 'AAPL',
            shares: 100,
            avg_cost: 150,
            name: 'Apple Inc.',
            tags: ['tech', 'holding'],
            note: '长期持仓',
            sector: '科技',
            currency: 'USD',
            opened_at: '2024-01-15',
            live_price: 145,
            market_value: 14500,
            cost_basis: 15000,
            unrealized_pnl: -500,
            price_source: 'mock',
          },
          {
            ticker: 'NVDA',
            shares: 50,
            avg_cost: 400,
            name: 'NVIDIA Corporation',
            tags: ['ai', 'growth'],
            note: 'AI 增长标的',
            sector: '科技',
            currency: 'USD',
            opened_at: '2024-03-01',
            live_price: 450,
            market_value: 22500,
            cost_basis: 20000,
            unrealized_pnl: 2500,
            price_source: 'mock',
          },
        ],
        total_value: 37000,
        total_cost: 35000,
        total_pnl: 2000,
      }),
    });
  });
}

// ============================================================
// 10. Watchlist / 自选列表
// ============================================================

export function setupWatchlistMocks(page: Page) {
  page.route('**/api/watchlist**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        items: [
          {
            ticker: 'GOOGL',
            name: 'Alphabet Inc.',
            tags: ['tech', 'advertising'],
            note: '关注搜索广告业务',
            group: '科技',
            priority: 5,
            watch_reason: 'AI 战略布局',
            added_at: '2024-10-01T10:00:00Z',
            updated_at: '2024-10-01T10:00:00Z',
          },
          {
            ticker: 'TSLA',
            name: 'Tesla Inc.',
            tags: ['ev', 'growth'],
            note: '关注自动驾驶进展',
            group: '消费',
            priority: 4,
            watch_reason: 'FSD Beta 进展',
            added_at: '2024-09-15T10:00:00Z',
            updated_at: '2024-09-15T10:00:00Z',
          },
        ],
        count: 2,
      }),
    });
  });
}

// ============================================================
// 组合 Mock 函数
// ============================================================

/**
 * Phase 4/5 核心功能 Mock（Timeline + What Changed + Research Quality）
 */
export function setupPhase45CoreMocks(page: Page, symbol = 'AAPL') {
  setupTimelineMocks(page, symbol);
  setupWhatChangedMocks(page);
  setupResearchQualityMocks(page);
  setupResearchNotesMocks(page);
}

/**
 * Today Workspace 全部 Mock
 */
export function setupTodayWorkspaceFullMocks(page: Page) {
  setupTodayWorkspaceMocks(page);
  setupPortfolioSummaryMocks(page);
  setupWatchlistMocks(page);
  setupAlertsFeedMocks(page);
  setupReportsMocks(page);
}

/**
 * 全局 Mock（覆盖所有功能）
 */
export function setupAllMocks(page: Page, symbol = 'AAPL') {
  setupReportsMocks(page);
  setupTimelineMocks(page, symbol);
  setupWhatChangedMocks(page);
  setupResearchQualityMocks(page);
  setupResearchNotesMocks(page);
  setupPortfolioRiskLensMocks(page);
  setupTodayWorkspaceMocks(page);
  setupAlertsFeedMocks(page);
  setupPortfolioSummaryMocks(page);
  setupWatchlistMocks(page);
}
