// FinSight Vue API 类型

/** 统一证据元数据 — 附在任何 AI 结论旁（camelCase，前端约定） */
export interface EvidenceInfo {
  source?: string | null;
  asOf?: string | null;
  freshnessStatus?: 'live' | 'delayed_15min' | 'cached' | 'stale' | 'unknown' | null;
  fallbackLevel?: number | null;   // 0=主源 1=fallback 2=cache
  confidence?: number | null;      // 0-1
  modelGenerated?: boolean | null;
  cached?: boolean | null;
  // 降级信号
  degraded?: boolean | null;       // true = 数据不足，结论保守
  staleData?: boolean | null;      // true = 数据超过 24h
  citationCount?: number | null;
  citationQuality?: 'high' | 'medium' | 'low' | null;
  qualityState?: string | null;    // 'pass' | 'block' | null
  quality?: Record<string, unknown> | null;
}

export interface MeResponse {
  success: boolean;
  user_id: string;
  email?: string | null;
  role: string;
  auth_type?: string;
}

export interface WatchlistItem {
  ticker: string;
  name?: string | null;
  tags: string[];
  note?: string | null;
  group?: string | null;
  priority?: number | null;
  watch_reason?: string | null;
  added_at?: string | null;
  updated_at?: string | null;
}

export interface PortfolioPosition {
  ticker: string;
  shares: number;
  avg_cost?: number | null;
  name?: string | null;
  tags?: string[];
  note?: string | null;
  sector?: string | null;
  currency?: string | null;
  opened_at?: string | null;
  updated_at?: string | null;
  live_price?: number | null;
  market_value?: number | null;
  cost_basis?: number | null;
  unrealized_pnl?: number | null;
  price_source?: string;
}

export interface PortfolioSummary {
  success: boolean;
  session_id: string;
  positions: PortfolioPosition[];
  count: number;
  total_value: number | null;
  total_cost: number | null;
  total_pnl: number | null;
}

export interface ReportIndexItem {
  report_id: string;
  session_id: string;
  ticker?: string | null;
  title?: string | null;
  summary?: string | null;
  generated_at?: string | null;
  confidence_score?: number | null;
  is_favorite: boolean;
  tags: string[];
  source_type?: string;
  quality_state?: string;
  publishable?: boolean;
  quality_reasons?: Array<{ code: string; message: string }>;
  user_note?: string | null;
  citation_count?: number;
  citation_quality?: 'high' | 'medium' | 'low' | null;
  analysis_depth?: string | null;
  // New asset management fields
  review_status?: 'new' | 'reviewed' | 'watch' | 'archived' | null;
  version_group_id?: string | null;
  previous_report_id?: string | null;
  as_of?: string | null;
  freshness_status?: string | null;
  last_viewed_at?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
}

export interface SubscriptionItem {
  subscription_id?: string;
  email: string;
  ticker: string;
  alert_types?: string[];
  price_threshold?: number | null;
  alert_mode?: string;
  risk_threshold?: string;
  disabled: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_triggered_at?: string | null;
}

export interface AlertEvent {
  id: string;
  ticker: string;
  event_type: string;
  severity: string;
  title: string;
  message: string;
  triggered_at: string;
}

export interface ChatStreamMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status?: 'streaming' | 'done' | 'error';
  evidence?: EvidenceInfo | null;       // AI 消息完成后附上
  metrics?: {
    llm_total_calls?: number;
    tool_total_calls?: number;
    request_started_at?: string;
    request_finished_at?: string;
    [key: string]: unknown;
  } | null;
}

export interface ExecutionTraceEvent {
  id: string;
  type: string;
  stage?: string | null;
  agent?: string | null;
  title?: string | null;
  message?: string | null;
  status?: 'pending' | 'running' | 'done' | 'error' | string | null;
  timestamp?: string | null;
  elapsed_ms?: number | null;
  payload?: Record<string, unknown> | null;
}

export interface DashboardResponse {
  state?: {
    active_asset?: {
      symbol?: string;
      display_name?: string;
      type?: string;
    };
    capabilities?: Record<string, unknown>;
  };
  data?: {
    snapshot?: Record<string, unknown>;
    charts?: Record<string, unknown>;
    news?: unknown[];
    peers?: unknown[];
    valuation?: Record<string, unknown> | null;
  };
}

export interface InsightCard {
  agent_name: string;
  scorer_name?: string | null;
  tab: string;
  score: number;
  score_label: string;
  summary: string;
  key_points: string[];
  risks: string[];
  key_metrics?: Array<{ label: string; value: string }> | null;
  confidence: number;
  as_of?: string | null;
  model_generated: boolean;
  [key: string]: unknown;
}

export interface DashboardInsightsResponse {
  success?: boolean;
  symbol?: string;
  insights?: Record<string, InsightCard>;
  cached?: boolean;
  cache_age_seconds?: number;
  generated_at?: string | null;
}

export interface DemoStatusResponse {
  success: boolean;
  demo_mode: boolean;
  data_source: 'demo' | 'live_or_local' | string;
  missing_services: string[];
  notes: string[];
}

export interface ScreenerItem {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  industry?: string | null;
  country?: string | null;
  exchange?: string | null;
  price?: number | null;
  market_cap?: number | null;
  volume?: number | null;
  beta?: number | null;
  dividend?: number | null;
  change_percent?: number | null;
}

export interface ScreenerRunRequest {
  market: 'US' | 'CN' | 'HK';
  filters?: Record<string, string | number | boolean | null | undefined>;
  limit?: number;
  page?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface ScreenerRunResponse {
  success: boolean;
  market: string;
  items?: ScreenerItem[];
  results?: ScreenerItem[];
  count: number;
  source?: string | null;
  warning?: string | null;
  capability_note?: string | null;
  error?: string | null;
  filters?: Record<string, unknown>;
  sort?: { by?: string; order?: string };
  page?: number;
  limit?: number;
}

export interface ScreenerMetaResponse {
  success: boolean;
  markets: Array<'US' | 'CN' | 'HK'>;
  sort_by: string[];
  sort_order: Array<'asc' | 'desc'>;
  filter_keys: string[];
  source?: string;
}

export interface DailyTask {
  id: string;
  title: string;
  category?: string;
  priority?: number;
  reason?: string;
  action_url?: string;
  icon?: string;
  execution_params?: Record<string, unknown> | null;
}

export interface DailyTaskResponse {
  success: boolean;
  session_id: string;
  tasks: DailyTask[];
  count: number;
}

export interface RagStatusResponse {
  status?: string;
  data?: Record<string, unknown>;
}

export interface RagRunSummary {
  id?: string;
  query_text?: string;
  status?: string;
  started_at?: string;
  fallback_used?: boolean;
  route_name?: string;
  collection?: string;
  [key: string]: unknown;
}

export interface RagRunsResponse {
  status?: string;
  data?: {
    items?: RagRunSummary[];
    next_cursor?: string | null;
  };
}

/** Today Workspace 推荐操作 */
export interface NextAction {
  id: string;
  type: string;
  title: string;
  reason: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  target_route: string;
  related_symbol?: string | null;
}

/** Today Workspace 聚合响应 */
export interface TodayWorkspaceResponse {
  success: boolean;
  as_of: string;
  freshness_status: string;
  summary: string;
  portfolio_snapshot: {
    total_value: number | null;
    total_pnl: number | null;
    total_cost: number | null;
    risk_positions: PortfolioPosition[];
    position_count: number;
  };
  watchlist_movers: any[];
  alert_feed: AlertEvent[];
  reports_to_review: ReportIndexItem[];
  next_actions: NextAction[];
}

/** Portfolio Risk Lens 风险项 */
export interface RiskItem {
  id: string;
  type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  reason: string;
  target_route: string;
  related_symbol?: string | null;
  metric_value?: number | null;
}

/** 行业/币种/市场暴露 */
export interface ExposureItem {
  sector?: string;
  currency?: string;
  market?: string;
  value: number;
  percentage: number;
}

/** Portfolio Risk Lens 响应 */
export interface PortfolioRiskLensResponse {
  success: boolean;
  as_of: string;
  total_value: number;
  total_cost: number;
  risk_score: number;
  concentration_risk: RiskItem[];
  sector_exposure: ExposureItem[];
  currency_exposure: ExposureItem[];
  market_exposure: ExposureItem[];
  stale_research: RiskItem[];
  loss_positions: RiskItem[];
  missing_coverage: RiskItem[];
  next_actions: RiskItem[];
}

/** Risk Lens 历史快照项 */
export interface RiskSnapshot {
  snapshot_date: string;
  risk_score: number;
  total_value: number | null;
  total_cost: number | null;
  concentration_risk_count: number;
  loss_positions_count: number;
  stale_research_count: number;
  missing_coverage_count: number;
  created_at: string;
}

/** Risk Lens 历史趋势响应 */
export interface RiskLensHistoryResponse {
  success: boolean;
  days: number;
  snapshots: RiskSnapshot[];
  error?: string;
}

/** Research Note 研究笔记 */
export interface ResearchNote {
  note_id: string;
  session_id: string;
  user_id: string;
  ticker?: string | null;
  title: string;
  content: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/** Note Image 笔记图片 */
export interface NoteImage {
  filename: string;
  url: string;
  size: number;
  uploaded_at: string;
}

/** Create Note Request */
export interface CreateNoteRequest {
  session_id: string;
  user_id: string;
  title: string;
  content?: string;
  ticker?: string | null;
  tags?: string[];
}

/** Update Note Request */
export interface UpdateNoteRequest {
  title?: string;
  content?: string;
  ticker?: string | null;
  tags?: string[];
}

/** Research Notes List Response */
export interface ResearchNotesListResponse {
  success: boolean;
  notes: ResearchNote[];
  count: number;
  error?: string;
}

/** Research Note Response */
export interface ResearchNoteResponse {
  success: boolean;
  note?: ResearchNote;
  error?: string;
}

/** Note Images Response */
export interface NoteImagesResponse {
  success: boolean;
  images: NoteImage[];
  count: number;
  error?: string;
}

/** Timeline Event */
export interface TimelineEvent {
  id: string;
  symbol: string;
  event_type: 'report' | 'alert' | 'note' | 'risk' | 'evidence' | 'watchlist';
  title: string;
  summary: string;
  occurred_at: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  source?: string;
  target_route?: string;
  related_report_id?: string;
  related_note_id?: string;
  evidence?: {
    confidence?: number | null;
    citation_count?: number | null;
    freshness_status?: string | null;
    quality_state?: string | null;
  };
}

/** Timeline Response */
export interface TimelineResponse {
  success: boolean;
  symbol: string;
  count: number;
  events: TimelineEvent[];
  error?: string;
}

// --- What Changed Types (Phase 4.4) ---
export interface WhatChangedItem {
  id: string;
  symbol?: string | null;
  change_type: 'price' | 'news' | 'risk' | 'report' | 'alert' | 'evidence' | 'portfolio' | 'note';
  title: string;
  before?: string | number | null;
  after?: string | number | null;
  delta?: string | number | null;
  severity: 'low' | 'medium' | 'high' | 'critical';
  reason: string;
  target_route: string;
  evidence?: {
    quality_state?: string | null;
    freshness_status?: string | null;
    citation_quality?: string | null;
    confidence?: number | null;
    citation_count?: number | null;
  } | null;
  report_id?: string | null;
  occurred_at?: string | null;
}

export interface WhatChangedResponse {
  success: boolean;
  as_of: string;
  items: WhatChangedItem[];
  count: number;
}

// Research Quality Types
export interface ResearchQualitySummary {
  total_reports: number;
  stale_reports: number;
  low_quality_reports: number;
  blocked_reports: number;
  warn_reports: number;
  watch_reports: number;
  reviewed_rate: number;
  challenged_conclusions: number;
  health_score: number;
}

export interface ResearchQualityIssue {
  id: string;
  issue_type: 'stale_report' | 'low_citation' | 'blocked_report' | 'warn_report' | 'unreviewed_report' | 'challenged_conclusion' | 'research_hygiene' | 'library_freshness';
  severity: 'low' | 'medium' | 'high' | 'critical';
  title: string;
  reason: string;
  target_route: string;
  related_symbol?: string | null;
  related_report_id?: string | null;
}

export interface ResearchQualityResponse {
  success: boolean;
  as_of: string;
  summary: ResearchQualitySummary;
  top_issues: ResearchQualityIssue[];
  next_actions: any[];
}
