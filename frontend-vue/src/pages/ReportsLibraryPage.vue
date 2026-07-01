<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { ReportIndexItem, ResearchQualitySummary, ResearchQualityIssue } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import ActionButton from '@/components/ActionButton.vue';
import EmptyState from '@/components/EmptyState.vue';
import EvidencePanel from '@/components/EvidencePanel.vue';
import LoadingState from '@/components/LoadingState.vue';
import ResearchQualityOverview from '@/components/ResearchQualityOverview.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import { reportFriendlyError } from '@/utils/error';

const identity = useIdentityStore();
const router = useRouter();

// ── 数据 ────────────────────────────────────────────────────
const items = ref<ReportIndexItem[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

// ── Research Quality (Phase 4.5) ─────────────────────────────
const qualitySummary = ref<ResearchQualitySummary>({
  total_reports: 0,
  stale_reports: 0,
  low_quality_reports: 0,
  blocked_reports: 0,
  warn_reports: 0,
  watch_reports: 0,
  reviewed_rate: 0,
  challenged_conclusions: 0,
  health_score: 100,
});
const qualityIssues = ref<ResearchQualityIssue[]>([]);
const showQuality = ref(false);

// ── 筛选 & 排序状态 ─────────────────────────────────────────
const searchQ = ref('');
const tickerFilter = ref('');
const favoriteOnly = ref(false);
const activeTag = ref<string | null>(null);
const sortBy = ref('generated_at_desc');
const reviewStatusFilter = ref('');
const qualityFilter = ref('');
const currentPage = ref(1);
const pageSize = 3;

const SORT_OPTIONS = [
  { value: 'generated_at_desc', label: '最新优先' },
  { value: 'generated_at_asc',  label: '最旧优先' },
  { value: 'confidence_desc',   label: '置信度高优先' },
  { value: 'updated_at_desc',   label: '最近更新' },
];

const REVIEW_OPTIONS = [
  { value: '',         label: '全部状态' },
  { value: 'new',      label: '未读' },
  { value: 'reviewed', label: '已复查' },
  { value: 'watch',    label: '持续关注' },
  { value: 'archived', label: '已归档' },
];

const REVIEW_LABELS: Record<string, { label: string; color: string }> = {
  new:      { label: '未读',   color: '#3b82f6' },
  reviewed: { label: '已复查', color: '#27ae60' },
  watch:    { label: '关注',   color: '#d97706' },
  archived: { label: '归档',   color: '#8c887e' },
};

// ── 标签聚合 ─────────────────────────────────────────────────
const allTags = computed(() => {
  const set = new Set<string>();
  for (const r of items.value) for (const t of (r.tags || [])) set.add(t);
  return [...set].sort();
});

// ── 客户端二次过滤（服务端已过滤主要条件，客户端只做 tag & 文本精炼）
const displayed = computed(() => {
  let list = items.value;
  const q = searchQ.value.trim().toLowerCase();
  if (q) list = list.filter(r =>
    (r.title || '').toLowerCase().includes(q) ||
    (r.ticker || '').toLowerCase().includes(q) ||
    (r.summary || '').toLowerCase().includes(q),
  );
  if (activeTag.value) list = list.filter(r => (r.tags || []).includes(activeTag.value!));
  return list;
});

const totalPages = computed(() => Math.max(1, Math.ceil(displayed.value.length / pageSize)));
const pageStart = computed(() => (currentPage.value - 1) * pageSize);
const pageEnd = computed(() => Math.min(displayed.value.length, pageStart.value + pageSize));
const pagedReports = computed(() => displayed.value.slice(pageStart.value, pageEnd.value));

function goPage(page: number) {
  currentPage.value = Math.min(totalPages.value, Math.max(1, page));
}

function fmtDate(v?: string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days < 1) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (days < 7) return `${days} 天前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

// ── 拉取数据 ──────────────────────────────────────────────────
async function refresh(): Promise<void> {
  loading.value = true; errorMsg.value = null;
  try {
    const [reportsResp, qualityResp] = await Promise.all([
      apiClient.listReports({
        sessionId: identity.sessionId,
        ticker: tickerFilter.value.trim() || undefined,
        favoriteOnly: favoriteOnly.value || undefined,
        reviewStatus: reviewStatusFilter.value || undefined,
        qualityStateFilter: qualityFilter.value || undefined,
        sortBy: sortBy.value,
      }),
      apiClient.getResearchQuality({
        sessionId: identity.sessionId,
        userId: identity.userId,
      }),
    ]);
    items.value = reportsResp.items || [];
    qualitySummary.value = qualityResp.summary;
    qualityIssues.value = qualityResp.top_issues;
  } catch (e) { errorMsg.value = reportFriendlyError(e, '报告库暂时加载失败，请刷新重试。'); }
  finally { loading.value = false; }
}

// ── 收藏切换 ──────────────────────────────────────────────────
async function toggleFav(item: ReportIndexItem, e: Event): Promise<void> {
  e.stopPropagation();
  const next = !item.is_favorite;
  try {
    await apiClient.setReportFavorite({ sessionId: identity.sessionId, reportId: item.report_id, isFavorite: next });
    item.is_favorite = next;
  } catch (err) { errorMsg.value = reportFriendlyError(err, '收藏状态更新失败，请稍后重试。'); }
}

// ── 复查状态切换 ──────────────────────────────────────────────
async function setReviewStatus(item: ReportIndexItem, status: string, e: Event): Promise<void> {
  e.stopPropagation();
  try {
    await apiClient.patchReportReviewStatus({ sessionId: identity.sessionId, reportId: item.report_id, reviewStatus: status });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    item.review_status = status as any;
  } catch (err) { errorMsg.value = reportFriendlyError(err, '复查状态更新失败，请稍后重试。'); }
}

// ── 标签管理 ──────────────────────────────────────────────────
const tagEditItem = ref<ReportIndexItem | null>(null);
const tagInput = ref('');

function openTagEdit(item: ReportIndexItem, e: Event) {
  e.stopPropagation();
  tagEditItem.value = item;
  tagInput.value = (item.tags || []).join(', ');
}

async function saveTagEdit(): Promise<void> {
  if (!tagEditItem.value) return;
  const tags = tagInput.value.split(',').map(t => t.trim()).filter(Boolean);
  try {
    await apiClient.patchReportTags({ sessionId: identity.sessionId, reportId: tagEditItem.value.report_id, tags });
    tagEditItem.value.tags = tags;
    tagEditItem.value = null;
  } catch (err) { errorMsg.value = reportFriendlyError(err, '标签保存失败，请稍后重试。'); }
}

// ── 报告详情侧边栏 ─────────────────────────────────────────────
const sidebarItem = ref<ReportIndexItem | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const sidebarReplay = ref<any>(null);
const sidebarLoading = ref(false);
const noteText = ref('');
const noteSaving = ref(false);
let noteDebounce: ReturnType<typeof setTimeout> | null = null;

async function openSidebar(item: ReportIndexItem): Promise<void> {
  sidebarItem.value = item;
  noteText.value = item.user_note || '';
  sidebarReplay.value = null;
  sidebarLoading.value = true;
  void apiClient.markReportViewed({ sessionId: identity.sessionId, reportId: item.report_id });
  try {
    const replay = await apiClient.getReportReplay({ sessionId: identity.sessionId, reportId: item.report_id });
    sidebarReplay.value = replay;
  } catch { /* 降级到列表摘要 */ }
  finally { sidebarLoading.value = false; }
}

function closeSidebar() {
  sidebarItem.value = null; sidebarReplay.value = null;
  noteText.value = '';
  if (noteDebounce) clearTimeout(noteDebounce);
}

function onNoteInput() {
  if (noteDebounce) clearTimeout(noteDebounce);
  noteDebounce = setTimeout(() => void saveNote(), 600);
}

async function saveNote(): Promise<void> {
  if (!sidebarItem.value) return;
  noteSaving.value = true;
  try {
    await apiClient.patchReportNote({ sessionId: identity.sessionId, reportId: sidebarItem.value.report_id, note: noteText.value });
    sidebarItem.value.user_note = noteText.value;
  } catch (err) { errorMsg.value = reportFriendlyError(err, '个人备注保存失败，请稍后重试。'); }
  finally { noteSaving.value = false; }
}

// ── 版本对比 ──────────────────────────────────────────────────
const compareMode = ref(false);
const compareA = ref<ReportIndexItem | null>(null);
const compareB = ref<ReportIndexItem | null>(null);
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const compareResult = ref<any>(null);
const compareLoading = ref(false);
const compareError = ref<string | null>(null);

function toggleCompareSelect(item: ReportIndexItem) {
  if (compareA.value?.report_id === item.report_id) { compareA.value = null; return; }
  if (compareB.value?.report_id === item.report_id) { compareB.value = null; return; }
  if (!compareA.value) { compareA.value = item; return; }
  compareB.value = item;
}

function isSelected(item: ReportIndexItem) {
  return compareA.value?.report_id === item.report_id || compareB.value?.report_id === item.report_id;
}

function selectedLabel(item: ReportIndexItem): 'A' | 'B' | null {
  if (compareA.value?.report_id === item.report_id) return 'A';
  if (compareB.value?.report_id === item.report_id) return 'B';
  return null;
}

async function runCompare(): Promise<void> {
  if (!compareA.value || !compareB.value) return;
  compareLoading.value = true; compareError.value = null; compareResult.value = null;
  try {
    const res = await apiClient.compareReports({ sessionId: identity.sessionId, id1: compareA.value.report_id, id2: compareB.value.report_id });
    compareResult.value = res;
  } catch (e) { compareError.value = reportFriendlyError(e, '报告对比失败，请稍后重试。'); }
  finally { compareLoading.value = false; }
}

function exitCompare() {
  compareMode.value = false; compareA.value = null; compareB.value = null;
  compareResult.value = null; compareError.value = null;
}

// ── Markdown 导出 ──────────────────────────────────────────────
function exportMarkdown(item: ReportIndexItem, e: Event) {
  e.stopPropagation();
  const dateStr = item.generated_at ? new Date(item.generated_at).toISOString().slice(0, 10) : 'unknown';
  const quality = item.quality_state || 'pass';
  const filename = `${item.ticker || 'report'}_${dateStr}_${quality}.md`;

  const evidenceSummary = [
    `- **数据截至**: ${item.as_of || item.generated_at || '—'}`,
    `- **新鲜度**: ${item.freshness_status || '—'}`,
    `- **置信度**: ${item.confidence_score != null ? Math.round(item.confidence_score * 100) + '%' : '—'}`,
    `- **引用数量**: ${item.citation_count ?? '—'}（质量：${item.citation_quality || '—'}）`,
    `- **质检状态**: ${quality}`,
  ].join('\n');

  const content = [
    `# ${item.title || item.report_id}`,
    ``,
    `**代码**: ${item.ticker || '—'} | **生成时间**: ${item.generated_at || '—'} | **分析深度**: ${item.analysis_depth || '—'}`,
    ``,
    `## 可信度摘要`,
    ``,
    evidenceSummary,
    ``,
    `## 摘要`,
    ``,
    item.summary || '（无摘要）',
    ``,
    item.user_note ? `## 个人备注\n\n${item.user_note}` : '',
    ``,
    `---`,
    `*由 FinSight AI 生成 · 仅供学习研究，不构成投资建议*`,
  ].filter(l => l !== undefined).join('\n');

  try {
    const blob = new Blob([content], { type: 'text/markdown; charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch {
    alert('导出失败，请检查浏览器权限');
  }
}

// ── 重新分析（跳转 Chat 预填）────────────────────────────────
function reanalyze(item: ReportIndexItem, e: Event) {
  e.stopPropagation();
  const q = item.ticker
    ? `请重新深度分析 ${item.ticker}，生成最新研究报告，并与之前的分析对比变化`
    : '请重新分析并生成报告';
  void router.push({ name: 'chat', query: { prefill: q } });
}

function startReportTool(tool: 'generate' | 'financials'): void {
  const prefill = tool === 'generate'
    ? '请生成一份可复查的 AI 研究报告，要求列出关键证据、风险、引用质量和待确认问题，不给买卖建议。'
    : '请分析最新财报，按收入、利润率、现金流、资产负债和风险假设输出复查清单，不给交易建议。';
  void router.push({ path: '/chat', query: { mode: tool === 'financials' ? 'financials' : 'report', prefill } });
}

onMounted(refresh);
watch(() => identity.sessionId, () => void refresh());
watch([searchQ, activeTag, tickerFilter, favoriteOnly, sortBy, reviewStatusFilter, qualityFilter], () => {
  currentPage.value = 1;
});
watch(displayed, () => {
  if (currentPage.value > totalPages.value) currentPage.value = totalPages.value;
});
</script>

<template>
  <section class="page">
    <!-- ── 页头 ── -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">报告库</h1>
        <span class="badge-count">
          {{ displayed.length ? pageStart + 1 : 0 }}-{{ pageEnd }} / {{ displayed.length }} 份
        </span>
      </div>
      <div class="header-right">
        <button class="btn-compare" :class="{ active: compareMode }" @click="compareMode ? exitCompare() : (compareMode = true)">
          {{ compareMode ? '退出对比' : '⚖ 版本对比' }}
        </button>
        <ActionButton variant="ghost" :loading="loading" loading-text="刷新中..." @click="refresh">
          刷新
        </ActionButton>
      </div>
    </div>

    <section class="report-tools" data-testid="report-tools">
      <article>
        <span>生成报告</span>
        <strong>AI 研究报告</strong>
        <p>从报告库发起生成，产物回流到这里复查、收藏和对比。</p>
        <ActionButton size="sm" @click="startReportTool('generate')">进入生成</ActionButton>
      </article>
      <article>
        <span>财报分析</span>
        <strong>财务复查入口</strong>
        <p>财报拆解不再单独占页面，作为报告库的生成工具使用。</p>
        <ActionButton size="sm" @click="startReportTool('financials')">分析财报</ActionButton>
      </article>
    </section>

    <!-- ── 对比模式提示栏 ── -->
    <div v-if="compareMode" class="compare-bar">
      <div class="compare-hint">
        <span class="select-label">A：</span>
        <strong v-if="compareA" class="sel-name">{{ compareA.ticker || compareA.report_id.slice(0, 8) }} — {{ compareA.title?.slice(0,30) }}</strong>
        <span v-else class="sel-empty">点击报告选择 A</span>
        <span class="vs">vs</span>
        <span class="select-label">B：</span>
        <strong v-if="compareB" class="sel-name">{{ compareB.ticker || compareB.report_id.slice(0, 8) }} — {{ compareB.title?.slice(0,30) }}</strong>
        <span v-else class="sel-empty">点击报告选择 B</span>
      </div>
      <ActionButton :disabled="!compareA || !compareB" :loading="compareLoading" loading-text="对比中..." @click="runCompare">
        开始对比
      </ActionButton>
    </div>

    <!-- ── 对比结果 ── -->
    <Transition name="slide-down">
      <div v-if="compareResult" class="compare-result">
        <div class="cr-head">
          <span class="cr-title">📊 对比结果</span>
          <button class="btn-close-sm" @click="compareResult = null">✕</button>
        </div>
        <div class="cr-meta">
          <div class="cr-report">
            <span class="cr-ab a">A</span>
            <span class="cr-rname">{{ compareResult.report_a?.title || compareResult.report_a?.report_id }}</span>
            <span class="cr-date">{{ fmtDate(compareResult.report_a?.generated_at) }}</span>
          </div>
          <div class="cr-report">
            <span class="cr-ab b">B</span>
            <span class="cr-rname">{{ compareResult.report_b?.title || compareResult.report_b?.report_id }}</span>
            <span class="cr-date">{{ fmtDate(compareResult.report_b?.generated_at) }}</span>
          </div>
        </div>
        <div class="cr-grid">
          <div v-if="compareResult.diff?.confidence_score" class="diff-card">
            <div class="diff-label">置信度</div>
            <div class="diff-vals">
              <span>A: {{ compareResult.diff.confidence_score.a != null ? Math.round(compareResult.diff.confidence_score.a * 100) + '%' : '—' }}</span>
              <span>B: {{ compareResult.diff.confidence_score.b != null ? Math.round(compareResult.diff.confidence_score.b * 100) + '%' : '—' }}</span>
              <span v-if="compareResult.diff.confidence_score.delta != null"
                :class="compareResult.diff.confidence_score.delta > 0 ? 'pos' : 'neg'">
                {{ compareResult.diff.confidence_score.delta > 0 ? '▲' : '▼' }}
                {{ Math.abs(Math.round(compareResult.diff.confidence_score.delta * 100)) }}%
              </span>
            </div>
          </div>
          <div v-if="compareResult.diff?.citation_count" class="diff-card">
            <div class="diff-label">引用数量</div>
            <div class="diff-vals">
              <span>A: {{ compareResult.diff.citation_count.a }}</span>
              <span>B: {{ compareResult.diff.citation_count.b }}</span>
            </div>
          </div>
          <div v-if="compareResult.diff?.data_freshness" class="diff-card">
            <div class="diff-label">数据截至时间</div>
            <div class="diff-vals small">
              <span>A: {{ fmtDate(compareResult.diff.data_freshness.a) || '—' }}</span>
              <span>B: {{ fmtDate(compareResult.diff.data_freshness.b) || '—' }}</span>
            </div>
          </div>
          <div v-if="compareResult.diff?.sentiment?.changed" class="diff-card">
            <div class="diff-label">观点变化</div>
            <div class="diff-vals">
              <span>{{ compareResult.diff.sentiment.a || '—' }}</span>
              <span class="arrow">→</span>
              <span class="changed">{{ compareResult.diff.sentiment.b || '—' }}</span>
            </div>
          </div>
          <div v-if="compareResult.diff?.risks" class="diff-card">
            <div class="diff-label">风险变化</div>
            <div class="diff-vals">
              <span class="pos" v-if="compareResult.diff.risks.removed?.length">-{{ compareResult.diff.risks.removed.length }} 消除</span>
              <span class="neg" v-if="compareResult.diff.risks.added?.length">+{{ compareResult.diff.risks.added.length }} 新增</span>
              <span>{{ compareResult.diff.risks.unchanged_count }} 不变</span>
            </div>
          </div>
          <div v-if="compareResult.diff?.risks?.added?.length || compareResult.diff?.risks?.removed?.length" class="diff-card full">
            <div class="diff-label">风险详情</div>
            <div class="risk-lists">
              <div v-if="compareResult.diff.risks.added?.length" class="risk-group">
                <div class="rg-label neg">新增风险</div>
                <div v-for="r in compareResult.diff.risks.added" :key="r" class="risk-item neg">{{ r }}</div>
              </div>
              <div v-if="compareResult.diff.risks.removed?.length" class="risk-group">
                <div class="rg-label pos">消除风险</div>
                <div v-for="r in compareResult.diff.risks.removed" :key="r" class="risk-item pos">{{ r }}</div>
              </div>
            </div>
          </div>
          <div v-if="compareResult.diff?.summary" class="diff-card full">
            <div class="diff-label">摘要对比</div>
            <div class="diff-summary-grid">
              <div><div class="cr-ab a" style="margin-bottom:6px">A</div><p class="diff-sum-text">{{ compareResult.diff.summary.a || '—' }}</p></div>
              <div><div class="cr-ab b" style="margin-bottom:6px">B</div><p class="diff-sum-text">{{ compareResult.diff.summary.b || '—' }}</p></div>
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Research Quality (Phase 4.5) ── -->
    <div v-if="showQuality && items.length > 0" class="quality-section">
      <div class="quality-header">
        <h2 class="quality-title">📊 研究库健康度</h2>
        <button class="btn-toggle" @click="showQuality = false">收起</button>
      </div>
      <ResearchQualityOverview
        :summary="qualitySummary"
        :top-issues="qualityIssues"
      />
    </div>
    <div v-if="!showQuality && items.length > 0" class="quality-collapsed">
      <button class="btn-expand" @click="showQuality = true">
        📊 查看研究库健康度 ({{ qualitySummary.health_score }} 分)
      </button>
    </div>

    <!-- ── 搜索 + 筛选工具栏 ── -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">⌕</span>
        <input v-model="searchQ" class="search-input" placeholder="搜索标题、代码、摘要…">
      </div>
      <input v-model="tickerFilter" placeholder="Ticker" class="input ticker-input" @keyup.enter="refresh">
      <select v-model="sortBy" class="input sort-select" @change="refresh">
        <option v-for="o in SORT_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <select v-model="reviewStatusFilter" class="input review-select" @change="refresh">
        <option v-for="o in REVIEW_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <label class="fav-check">
        <input v-model="favoriteOnly" type="checkbox" class="check-native" @change="refresh">
        <span class="check-box" :class="{ checked: favoriteOnly }" />
        仅收藏
      </label>
    </div>

    <!-- ── 标签筛选栏 ── -->
    <div v-if="allTags.length" class="tag-bar">
      <span class="tag-bar-label">标签：</span>
      <button v-for="tag in allTags" :key="tag" class="tag-chip" :class="{ active: activeTag === tag }" @click="activeTag = activeTag === tag ? null : tag">
        {{ tag }}
      </button>
      <button v-if="activeTag" class="tag-clear" @click="activeTag = null">✕ 清除</button>
    </div>

    <StatusBanner
      v-if="errorMsg"
      variant="error"
      :message="errorMsg"
      dismissible
      @dismiss="errorMsg = null"
    />
    <StatusBanner
      v-if="compareError"
      variant="error"
      :message="compareError"
      dismissible
      @dismiss="compareError = null"
    />

    <!-- ── 加载 ── -->
    <LoadingState v-if="loading" label="正在加载报告库..." />

    <!-- ── 空态 ── -->
    <EmptyState
      v-else-if="items.length === 0"
      title="还没有研究报告"
      hint="在「AI 助手」发起现有研究流程后，生成的报告会保存在这里。"
      action-label="前往 AI 助手"
      @action="router.push('/chat')"
    />
    <EmptyState
      v-else-if="displayed.length === 0"
      title="没有匹配的报告"
      hint="可以清空筛选条件，或换一个 ticker / 关键词。"
      compact
    />
    <div v-else-if="displayed.length > pageSize" class="pager top-pager">
      <span class="pager-summary">第 {{ currentPage }} / {{ totalPages }} 页，显示 {{ pageStart + 1 }}-{{ pageEnd }} 条</span>
      <button class="pager-btn" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
      <div class="pager-pages">
        <button
          v-for="page in totalPages"
          :key="page"
          class="pager-num"
          :class="{ active: page === currentPage }"
          @click="goPage(page)"
        >
          {{ page }}
        </button>
      </div>
      <button class="pager-btn" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
    </div>

    <!-- ── 报告列表 ── -->
    <div v-if="!loading && items.length > 0 && displayed.length > 0" class="report-list">
      <div
        v-for="r in pagedReports"
        :key="r.report_id"
        class="report-card"
        :class="{ 'selected-compare': compareMode && isSelected(r) }"
        @click="compareMode ? toggleCompareSelect(r) : openSidebar(r)"
      >
        <!-- 对比标签 -->
        <div v-if="compareMode && isSelected(r)" class="compare-badge" :class="selectedLabel(r)?.toLowerCase()">
          {{ selectedLabel(r) }}
        </div>

        <!-- 左侧操作 -->
        <div class="card-left">
          <button class="star" :class="{ on: r.is_favorite }" @click="e => toggleFav(r, e)">
            {{ r.is_favorite ? '★' : '☆' }}
          </button>
        </div>

        <!-- 主体 -->
        <div class="report-body">
          <!-- 行1：Ticker + depth + quality + review -->
          <div class="report-row1">
            <span v-if="r.ticker" class="report-ticker">{{ r.ticker }}</span>
            <span v-if="r.analysis_depth" class="depth-badge">{{ r.analysis_depth }}</span>
            <span v-if="r.quality_state === 'pass'" class="quality-pass">✓ 质检</span>
            <span v-if="r.quality_state === 'block'" class="quality-block">✗ 质检</span>
            <span
              v-if="r.review_status"
              class="review-badge"
              :style="{ background: (REVIEW_LABELS[r.review_status]?.color || '#8c887e') + '20', color: REVIEW_LABELS[r.review_status]?.color || '#8c887e' }"
            >{{ REVIEW_LABELS[r.review_status]?.label }}</span>
            <h3 class="report-title">{{ r.title || '(无标题)' }}</h3>
            <span v-if="r.citation_count" class="cite-badge">引用 {{ r.citation_count }}</span>
          </div>

          <!-- 摘要 -->
          <p v-if="r.summary" class="report-summary">{{ r.summary }}</p>

          <!-- EvidencePanel -->
          <EvidencePanel
            :as-of="r.as_of || r.generated_at"
            :confidence="r.confidence_score"
            :source="r.source_type"
            :quality-state="r.quality_state"
            :citation-count="r.citation_count"
            :citation-quality="r.citation_quality"
            :freshness-status="(r.freshness_status || undefined) as any"
            :model-generated="true"
            compact
            class="report-evidence"
          />

          <!-- 标签 -->
          <div v-if="(r.tags || []).length" class="report-tags">
            <span v-for="t in r.tags" :key="t" class="tag-pill" @click.stop="activeTag = t">{{ t }}</span>
          </div>

          <!-- 底栏 -->
          <div class="report-footer">
            <span class="report-date">{{ fmtDate(r.generated_at) }}</span>
            <span v-if="r.last_viewed_at" class="last-viewed">查看于 {{ fmtDate(r.last_viewed_at) }}</span>
            <span v-if="r.user_note" class="has-note">📝</span>
            <div class="report-actions" @click.stop>
              <!-- 复查状态菜单 -->
              <select
                class="status-select"
                :value="r.review_status || 'new'"
                @change="e => setReviewStatus(r, (e.target as HTMLSelectElement).value, e)"
              >
                <option v-for="o in REVIEW_OPTIONS.slice(1)" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <button class="btn-action" title="编辑标签" @click="e => openTagEdit(r, e)">🏷</button>
              <button class="btn-action" title="导出 Markdown" @click="e => exportMarkdown(r, e)">↓ MD</button>
              <button class="btn-action" title="重新分析" @click="e => reanalyze(r, e)">↺</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="displayed.length > pageSize" class="pager">
        <button class="pager-btn" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
        <div class="pager-pages">
          <button
            v-for="page in totalPages"
            :key="page"
            class="pager-num"
            :class="{ active: page === currentPage }"
            @click="goPage(page)"
          >
            {{ page }}
          </button>
        </div>
        <button class="pager-btn" :disabled="currentPage >= totalPages" @click="goPage(currentPage + 1)">下一页</button>
      </div>
    </div>

    <!-- ── 标签编辑 Modal ── -->
    <Teleport to="body">
      <div v-if="tagEditItem" class="modal-backdrop" @click.self="tagEditItem = null">
        <div class="modal-sm">
          <div class="modal-head">
            <span class="modal-title">编辑标签 — {{ tagEditItem.ticker || tagEditItem.report_id.slice(0, 8) }}</span>
            <button class="btn-close-sm" @click="tagEditItem = null">✕</button>
          </div>
          <p class="modal-hint">逗号分隔，例如：AI芯片, 财报后复盘, 待跟踪</p>
          <input v-model="tagInput" class="input full" placeholder="AI芯片, 高风险" @keyup.enter="saveTagEdit">
          <div class="modal-actions">
            <button class="btn-primary" @click="saveTagEdit">保存</button>
            <button class="btn-cancel" @click="tagEditItem = null">取消</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── 报告详情侧边栏 ── -->
    <Teleport to="body">
      <div v-if="sidebarItem && !compareMode" class="sidebar-backdrop" @click.self="closeSidebar">
        <aside class="sidebar">
          <div class="sidebar-head">
            <div class="sidebar-meta-top">
              <span v-if="sidebarItem.ticker" class="sidebar-ticker">{{ sidebarItem.ticker }}</span>
              <span v-if="sidebarItem.analysis_depth" class="depth-badge">{{ sidebarItem.analysis_depth }}</span>
              <span v-if="sidebarItem.review_status" class="review-badge"
                :style="{ background: (REVIEW_LABELS[sidebarItem.review_status]?.color || '#8c887e') + '20', color: REVIEW_LABELS[sidebarItem.review_status]?.color || '#8c887e' }">
                {{ REVIEW_LABELS[sidebarItem.review_status]?.label }}
              </span>
            </div>
            <div class="sidebar-head-actions">
              <button v-if="sidebarItem.ticker" class="btn-action" @click="router.push(`/dossier/${sidebarItem.ticker}`)">时间线</button>
              <button class="btn-action" @click="e => exportMarkdown(sidebarItem!, e)">↓ MD</button>
              <button class="btn-action" @click="e => reanalyze(sidebarItem!, e)">↺ 刷新</button>
              <button class="sidebar-close" @click="closeSidebar">✕</button>
            </div>
          </div>

          <h3 class="sidebar-title">{{ sidebarItem.title || '(无标题)' }}</h3>

          <!-- 完整 EvidencePanel -->
          <EvidencePanel
            :as-of="sidebarItem.as_of || sidebarItem.generated_at"
            :confidence="sidebarItem.confidence_score"
            :source="sidebarItem.source_type"
            :quality-state="sidebarItem.quality_state"
            :citation-count="sidebarItem.citation_count"
            :citation-quality="sidebarItem.citation_quality"
            :freshness-status="(sidebarItem.freshness_status || undefined) as any"
            :model-generated="true"
          />

          <LoadingState v-if="sidebarLoading" label="正在加载报告内容..." compact />

          <!-- 报告全文 / 摘要 -->
          <div v-else class="sidebar-sections">
            <div v-if="sidebarReplay?.report?.content || sidebarItem.summary" class="sidebar-section">
              <div class="section-title">摘要</div>
              <p class="sidebar-summary">{{ sidebarReplay?.report?.content || sidebarItem.summary }}</p>
            </div>

            <!-- 标签 -->
            <div class="sidebar-section">
              <div class="section-title">
                标签
                <button class="tag-edit-btn" @click="e => openTagEdit(sidebarItem!, e)">编辑</button>
              </div>
              <div class="sidebar-tags">
                <span v-for="t in (sidebarItem.tags || [])" :key="t" class="tag-pill">{{ t }}</span>
                <span v-if="!(sidebarItem.tags || []).length" class="no-tags">暂无标签</span>
              </div>
            </div>

            <!-- 引用来源 -->
            <div v-if="sidebarReplay?.citations?.length" class="sidebar-section">
              <div class="section-title">引用来源 ({{ sidebarReplay.citations.length }})</div>
              <ul class="citations-list">
                <li v-for="(c, i) in sidebarReplay.citations.slice(0, 8)" :key="i" class="citation-item">
                  <span class="cite-num">{{ i + 1 }}</span>
                  <div class="cite-body">
                    <div class="cite-title">{{ c.title || c.source_id }}</div>
                    <div v-if="c.snippet" class="cite-snippet">{{ c.snippet }}</div>
                    <div class="cite-meta">
                      <span v-if="c.published_date">{{ fmtDate(c.published_date) }}</span>
                      <span v-if="c.confidence != null"> · 可信度 {{ Math.round(c.confidence * 100) }}%</span>
                    </div>
                  </div>
                </li>
              </ul>
            </div>

            <!-- 版本链接 -->
            <div v-if="sidebarItem.previous_report_id" class="sidebar-section">
              <div class="section-title">版本历史</div>
              <div class="version-link">
                <span class="vl-label">上一版本：</span>
                <span class="vl-id">{{ sidebarItem.previous_report_id.slice(0, 16) }}…</span>
              </div>
            </div>
          </div>

          <!-- 备注 -->
          <div class="note-section">
            <div class="note-label">
              <span>个人备注</span>
              <span v-if="noteSaving" class="note-saving">保存中…</span>
            </div>
            <textarea v-model="noteText" class="note-area" placeholder="记录投资判断、复核意见、待跟踪问题…" rows="5" @input="onNoteInput" />
          </div>

          <!-- 跳转 -->
          <div class="sidebar-nav-btns">
            <button v-if="sidebarItem.ticker" class="btn-nav" @click="router.push(`/dossier/${sidebarItem.ticker}`)">
              查看 {{ sidebarItem.ticker }} 标的档案
            </button>
            <button class="btn-nav outline" @click="e => { reanalyze(sidebarItem!, e); closeSidebar(); }">
              发起 Chat 追问
            </button>
          </div>
        </aside>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 14px; }

/* ── 页头 ── */
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 24px; font-weight: 700; margin: 0; }
.badge-count { font-size: 12px; font-weight: 600; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 10px; border-radius: 20px; }
.header-right { display: flex; gap: 8px; align-items: center; }
.btn-compare { padding: 9px 16px; border: 1.5px solid var(--fin-border); border-radius: 10px; background: var(--fin-card); font-size: 14px; font-weight: 600; cursor: pointer; color: var(--fin-text-2); transition: all 0.15s; }
.btn-compare.active { border-color: var(--fin-primary); color: var(--fin-primary); background: var(--fin-primary-soft); }
.btn-ghost { display: flex; align-items: center; gap: 6px; padding: 9px 12px; border: 1.5px solid var(--fin-border); border-radius: 10px; background: var(--fin-card); cursor: pointer; font-size: 15px; color: var(--fin-muted); }
.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.report-tools { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.report-tools article { border: 1.5px solid var(--fin-border); border-radius: 8px; padding: 16px; background: var(--fin-card); }
.report-tools span { display: block; color: var(--fin-primary); font-size: 12px; font-weight: 800; }
.report-tools strong { display: block; margin-top: 6px; color: var(--fin-text); font-size: 18px; }
.report-tools p { margin: 8px 0 14px; color: var(--fin-muted); line-height: 1.6; }
.report-tools button { border: 0; border-radius: 8px; padding: 9px 12px; background: var(--fin-primary); color: #fff; cursor: pointer; font-weight: 700; }

/* ── 对比栏 ── */
.compare-bar { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 18px; background: var(--fin-primary-soft); border: 1.5px solid var(--fin-primary); border-radius: 12px; flex-wrap: wrap; }
.compare-hint { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 14px; }
.select-label { font-weight: 700; color: var(--fin-primary); }
.sel-name { color: var(--fin-text); }
.sel-empty { color: var(--fin-muted); font-style: italic; }
.vs { color: var(--fin-muted); font-weight: 600; }
.btn-primary { padding: 9px 18px; border: none; border-radius: 8px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; white-space: nowrap; flex-shrink: 0; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary:hover:not(:disabled) { opacity: 0.88; }

/* ── 对比结果 ── */
.compare-result { background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 14px; padding: 18px; }
.cr-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.cr-title { font-size: 15px; font-weight: 700; }
.btn-close-sm { border: none; background: transparent; font-size: 16px; cursor: pointer; color: var(--fin-muted); padding: 2px 6px; }
.cr-meta { display: flex; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.cr-report { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--fin-bg); border-radius: 8px; }
.cr-ab { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: #fff; flex-shrink: 0; }
.cr-ab.a { background: #3b82f6; }
.cr-ab.b { background: #cc785c; }
.cr-rname { font-size: 13px; font-weight: 600; color: var(--fin-text); }
.cr-date { font-size: 12px; color: var(--fin-muted); }
.cr-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.diff-card { padding: 12px; background: var(--fin-bg); border-radius: 8px; }
.diff-card.full { grid-column: 1 / -1; }
.diff-label { font-size: 11px; font-weight: 700; color: var(--fin-muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .04em; }
.diff-vals { display: flex; gap: 10px; font-size: 13px; align-items: center; flex-wrap: wrap; }
.diff-vals.small { font-size: 12px; }
.pos { color: #27ae60; font-weight: 700; }
.neg { color: #e74c3c; font-weight: 700; }
.arrow { color: var(--fin-muted); }
.changed { font-weight: 700; color: var(--fin-primary); }
.diff-summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; }
.diff-sum-text { font-size: 13px; color: var(--fin-text-2); line-height: 1.6; margin: 0; }
.risk-lists { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px; }
.risk-group { display: flex; flex-direction: column; gap: 4px; }
.rg-label { font-size: 11px; font-weight: 700; margin-bottom: 2px; }
.risk-item { font-size: 12px; padding: 3px 8px; border-radius: 4px; line-height: 1.4; }
.risk-item.neg { background: #fff1f0; color: #cf1322; }
.risk-item.pos { background: #f0faf4; color: #2d7d46; }

/* ── 工具栏 ── */
.toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.search-wrap { flex: 2; min-width: 180px; display: flex; align-items: center; gap: 8px; padding: 9px 14px; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 10px; }
.search-icon { font-size: 16px; color: var(--fin-muted); }
.search-input { flex: 1; border: none; outline: none; font-size: 14px; background: transparent; color: var(--fin-text); }
.input { padding: 9px 12px; border: 1.5px solid var(--fin-border); border-radius: 10px; font-size: 13px; background: var(--fin-card); color: var(--fin-text); }
.input:focus { outline: none; border-color: var(--fin-primary); }
.ticker-input { width: 90px; }
.sort-select { min-width: 110px; }
.review-select { min-width: 100px; }
.fav-check { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--fin-text-2); cursor: pointer; white-space: nowrap; }
.check-native { display: none; }
.check-box { width: 15px; height: 15px; border: 2px solid var(--fin-border); border-radius: 3px; }
.check-box.checked { background: var(--fin-primary); border-color: var(--fin-primary); }

/* ── 标签栏 ── */
.tag-bar { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.tag-bar-label { font-size: 12px; color: var(--fin-muted); font-weight: 600; }
.tag-chip { padding: 3px 10px; border: 1.5px solid var(--fin-border); border-radius: 20px; background: transparent; font-size: 12px; cursor: pointer; color: var(--fin-text-2); transition: all 0.15s; }
.tag-chip.active { background: var(--fin-primary); border-color: var(--fin-primary); color: #fff; font-weight: 600; }
.tag-clear { padding: 3px 10px; border: none; background: transparent; font-size: 12px; cursor: pointer; color: var(--fin-danger); }

.loader { width: 18px; height: 18px; border: 2px solid var(--fin-border); border-top-color: var(--fin-primary); border-radius: 50%; animation: spin 0.8s linear infinite; }

/* ── 报告列表 ── */
.report-list { display: flex; flex-direction: column; gap: 8px; }

.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 10px 2px 0;
  flex-wrap: wrap;
}

.top-pager {
  justify-content: space-between;
  padding: 8px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 12px;
  background: var(--fin-card);
}

.pager-summary {
  color: var(--fin-muted);
  font-size: 13px;
  font-weight: 700;
}

.pager-pages {
  display: flex;
  gap: 5px;
  align-items: center;
}

.pager-btn,
.pager-num {
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card);
  color: var(--fin-text-2);
  cursor: pointer;
  font-weight: 700;
}

.pager-btn {
  padding: 7px 12px;
}

.pager-num {
  min-width: 32px;
  height: 32px;
}

.pager-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.pager-num.active {
  border-color: var(--fin-primary);
  background: var(--fin-primary);
  color: #fff;
}

.report-card {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 16px 18px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.15s;
}
.report-card:hover { border-color: var(--fin-primary); transform: translateY(-1px); box-shadow: 0 3px 14px rgba(204,120,92,0.07); }
.report-card.selected-compare { border-color: var(--fin-primary); background: var(--fin-primary-soft); }

.compare-badge { position: absolute; top: -8px; left: 14px; font-size: 11px; font-weight: 800; color: #fff; padding: 1px 8px; border-radius: 10px; }
.compare-badge.a { background: #3b82f6; }
.compare-badge.b { background: #cc785c; }

.card-left { display: flex; flex-direction: column; align-items: center; gap: 8px; flex-shrink: 0; }
.star { border: none; background: transparent; font-size: 20px; cursor: pointer; color: #bfb6a3; padding: 0; transition: transform 0.15s; }
.star:hover { transform: scale(1.2); }
.star.on { color: var(--fin-primary); }

.report-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }

.report-row1 { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.report-ticker { font-size: 12px; font-weight: 700; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 2px 8px; border-radius: 6px; }
.depth-badge { font-size: 10px; padding: 2px 6px; border-radius: 20px; background: #f3eee3; color: var(--fin-muted); text-transform: uppercase; }
.quality-pass { font-size: 10px; padding: 2px 6px; border-radius: 20px; background: #e6f4ec; color: #2d7d46; font-weight: 700; }
.quality-block { font-size: 10px; padding: 2px 6px; border-radius: 20px; background: #fce4e4; color: #c44545; font-weight: 700; }
.review-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 20px; }
.report-title { font-size: 14px; font-weight: 600; color: var(--fin-text); margin: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.cite-badge { font-size: 11px; padding: 2px 7px; border-radius: 20px; background: #f3eee3; color: var(--fin-muted); white-space: nowrap; flex-shrink: 0; }

.report-summary { font-size: 13px; color: var(--fin-text-2); margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.6; }
.report-evidence { margin-top: 2px; }

.report-tags { display: flex; gap: 5px; flex-wrap: wrap; }
.tag-pill { font-size: 11px; padding: 2px 8px; border-radius: 20px; background: #f0f0f0; color: var(--fin-text-2); cursor: pointer; transition: background 0.15s; }
.tag-pill:hover { background: var(--fin-primary-soft); color: var(--fin-primary); }

.report-footer { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.report-date { font-size: 12px; color: var(--fin-muted); }
.last-viewed { font-size: 11px; color: var(--fin-muted); }
.has-note { font-size: 13px; }

.report-actions { display: flex; gap: 5px; align-items: center; margin-left: auto; }
.status-select { padding: 4px 8px; border: 1.5px solid var(--fin-border); border-radius: 6px; font-size: 11px; background: var(--fin-bg); color: var(--fin-text-2); cursor: pointer; }
.btn-action { padding: 4px 9px; border: 1.5px solid var(--fin-border); border-radius: 6px; background: var(--fin-bg); font-size: 12px; font-weight: 600; color: var(--fin-text-2); cursor: pointer; transition: all 0.15s; }
.btn-action:hover { border-color: var(--fin-primary); color: var(--fin-primary); }

/* ── 标签编辑 Modal ── */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
.modal-sm { background: var(--fin-bg); border-radius: 8px; padding: 22px; width: min(400px, 100%); max-height: min(88vh, 680px); overflow-y: auto; box-shadow: 0 8px 40px rgba(0,0,0,0.14); }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.modal-title { font-size: 15px; font-weight: 700; }
.modal-hint { font-size: 12px; color: var(--fin-muted); margin: 0 0 12px; }
.input.full { width: 100%; box-sizing: border-box; margin-bottom: 14px; }
.modal-actions { display: flex; gap: 8px; }
.btn-cancel { padding: 9px 18px; border: 1.5px solid var(--fin-border); border-radius: 8px; background: transparent; font-size: 14px; color: var(--fin-muted); cursor: pointer; }

/* ── 侧边栏 ── */
.sidebar-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.28); z-index: 1000; display: flex; justify-content: flex-end; }
.sidebar { width: min(500px, 96vw); height: 100dvh; max-height: 100dvh; background: var(--fin-bg); box-shadow: -4px 0 32px rgba(0,0,0,0.1); padding: 22px 22px 32px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }

.sidebar-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.sidebar-meta-top { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.sidebar-ticker { font-size: 13px; font-weight: 700; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 2px 8px; border-radius: 6px; }
.sidebar-head-actions { display: flex; gap: 5px; align-items: center; flex-shrink: 0; }
.sidebar-close { width: 34px; height: 34px; border: 1px solid var(--fin-border); border-radius: 8px; background: var(--fin-card); font-size: 18px; cursor: pointer; color: var(--fin-muted); }
.sidebar-title { font-size: 17px; font-weight: 700; color: var(--fin-text); margin: 0; line-height: 1.4; }

.sidebar-sections { display: flex; flex-direction: column; gap: 14px; }
.sidebar-section { background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 10px; padding: 14px 16px; }
.section-title { font-size: 12px; font-weight: 700; color: var(--fin-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; }
.tag-edit-btn { font-size: 11px; color: var(--fin-primary); border: none; background: transparent; cursor: pointer; text-decoration: underline; }
.sidebar-summary { font-size: 14px; color: var(--fin-text-2); line-height: 1.75; margin: 0; white-space: pre-wrap; }
.sidebar-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.no-tags { font-size: 12px; color: var(--fin-muted); font-style: italic; }

/* 引用 */
.citations-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.citation-item { display: flex; gap: 10px; }
.cite-num { font-size: 11px; font-weight: 800; color: var(--fin-primary); background: var(--fin-primary-soft); width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
.cite-body { flex: 1; }
.cite-title { font-size: 12px; font-weight: 600; color: var(--fin-text); }
.cite-snippet { font-size: 11px; color: var(--fin-muted); line-height: 1.5; margin-top: 2px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.cite-meta { font-size: 11px; color: var(--fin-muted); margin-top: 2px; }

/* 版本链接 */
.version-link { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.vl-label { color: var(--fin-muted); }
.vl-id { font-family: monospace; color: var(--fin-text-2); font-size: 12px; }

/* 备注 */
.note-section { display: flex; flex-direction: column; gap: 6px; }
.note-label { display: flex; align-items: center; justify-content: space-between; font-size: 13px; font-weight: 700; color: var(--fin-text); }
.note-saving { font-size: 11px; color: var(--fin-primary); }
.note-area { width: 100%; box-sizing: border-box; padding: 12px; border: 1.5px solid var(--fin-border); border-radius: 10px; font-size: 14px; background: var(--fin-card); resize: vertical; font-family: inherit; line-height: 1.7; color: var(--fin-text); min-height: 100px; }
.note-area:focus { outline: none; border-color: var(--fin-primary); }

/* 跳转按钮 */
.sidebar-nav-btns { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-nav { flex: 1; padding: 10px; border: none; border-radius: 8px; background: var(--fin-primary); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; text-align: center; }
.btn-nav:hover { opacity: 0.88; }
.btn-nav.outline { background: transparent; border: 1.5px solid var(--fin-primary); color: var(--fin-primary); }
.btn-nav.outline:hover { background: var(--fin-primary-soft); }

/* 动画 */
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.25s ease; overflow: hidden; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; max-height: 0; }
.slide-down-enter-to, .slide-down-leave-from { opacity: 1; max-height: 1200px; }

@media (max-width: 640px) {
  .cr-grid { grid-template-columns: 1fr 1fr; }
  .report-tools { grid-template-columns: 1fr; }
  .toolbar { flex-direction: column; align-items: stretch; }
  .sort-select, .review-select, .ticker-input { width: 100%; box-sizing: border-box; }
}

/* ── Research Quality (Phase 4.5) ── */
.quality-section {
  margin-bottom: 1.5rem;
  padding: 1.5rem;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.quality-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.quality-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.btn-toggle {
  padding: 0.25rem 0.75rem;
  background: #f3f4f6;
  border: none;
  border-radius: 4px;
  font-size: 0.875rem;
  color: #6b7280;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-toggle:hover {
  background: #e5e7eb;
}

.quality-collapsed {
  margin-bottom: 1.5rem;
}

.btn-expand {
  width: 100%;
  padding: 1rem;
  background: #f9fafb;
  border: 1px dashed #d1d5db;
  border-radius: 8px;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #4b5563;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-expand:hover {
  background: #f3f4f6;
  border-color: #9ca3af;
}
</style>
