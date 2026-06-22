import axios, { type AxiosError } from 'axios';
import { API_BASE_URL } from '@/config/runtime';
import type {
  EvidenceInfo,
  MeResponse,
  DailyTaskResponse,
  DashboardInsightsResponse,
  DashboardResponse,
  DemoStatusResponse,
  PortfolioSummary,
  RagRunsResponse,
  RagStatusResponse,
  ReportIndexItem,
  SubscriptionItem,
  AlertEvent,
  WatchlistItem,
  TodayWorkspaceResponse,
  PortfolioRiskLensResponse,
  RiskLensHistoryResponse,
  CreateNoteRequest,
  UpdateNoteRequest,
  ResearchNotesListResponse,
  ResearchNoteResponse,
  NoteImagesResponse,
  TimelineResponse,
  WhatChangedResponse,
  ResearchQualityResponse,
  ExecutionTraceEvent,
  ChatHistoryResponse,
  ScreenerMetaResponse,
  ScreenerRunRequest,
  ScreenerRunResponse,
} from './types';

const http = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json; charset=utf-8' },
  timeout: 15_000,
});

const SKIP_GLOBAL_LOADING_HEADER = 'X-Skip-Global-Loading';

// 全局Loading状态管理
let activeRequestCount = 0;
const loadingCallbacks = new Set<(isLoading: boolean) => void>();

export function onLoadingChange(callback: (isLoading: boolean) => void) {
  loadingCallbacks.add(callback);
  return () => loadingCallbacks.delete(callback);
}

function updateLoadingState(delta: number) {
  activeRequestCount = Math.max(0, activeRequestCount + delta);
  const isLoading = activeRequestCount > 0;
  loadingCallbacks.forEach(cb => {
    try {
      cb(isLoading);
    } catch (e) {
      console.error('Loading callback error:', e);
    }
  });
}

function getHeaderValue(headers: unknown, key: string): unknown {
  if (!headers) return undefined;
  if (typeof (headers as { get?: unknown }).get === 'function') {
    return (headers as { get: (name: string) => unknown }).get(key);
  }
  return (headers as Record<string, unknown>)[key];
}

function removeHeader(headers: unknown, key: string): void {
  if (!headers) return;
  if (typeof (headers as { delete?: unknown }).delete === 'function') {
    (headers as { delete: (name: string) => void }).delete(key);
    return;
  }
  delete (headers as Record<string, unknown>)[key];
}

function shouldSkipGlobalLoading(config: { headers?: unknown }): boolean {
  return String(getHeaderValue(config.headers, SKIP_GLOBAL_LOADING_HEADER) || '').trim() === '1';
}

http.interceptors.request.use((config) => {
  const configWithMeta = config as typeof config & { skipGlobalLoading?: boolean };
  configWithMeta.skipGlobalLoading = shouldSkipGlobalLoading(config);
  removeHeader(config.headers, SKIP_GLOBAL_LOADING_HEADER);

  if (!configWithMeta.skipGlobalLoading) {
    // 增加活跃请求计数
    updateLoadingState(1);
  }

  if (typeof window === 'undefined') return config;
  const token = String(window.localStorage.getItem('finsight-access-token') || '').trim();
  if (!token) return config;
  const headers = config.headers ?? {};
  const hasAuthorization = typeof headers.get === 'function'
    ? Boolean(headers.get('Authorization'))
    : Boolean((headers as Record<string, string>).Authorization);
  if (!hasAuthorization) {
    if (typeof headers.set === 'function') {
      headers.set('Authorization', `Bearer ${token}`);
    } else {
      (headers as Record<string, string>).Authorization = `Bearer ${token}`;
    }
  }
  config.headers = headers;
  return config;
}, (error) => {
  // 请求失败也要减少计数
  updateLoadingState(-1);
  return Promise.reject(error);
});

http.interceptors.response.use(
  (resp) => {
    if (!(resp.config as typeof resp.config & { skipGlobalLoading?: boolean }).skipGlobalLoading) {
      // 请求成功，减少计数
      updateLoadingState(-1);
    }
    return resp;
  },
  (error: AxiosError) => {
    if (!(error.config as typeof error.config & { skipGlobalLoading?: boolean } | undefined)?.skipGlobalLoading) {
      // 请求失败，减少计数
      updateLoadingState(-1);
    }
    return Promise.reject(error);
  },
);

export interface ChatStreamCallbacks {
  onToken?: (token: string) => void;
  onEvent?: (event: ExecutionTraceEvent, payload?: Record<string, unknown>) => void;
  onDone?: (evidence: EvidenceInfo | null, payload?: unknown) => void;
  onError?: (message: string) => void;
}

/** done 载荷 → EvidenceInfo，提取后端 quality/metrics/source */
function _extractEvidence(payload: Record<string, unknown>): EvidenceInfo {
  const quality = payload.quality as Record<string, unknown> | null | undefined;
  const metrics = payload.metrics as Record<string, unknown> | null | undefined;
  const report = payload.report as Record<string, unknown> | null | undefined;

    const citationCount =
    typeof report?.citation_count === 'number' ? report.citation_count :
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    typeof (payload as any).citation_count === 'number' ? (payload as any).citation_count : null;

  const confidenceScore =
    typeof report?.confidence_score === 'number' ? report.confidence_score :
    typeof quality?.confidence_score === 'number' ? quality.confidence_score : null;

  const qualityState = (quality?.state as string) || (payload.quality_blocked ? 'block' : payload.publishable ? 'pass' : null);

  const citationQuality: EvidenceInfo['citationQuality'] =
    citationCount == null ? null :
    citationCount >= 5 ? 'high' :
    citationCount >= 2 ? 'medium' : 'low';

  const requestStarted = metrics?.request_started_at as string | undefined;
  const degraded = Boolean(payload.quality_blocked) || Boolean(payload.soft_blocked);

  return {
    source: (payload.source as string) || 'langgraph',
    asOf: requestStarted || new Date().toISOString(),
    freshnessStatus: 'live' as const,
    fallbackLevel: 0,
    confidence: confidenceScore,
    modelGenerated: true,
    degraded,
    citationCount: citationCount,
    citationQuality: citationQuality,
    qualityState: qualityState as string | null,
    quality: quality ?? null,
  };
}

export const apiClient = {
  async login(payload: { email: string; password: string }): Promise<{
    success: boolean;
    token: string;
    user_id: string;
    role: string;
    email: string;
  }> {
    const { data } = await http.post('/api/auth/login', payload);
    return data;
  },

  async logout(): Promise<{ success: boolean }> {
    const { data } = await http.post('/api/auth/logout');
    return data;
  },

  async getMe(): Promise<MeResponse> {
    const { data } = await http.get<MeResponse>('/api/me');
    return data;
  },

  async getDemoStatus(): Promise<DemoStatusResponse> {
    const { data } = await http.get<DemoStatusResponse>('/api/demo/status');
    return data;
  },

  async getDataSourceStatus(): Promise<DemoStatusResponse> {
    const { data } = await http.get<DemoStatusResponse>('/api/data-sources/status');
    return data;
  },

  async getDashboard(symbol: string): Promise<DashboardResponse> {
    const { data } = await http.get<DashboardResponse>('/api/dashboard', { params: { symbol } });
    return data;
  },

  async getDashboardInsights(symbol: string, force = false): Promise<DashboardInsightsResponse> {
    const { data } = await http.get<DashboardInsightsResponse>('/api/dashboard/insights', {
      params: { symbol, force },
    });
    return data;
  },

  async getQuote(symbol: string): Promise<unknown> {
    const { data } = await http.get(`/api/quote/${symbol}`);
    return data;
  },

  async getKline(symbol: string, period = '1mo', interval = '1d'): Promise<unknown> {
    const { data } = await http.get(`/api/kline/${symbol}`, { params: { period, interval } });
    return data;
  },

  async getNews(symbol: string): Promise<unknown> {
    const { data } = await http.get(`/api/stock/news/${symbol}`);
    return data;
  },

  async getFinancials(symbol: string): Promise<unknown> {
    const { data } = await http.get(`/api/financials/${symbol}`);
    return data;
  },

  async getScreenerMeta(): Promise<ScreenerMetaResponse> {
    const { data } = await http.get<ScreenerMetaResponse>('/api/screener/filters/meta', {
      headers: { [SKIP_GLOBAL_LOADING_HEADER]: '1' },
    });
    return data;
  },

  async runScreener(payload: ScreenerRunRequest): Promise<ScreenerRunResponse> {
    const { data } = await http.post<ScreenerRunResponse>('/api/screener/run', payload, {
      headers: { [SKIP_GLOBAL_LOADING_HEADER]: '1' },
      timeout: 45_000,
    });
    return data;
  },

  async getDailyTasks(sessionId: string): Promise<DailyTaskResponse> {
    const { data } = await http.get<DailyTaskResponse>('/api/tasks/daily', {
      params: { session_id: sessionId },
    });
    return data;
  },

  async getRagStatus(): Promise<RagStatusResponse> {
    const { data } = await http.get<RagStatusResponse>('/diagnostics/rag/status');
    return data;
  },

  async listRagRuns(params?: { q?: string; fallbackOnly?: boolean; limit?: number }): Promise<RagRunsResponse> {
    const { data } = await http.get<RagRunsResponse>('/diagnostics/rag/runs', {
      params: {
        q: params?.q,
        fallback_only: params?.fallbackOnly ?? false,
        limit: params?.limit ?? 20,
      },
    });
    return data;
  },

  async getChatHistory(sessionId: string, limit = 100): Promise<ChatHistoryResponse> {
    const { data } = await http.get<ChatHistoryResponse>('/api/chat/history', {
      params: { session_id: sessionId, limit },
      headers: { [SKIP_GLOBAL_LOADING_HEADER]: '1' },
    });
    return data;
  },

  async clearChatHistory(sessionId: string): Promise<{ success: boolean; session_id: string }> {
    const { data } = await http.delete('/api/chat/history', {
      params: { session_id: sessionId },
      headers: { [SKIP_GLOBAL_LOADING_HEADER]: '1' },
    });
    return data;
  },

  async streamChat(
    body: Record<string, unknown>,
    callbacks: ChatStreamCallbacks,
  ): Promise<void> {
    const token = typeof window === 'undefined'
      ? ''
      : String(window.localStorage.getItem('finsight-access-token') || '').trim();
    const response = await fetch(`${API_BASE_URL}/chat/supervisor/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('无法读取流式响应');
    }

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split('\n');
      buffer = chunks.pop() || '';
      for (const line of chunks) {
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6);
        try {
          const payload = JSON.parse(raw) as Record<string, unknown>;
          if (payload.type === 'token' && typeof payload.content === 'string') {
            callbacks.onToken?.(payload.content);
          } else if (payload.type === 'done') {
            const evidence = _extractEvidence(payload);
            callbacks.onDone?.(evidence, payload);
          } else if (payload.type === 'error') {
            callbacks.onError?.(String(payload.message || '流式会话失败'));
          } else {
            callbacks.onEvent?.({
              id: String(payload.id || `${payload.type || 'event'}-${Date.now()}-${Math.random().toString(16).slice(2)}`),
              type: String(payload.type || 'event'),
              stage: typeof payload.stage === 'string' ? payload.stage : null,
              agent: typeof payload.agent === 'string' ? payload.agent : null,
              title: typeof payload.title === 'string' ? payload.title : null,
              message: typeof payload.message === 'string'
                ? payload.message
                : typeof payload.content === 'string'
                  ? payload.content
                  : null,
              status: typeof payload.status === 'string' ? payload.status : null,
              timestamp: typeof payload.timestamp === 'string' ? payload.timestamp : new Date().toISOString(),
              elapsed_ms: typeof payload.elapsed_ms === 'number' ? payload.elapsed_ms : null,
              payload,
            }, payload);
          }
        } catch {
          // ignore invalid SSE frame
        }
      }
    }
  },

  // ── Watchlist ──
  async listWatchlist(userId?: string, q?: string): Promise<{ success: boolean; items: WatchlistItem[]; count: number }> {
    const params: Record<string, string> = {};
    if (userId) params.user_id = userId;
    if (q) params.q = q;
    const { data } = await http.get('/api/user/watchlist', { params });
    return data;
  },
  async addWatchlist(payload: { user_id?: string; ticker: string; name?: string; tags?: string[]; note?: string; group?: string; priority?: number; watch_reason?: string; research_status?: string }) {
    const { data } = await http.post('/api/user/watchlist/add', payload);
    return data;
  },
  async updateWatchlist(payload: { user_id?: string; ticker: string; name?: string; tags?: string[]; note?: string; group?: string; priority?: number; watch_reason?: string; research_status?: string }) {
    const { data } = await http.post('/api/user/watchlist/update', payload);
    return data;
  },
  async removeWatchlist(payload: { user_id?: string; ticker: string }) {
    const { data } = await http.post('/api/user/watchlist/remove', payload);
    return data;
  },

  // ── Portfolio ──
  async getPortfolioSummary(sessionId: string): Promise<PortfolioSummary> {
    const { data } = await http.get<PortfolioSummary>('/api/portfolio/summary', { params: { session_id: sessionId } });
    return data;
  },
  async upsertPosition(params: {
    sessionId: string;
    ticker: string;
    shares: number;
    avgCost?: number | null;
    name?: string;
    tags?: string[];
    note?: string;
    sector?: string;
    currency?: string;
    openedAt?: string;
  }) {
    const { data } = await http.put(
      `/api/portfolio/positions/${encodeURIComponent(params.ticker)}`,
      {
        shares: params.shares,
        avg_cost: params.avgCost ?? null,
        name: params.name,
        tags: params.tags,
        note: params.note,
        sector: params.sector,
        currency: params.currency,
        opened_at: params.openedAt,
      },
      { params: { session_id: params.sessionId } },
    );
    return data;
  },
  async removePosition(params: { sessionId: string; ticker: string }) {
    const { data } = await http.delete(`/api/portfolio/positions/${encodeURIComponent(params.ticker)}`, {
      params: { session_id: params.sessionId },
    });
    return data;
  },
  async bulkImportPositions(params: {
    sessionId: string;
    positions: Array<{ ticker: string; shares: number; avg_cost?: number | null; name?: string; tags?: string[]; note?: string }>;
  }) {
    const { data } = await http.post('/api/portfolio/bulk', {
      session_id: params.sessionId,
      positions: params.positions,
    });
    return data;
  },

  // ── Reports ──
  async listReports(params: {
    sessionId: string;
    ticker?: string;
    query?: string;
    dateFrom?: string;
    dateTo?: string;
    tag?: string;
    sourceType?: string;
    reviewStatus?: string;
    qualityStateFilter?: string;
    sortBy?: string;
    favoriteOnly?: boolean;
    limit?: number;
  }): Promise<{ success: boolean; items: ReportIndexItem[]; count: number }> {
    const { data } = await http.get('/api/reports/index', {
      params: {
        session_id: params.sessionId,
        ticker: params.ticker,
        query: params.query,
        date_from: params.dateFrom,
        date_to: params.dateTo,
        tag: params.tag,
        source_type: params.sourceType,
        review_status: params.reviewStatus,
        quality_state_filter: params.qualityStateFilter,
        sort_by: params.sortBy ?? 'generated_at_desc',
        favorite_only: params.favoriteOnly,
        limit: params.limit ?? 50,
      },
    });
    return data;
  },
  async setReportFavorite(params: { sessionId: string; reportId: string; isFavorite: boolean }) {
    const { data } = await http.post(`/api/reports/${encodeURIComponent(params.reportId)}/favorite`, {
      session_id: params.sessionId,
      is_favorite: params.isFavorite,
    });
    return data;
  },
  async patchReportNote(params: { sessionId: string; reportId: string; note: string }) {
    const { data } = await http.patch(`/api/reports/${encodeURIComponent(params.reportId)}/note`, {
      session_id: params.sessionId,
      user_note: params.note,
    });
    return data;
  },

  async patchReportReviewStatus(params: { sessionId: string; reportId: string; reviewStatus: string }) {
    const { data } = await http.patch(`/api/reports/${encodeURIComponent(params.reportId)}/review_status`, {
      session_id: params.sessionId,
      review_status: params.reviewStatus,
    });
    return data;
  },

  async patchReportTags(params: { sessionId: string; reportId: string; tags: string[] }) {
    const { data } = await http.patch(`/api/reports/${encodeURIComponent(params.reportId)}/tags`, {
      session_id: params.sessionId,
      tags: params.tags,
    });
    return data;
  },

  async markReportViewed(params: { sessionId: string; reportId: string }) {
    const { data } = await http.post(`/api/reports/${encodeURIComponent(params.reportId)}/viewed`, {
      session_id: params.sessionId,
    });
    return data;
  },

  async compareReports(params: { sessionId: string; id1: string; id2: string }): Promise<unknown> {
    const { data } = await http.get('/api/reports/compare', {
      params: { session_id: params.sessionId, id1: params.id1, id2: params.id2 },
    });
    return data;
  },

  async getReportReplay(params: { sessionId: string; reportId: string }): Promise<unknown> {
    const { data } = await http.get(`/api/reports/replay/${encodeURIComponent(params.reportId)}`, {
      params: { session_id: params.sessionId },
    });
    return data;
  },

  // ── Subscriptions / Alerts ──
  async listSubscriptions(email: string): Promise<{ success: boolean; subscriptions: SubscriptionItem[]; count: number }> {
    const { data } = await http.get('/api/subscriptions', { params: { email } });
    return data;
  },
  async toggleSubscription(payload: { email: string; ticker: string; enabled: boolean }) {
    const { data } = await http.post('/api/subscription/toggle', payload);
    return data;
  },
  async subscribe(payload: { email: string; ticker: string; alert_mode: string; risk_threshold?: string }) {
    const { data } = await http.post('/api/subscribe', payload);
    return data;
  },
  async unsubscribe(payload: { email: string; ticker?: string }) {
    const { data } = await http.post('/api/unsubscribe', payload);
    return data;
  },
  async alertsFeed(email: string, limit = 30): Promise<{ success: boolean; events: AlertEvent[]; count: number }> {
    const { data } = await http.get('/api/alerts/feed', { params: { email, limit } });
    return data;
  },

  // ── Today Workspace ──
  async getTodayWorkspace(sessionId: string, userId: string): Promise<TodayWorkspaceResponse> {
    const { data } = await http.get<TodayWorkspaceResponse>('/api/today', {
      params: { session_id: sessionId, user_id: userId },
    });
    return data;
  },

  // ── Portfolio Risk Lens ──
  async getPortfolioRiskLens(sessionId: string, userId: string): Promise<PortfolioRiskLensResponse> {
    const { data } = await http.get<PortfolioRiskLensResponse>('/api/portfolio/risk-lens', {
      params: { session_id: sessionId, user_id: userId },
    });
    return data;
  },

  async getRiskLensHistory(sessionId: string, userId: string, days: number = 30): Promise<RiskLensHistoryResponse> {
    const { data } = await http.get<RiskLensHistoryResponse>('/api/portfolio/risk-lens/history', {
      params: { session_id: sessionId, user_id: userId, days },
    });
    return data;
  },

  // ── Research Notes ──
  async createNote(req: CreateNoteRequest): Promise<{ success: boolean; note_id?: string; error?: string }> {
    const { data } = await http.post('/api/research-notes', req);
    return data;
  },

  async listNotes(
    sessionId: string,
    userId: string,
    ticker?: string,
    query?: string,
    limit: number = 50,
    offset: number = 0
  ): Promise<ResearchNotesListResponse> {
    const { data } = await http.get<ResearchNotesListResponse>('/api/research-notes', {
      params: { session_id: sessionId, user_id: userId, ticker, q: query, limit, offset },
    });
    return data;
  },

  async getNote(noteId: string): Promise<ResearchNoteResponse> {
    const { data } = await http.get<ResearchNoteResponse>(`/api/research-notes/${noteId}`);
    return data;
  },

  async updateNote(noteId: string, req: UpdateNoteRequest): Promise<{ success: boolean; error?: string }> {
    const { data } = await http.put(`/api/research-notes/${noteId}`, req);
    return data;
  },

  async deleteNote(noteId: string): Promise<{ success: boolean; error?: string }> {
    const { data } = await http.delete(`/api/research-notes/${noteId}`);
    return data;
  },

  async uploadNoteImage(noteId: string, file: File): Promise<{ success: boolean; url?: string; error?: string }> {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await http.post(`/api/research-notes/${noteId}/images`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  async listNoteImages(noteId: string): Promise<NoteImagesResponse> {
    const { data } = await http.get<NoteImagesResponse>(`/api/research-notes/${noteId}/images`);
    return data;
  },

  async deleteNoteImage(noteId: string, filename: string): Promise<{ success: boolean; error?: string }> {
    const { data } = await http.delete(`/api/research-notes/${noteId}/images/${filename}`);
    return data;
  },

  // ── Timeline ──
  async getTimeline(params: {
    symbol: string;
    sessionId: string;
    userId: string;
    eventType?: string;
    from?: string;
    to?: string;
    limit?: number;
  }): Promise<TimelineResponse> {
    const { data } = await http.get<TimelineResponse>(`/api/timeline/${params.symbol}`, {
      params: {
        session_id: params.sessionId,
        user_id: params.userId,
        event_type: params.eventType,
        from: params.from,
        to: params.to,
        limit: params.limit ?? 50,
      },
    });
    return data;
  },

  // --- What Changed API (Phase 4.4) ---
  async getWhatChanged(params: {
    sessionId: string;
    userId: string;
    symbol?: string;
    limit?: number;
  }): Promise<WhatChangedResponse> {
    const { data } = await http.get<WhatChangedResponse>('/api/what-changed', {
      params: {
        session_id: params.sessionId,
        user_id: params.userId,
        symbol: params.symbol,
        limit: params.limit || 5,
      },
    });
    return data;
  },

  // --- Research Quality API (Phase 4.5) ---
  async getResearchQuality(params: {
    sessionId: string;
    userId: string;
    symbol?: string;
  }): Promise<ResearchQualityResponse> {
    const { data } = await http.get<ResearchQualityResponse>('/api/research-quality', {
      params: {
        session_id: params.sessionId,
        user_id: params.userId,
        symbol: params.symbol,
      },
    });
    return data;
  },

  async getSystemHealth(): Promise<unknown> {
    const { data } = await http.get('/api/system/health');
    return data;
  },

  async getHealthTrend(source?: string, days: number = 7): Promise<unknown> {
    const params = new URLSearchParams();
    if (source) params.append('source', source);
    params.append('days', String(days));
    const { data } = await http.get(`/api/system/health/trend?${params.toString()}`);
    return data;
  },

  async getHealthStats(): Promise<unknown> {
    const { data } = await http.get('/api/system/health/stats');
    return data;
  },

  async getTopList(ticker: string): Promise<Record<string, unknown>> {
    const { data } = await http.get<Record<string, unknown>>(`/api/stock/top-list/${encodeURIComponent(ticker)}`);
    return data;
  },

  async getNorthFlow(): Promise<Record<string, unknown>> {
    const { data } = await http.get<Record<string, unknown>>('/api/market/north-flow');
    return data;
  },

  async getMarginTrading(ticker: string): Promise<Record<string, unknown>> {
    const { data } = await http.get<Record<string, unknown>>(`/api/stock/margin/${encodeURIComponent(ticker)}`);
    return data;
  },
};

// 导出底层 axios 实例，供需要直接调用 get/post 的页面使用
export { http };
