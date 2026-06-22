<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { PortfolioPosition } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import SkeletonLoader from '@/components/SkeletonLoader.vue';
import ActionButton from '@/components/ActionButton.vue';
import EmptyState from '@/components/EmptyState.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import { reportFriendlyError } from '@/utils/error';

const identity = useIdentityStore();
const route = useRoute();
const router = useRouter();

const positions = ref<PortfolioPosition[]>([]);
const totals = ref<{ value: number | null; cost: number | null; pnl: number | null }>({ value: null, cost: null, pnl: null });
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const addExpanded = ref(false);

const editTicker = ref('');
const editShares = ref('');
const editAvgCost = ref('');
const editName = ref('');

const activeTag = ref<string | null>(null);

const allTags = computed(() => {
  const set = new Set<string>();
  for (const p of positions.value) for (const t of (p.tags || [])) set.add(t);
  return [...set].sort();
});

const filteredPositions = computed(() =>
  activeTag.value ? positions.value.filter((p) => (p.tags || []).includes(activeTag.value!)) : positions.value,
);

function toggleTag(tag: string) { activeTag.value = activeTag.value === tag ? null : tag; }

const pnlPercent = computed(() => {
  if (!totals.value.cost || !totals.value.pnl) return null;
  return ((totals.value.pnl / totals.value.cost) * 100).toFixed(2);
});
const activeTool = computed(() => String(route.query.tool || 'risk'));
const portfolioTools = [
  {
    key: 'risk',
    title: '风险透镜',
    summary: '集中度、亏损持仓、研究覆盖缺口都在这里复查。',
    action: '生成风险复查清单',
  },
  {
    key: 'optimize',
    title: '组合优化',
    summary: '把仓位约束转成研究问题，由 AI 输出可复核的调整清单。',
    action: '打开优化问答',
  },
  {
    key: 'backtest',
    title: '策略回测',
    summary: '回测不再单独占导航，作为组合工具的一种验证动作。',
    action: '准备回测问题',
  },
];

// ── CSV import ──
const showImport = ref(false);
const csvText = ref('');
const csvFile = ref<HTMLInputElement | null>(null);
const csvRows = ref<Array<{ ticker: string; shares: number; avg_cost: number | null; name: string; tags: string[]; note: string; error?: string }>>([]);
const csvParsed = ref(false);

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => { csvText.value = String(ev.target?.result || ''); };
  reader.readAsText(file, 'utf-8');
}

function parseCsv() {
  csvRows.value = [];
  const lines = csvText.value.split('\n').map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    if (line.startsWith('#') || line.toLowerCase().startsWith('ticker')) continue;
    const cols = line.split(',').map((c) => c.trim());
    const [rawTicker, rawShares, rawCost, rawName, rawTags, rawNote] = cols;
    const ticker = (rawTicker || '').toUpperCase();
    const shares = Number(rawShares);
    if (!ticker || !Number.isFinite(shares) || shares < 0) {
      csvRows.value.push({ ticker: rawTicker || '', shares: 0, avg_cost: null, name: '', tags: [], note: '', error: `格式错误: "${line}"` });
      continue;
    }
    const avg_cost = rawCost && rawCost !== '' ? Number(rawCost) : null;
    if (avg_cost !== null && (!Number.isFinite(avg_cost) || avg_cost < 0)) {
      csvRows.value.push({ ticker, shares: 0, avg_cost: null, name: '', tags: [], note: '', error: `成本价非法: "${rawCost}"` });
      continue;
    }
    csvRows.value.push({ ticker, shares, avg_cost, name: rawName || '', tags: rawTags ? rawTags.split(';').map((t) => t.trim()).filter(Boolean) : [], note: rawNote || '' });
  }
  csvParsed.value = true;
}

const csvValidRows = computed(() => csvRows.value.filter((r) => !r.error));
const csvErrorRows = computed(() => csvRows.value.filter((r) => r.error));

async function confirmImport() {
  if (!csvValidRows.value.length) return;
  loading.value = true;
  errorMsg.value = null;
  try {
    await apiClient.bulkImportPositions({ sessionId: identity.sessionId, positions: csvValidRows.value.map((r) => ({ ticker: r.ticker, shares: r.shares, avg_cost: r.avg_cost, name: r.name || undefined, tags: r.tags.length ? r.tags : undefined, note: r.note || undefined })) });
    showImport.value = false; csvText.value = ''; csvRows.value = []; csvParsed.value = false;
    await refresh();
  } catch (e) { errorMsg.value = reportFriendlyError(e, '导入持仓失败，请检查 CSV 内容后重试。'); } finally { loading.value = false; }
}

function closeImport() { showImport.value = false; csvText.value = ''; csvRows.value = []; csvParsed.value = false; }

// ── Inline edit ──
const editingTicker = ref<string | null>(null);
const editForm = ref({ shares: '', avgCost: '', name: '', tags: '', note: '', sector: '', currency: '', openedAt: '' });

function startEdit(p: PortfolioPosition) {
  editingTicker.value = p.ticker;
  editForm.value = {
    shares: String(p.shares),
    avgCost: p.avg_cost != null ? String(p.avg_cost) : '',
    name: p.name || '',
    tags: (p.tags || []).join(';'),
    note: p.note || '',
    sector: p.sector || '',
    currency: p.currency || 'USD',
    openedAt: p.opened_at || '',
  };
}
function cancelEdit() { editingTicker.value = null; }

async function saveEdit(ticker: string): Promise<void> {
  const shares = Number(editForm.value.shares);
  if (!Number.isFinite(shares) || shares < 0) { errorMsg.value = '股数须为非负数'; return; }
  const avgCost = editForm.value.avgCost.trim() === '' ? null : Number(editForm.value.avgCost);
  if (avgCost !== null && (!Number.isFinite(avgCost) || avgCost < 0)) { errorMsg.value = '成本价须为非负数'; return; }
  const tags = editForm.value.tags.split(';').map((t) => t.trim()).filter(Boolean);
  try {
    await apiClient.upsertPosition({
      sessionId: identity.sessionId,
      ticker,
      shares,
      avgCost,
      name: editForm.value.name.trim() || undefined,
      tags: tags.length ? tags : undefined,
      note: editForm.value.note.trim() || undefined,
      sector: editForm.value.sector.trim() || undefined,
      currency: editForm.value.currency.trim() || undefined,
      openedAt: editForm.value.openedAt.trim() || undefined,
    });
    editingTicker.value = null; await refresh();
  } catch (e) { errorMsg.value = reportFriendlyError(e, '保存持仓失败，请稍后重试。'); }
}

function fmt(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });
}

async function refresh(): Promise<void> {
  loading.value = true; errorMsg.value = null;
  try {
    const resp = await apiClient.getPortfolioSummary(identity.sessionId);
    positions.value = resp.positions || [];
    totals.value = { value: resp.total_value, cost: resp.total_cost, pnl: resp.total_pnl };
  } catch (e) { errorMsg.value = reportFriendlyError(e, '持仓列表加载失败，请刷新重试。'); } finally { loading.value = false; }
}

async function save(): Promise<void> {
  const ticker = editTicker.value.trim().toUpperCase();
  const shares = Number(editShares.value);
  if (!ticker || !Number.isFinite(shares) || shares < 0) { errorMsg.value = '请输入合法 ticker 与非负 shares'; return; }
  const avgCost = editAvgCost.value.trim() === '' ? null : Number(editAvgCost.value);
  if (avgCost !== null && (!Number.isFinite(avgCost) || avgCost < 0)) { errorMsg.value = '成本价须为非负数'; return; }
  try {
    await apiClient.upsertPosition({ sessionId: identity.sessionId, ticker, shares, avgCost, name: editName.value.trim() || undefined });
    editTicker.value = ''; editShares.value = ''; editAvgCost.value = ''; editName.value = '';
    addExpanded.value = false;
    await refresh();
  } catch (e) { errorMsg.value = reportFriendlyError(e, '保存持仓失败，请稍后重试。'); }
}

function openTool(tool: string): void {
  const promptMap: Record<string, string> = {
    risk: '请基于当前组合生成风险透镜复查清单，重点看集中度、亏损持仓和研究覆盖缺口，不给买卖建议。',
    optimize: '请基于当前组合做组合优化复查，只输出仓位约束、风险暴露和需要人工确认的问题，不给交易指令。',
    backtest: '请帮我准备一个策略回测研究计划，说明标的、区间、基准和风险指标，不输出收益承诺。',
  };
  void router.push({
    path: '/chat',
    query: {
      mode: 'qa',
      prefill: promptMap[tool] || promptMap.risk,
    },
  });
}

async function remove(ticker: string): Promise<void> {
  try {
    await apiClient.removePosition({ sessionId: identity.sessionId, ticker });
    positions.value = positions.value.filter((p) => p.ticker !== ticker);
  } catch (e) { errorMsg.value = reportFriendlyError(e, '移除持仓失败，请稍后重试。'); }
}

onMounted(refresh);
watch(() => identity.sessionId, () => { void refresh(); });
</script>

<template>
  <section class="page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">持仓组合</h1>
        <span class="badge-count">{{ positions.length }} 持仓</span>
      </div>
      <div class="header-right">
        <button class="btn-secondary" @click="showImport = true">导入 CSV</button>
        <button class="btn-add" @click="addExpanded = !addExpanded">{{ addExpanded ? '收起' : '+ 新增持仓' }}</button>
        <ActionButton variant="ghost" :loading="loading" loading-text="刷新中..." aria-label="刷新持仓" @click="refresh">
          刷新
        </ActionButton>
      </div>
    </div>

    <!-- 汇总卡片 -->
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">持仓成本</div>
        <div class="summary-value">¥{{ fmt(totals.cost) }}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">当前市值</div>
        <div class="summary-value">{{ totals.value == null ? '行情不可用' : '¥' + fmt(totals.value) }}</div>
      </div>
      <div class="summary-card" :class="{ gain: (totals.pnl ?? 0) > 0, loss: (totals.pnl ?? 0) < 0 }">
        <div class="summary-label">总盈亏</div>
        <div class="summary-value">
          {{ totals.pnl == null ? '—' : (totals.pnl >= 0 ? '+' : '') + '¥' + fmt(totals.pnl) }}
          <span v-if="pnlPercent" class="pnl-pct">({{ totals.pnl! >= 0 ? '+' : '' }}{{ pnlPercent }}%)</span>
        </div>
      </div>
    </div>

    <section class="tool-panel" data-testid="portfolio-tools">
      <div class="tool-panel-head">
        <div>
          <p class="tool-kicker">PORTFOLIO TOOLS</p>
          <h2>组合工具</h2>
        </div>
        <span>风险透镜 / 组合优化 / 策略回测</span>
      </div>
      <div class="tool-grid">
        <article
          v-for="tool in portfolioTools"
          :key="tool.key"
          class="tool-card"
          :class="{ active: activeTool === tool.key }"
        >
          <strong>{{ tool.title }}</strong>
          <p>{{ tool.summary }}</p>
          <ActionButton size="sm" @click="openTool(tool.key)">{{ tool.action }}</ActionButton>
        </article>
      </div>
    </section>

    <!-- 添加持仓表单 -->
    <Transition name="slide-down">
      <div v-if="addExpanded" class="add-card">
        <div class="add-fields">
          <div class="field-wrap">
            <label class="field-label">股票代码 *</label>
            <input v-model="editTicker" placeholder="AAPL" class="input">
          </div>
          <div class="field-wrap">
            <label class="field-label">股数 *</label>
            <input v-model="editShares" placeholder="100" class="input" type="number">
          </div>
          <div class="field-wrap">
            <label class="field-label">成本价（可选）</label>
            <input v-model="editAvgCost" placeholder="182.50" class="input" type="number">
          </div>
          <div class="field-wrap">
            <label class="field-label">名称（可选）</label>
            <input v-model="editName" placeholder="苹果公司" class="input">
          </div>
        </div>
        <div class="add-actions">
          <ActionButton :loading="loading" loading-text="保存中..." @click="save">确认保存</ActionButton>
          <button class="btn-cancel" @click="addExpanded = false">取消</button>
        </div>
      </div>
    </Transition>

    <!-- 标签筛选 -->
    <div v-if="allTags.length" class="tag-bar">
      <span class="tag-bar-label">标签：</span>
      <button v-for="tag in allTags" :key="tag" class="tag-chip" :class="{ active: activeTag === tag }" @click="toggleTag(tag)">{{ tag }}</button>
      <button v-if="activeTag" class="tag-clear" @click="activeTag = null">✕ 清除</button>
    </div>

    <StatusBanner
      v-if="errorMsg"
      variant="error"
      :message="errorMsg"
      dismissible
      @dismiss="errorMsg = null"
    />

    <!-- 加载骨架屏 -->
    <SkeletonLoader v-if="loading && positions.length === 0" type="table" :rows="5" />

    <!-- 空态 -->
    <EmptyState
      v-else-if="!loading && positions.length === 0"
      title="还没有持仓记录"
      hint="在上方添加第一笔持仓，或通过「导入 CSV」批量导入。"
      action-label="手动添加"
      secondary-action-label="导入 CSV"
      @action="addExpanded = true"
      @secondary-action="showImport = true"
    />

    <!-- 持仓列表 -->
    <ul v-else class="positions">
      <li v-for="p in filteredPositions" :key="p.ticker" class="pos-card">
        <!-- 内联编辑 -->
        <template v-if="editingTicker === p.ticker">
          <div class="edit-header">
            <span class="pos-ticker">{{ p.ticker }}</span>
            <span class="edit-badge">编辑中</span>
          </div>
          <div class="edit-grid">
            <label class="edit-label">股数<input v-model="editForm.shares" type="number" class="input"></label>
            <label class="edit-label">成本价<input v-model="editForm.avgCost" type="number" class="input" placeholder="可选"></label>
            <label class="edit-label">名称<input v-model="editForm.name" class="input" placeholder="可选"></label>
            <label class="edit-label">标签（分号）<input v-model="editForm.tags" class="input" placeholder="科技;美股"></label>
            <label class="edit-label">行业<input v-model="editForm.sector" class="input" placeholder="科技/金融/消费"></label>
            <label class="edit-label">币种<input v-model="editForm.currency" class="input" placeholder="USD/CNY/HKD"></label>
            <label class="edit-label">开仓时间<input v-model="editForm.openedAt" type="date" class="input" placeholder="YYYY-MM-DD"></label>
          </div>
          <label class="edit-label full">备注<textarea v-model="editForm.note" class="input edit-note" rows="2" placeholder="可选" /></label>
          <div class="edit-actions">
          <ActionButton size="sm" :loading="loading" loading-text="保存中..." @click="saveEdit(p.ticker)">保存</ActionButton>
            <button class="btn-cancel" @click="cancelEdit">取消</button>
          </div>
        </template>

        <!-- 正常展示 -->
        <template v-else>
          <div class="pos-main">
            <div class="pos-info">
              <span class="pos-ticker">{{ p.ticker }}</span>
              <span v-if="p.name" class="pos-name">{{ p.name }}</span>
              <span v-for="tag in (p.tags || [])" :key="tag" class="wl-tag" :class="{ active: activeTag === tag }" @click="toggleTag(tag)">{{ tag }}</span>
            </div>
            <div class="pos-metrics">
              <div class="metric"><div class="metric-label">持仓股数</div><div class="metric-val">{{ p.shares }}</div></div>
              <div class="metric" v-if="p.avg_cost != null"><div class="metric-label">成本价</div><div class="metric-val">¥{{ p.avg_cost }}</div></div>
              <div class="metric"><div class="metric-label">当前市值</div><div class="metric-val" :class="{ na: p.market_value == null }">{{ p.market_value == null ? '不可用' : '¥' + fmt(p.market_value) }}</div></div>
              <div class="metric" v-if="p.sector"><div class="metric-label">行业</div><div class="metric-val">{{ p.sector }}</div></div>
              <div class="metric" v-if="p.currency"><div class="metric-label">币种</div><div class="metric-val">{{ p.currency }}</div></div>
              <div class="metric" v-if="p.opened_at"><div class="metric-label">开仓时间</div><div class="metric-val">{{ p.opened_at.slice(0, 10) }}</div></div>
            </div>
          </div>
          <div v-if="p.note" class="pos-note">{{ p.note }}</div>
          <div class="pos-actions">
            <button class="btn-edit" @click="startEdit(p)">编辑</button>
            <button class="btn-remove" @click="remove(p.ticker)">移除</button>
          </div>
        </template>
      </li>
    </ul>

    <!-- CSV 导入 Modal -->
    <Teleport to="body">
      <div v-if="showImport" class="modal-backdrop" @click.self="closeImport">
        <div class="modal">
          <div class="modal-head">
            <h2 class="modal-title">导入 CSV</h2>
            <button class="modal-close" @click="closeImport">✕</button>
          </div>
          <p class="modal-hint">格式：<code>ticker,shares,avg_cost,name,tags,note</code>（后四列可选，tags 用分号分隔）</p>
          <div class="file-row">
            <label class="file-label">选择文件<input ref="csvFile" type="file" accept=".csv,.txt" class="file-input" @change="onFileChange"></label>
            <span class="file-hint">或直接粘贴到下方</span>
          </div>
          <textarea v-model="csvText" class="csv-area" placeholder="AAPL,10,182.5,苹果,科技;美股&#10;TSLA,5,220" rows="6" />
          <ActionButton :disabled="!csvText.trim()" @click="parseCsv">解析预览</ActionButton>
          <div v-if="csvParsed" class="preview">
            <p class="preview-stat">共 {{ csvRows.length }} 行 — <span class="ok">{{ csvValidRows.length }} 可导入</span><span v-if="csvErrorRows.length" class="fail"> · {{ csvErrorRows.length }} 错误</span></p>
            <ul class="preview-list">
              <li v-for="(row, i) in csvRows" :key="i" :class="row.error ? 'row-err' : 'row-ok'">
                <span v-if="row.error">⚠ {{ row.error }}</span>
                <span v-else>✓ {{ row.ticker }} · {{ row.shares }} 股{{ row.avg_cost != null ? ` · 成本 ${row.avg_cost}` : '' }}</span>
              </li>
            </ul>
            <div class="modal-actions">
              <ActionButton :disabled="!csvValidRows.length" :loading="loading" loading-text="导入中..." @click="confirmImport">确认导入 {{ csvValidRows.length }} 条</ActionButton>
              <button class="btn-cancel" @click="closeImport">取消</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }

.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 24px; font-weight: 700; margin: 0; color: var(--fin-text); }
.badge-count { font-size: 12px; font-weight: 600; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 10px; border-radius: 20px; }
.header-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.btn-add { padding: 9px 18px; border: none; border-radius: 10px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-add:hover { opacity: 0.88; }
.btn-secondary { padding: 9px 16px; border: 1.5px solid var(--fin-primary); border-radius: 10px; background: transparent; color: var(--fin-primary); font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-secondary:hover { background: var(--fin-primary-soft); }
.btn-ghost { padding: 9px 12px; border: 1.5px solid var(--fin-border); border-radius: 10px; background: var(--fin-card); cursor: pointer; font-size: 16px; color: var(--fin-muted); }
.btn-ghost:hover { border-color: var(--fin-primary); color: var(--fin-primary); }

.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 汇总 */
.summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.summary-card { padding: 20px; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 12px; }
.summary-card.gain { border-color: #27ae60; background: #f0faf4; }
.summary-card.loss { border-color: #e74c3c; background: #fff4f4; }
.summary-label { font-size: 12px; color: var(--fin-muted); margin-bottom: 8px; font-weight: 600; }
.summary-value { font-size: 22px; font-weight: 700; color: var(--fin-text); }
.summary-card.gain .summary-value { color: #27ae60; }
.summary-card.loss .summary-value { color: #e74c3c; }
.pnl-pct { font-size: 14px; font-weight: 600; }

.tool-panel { padding: 18px; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 12px; }
.tool-panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.tool-panel-head h2 { margin: 0; color: var(--fin-text); font-size: 20px; }
.tool-panel-head span,
.tool-card p { color: var(--fin-muted); }
.tool-kicker { margin: 0 0 4px; color: var(--fin-primary); font-family: var(--fin-mono); font-size: 11px; font-weight: 900; letter-spacing: .14em; }
.tool-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.tool-card { border: 1.5px solid var(--fin-border); border-radius: 8px; padding: 16px; background: var(--fin-bg); }
.tool-card.active { border-color: var(--fin-primary); background: var(--fin-primary-soft); }
.tool-card strong { color: var(--fin-text); font-size: 16px; }
.tool-card p { min-height: 44px; margin: 8px 0 14px; line-height: 1.6; }
.tool-card button { border: 0; border-radius: 8px; padding: 9px 12px; background: var(--fin-primary); color: #fff; cursor: pointer; font-weight: 700; }

/* 表单 */
.add-card { background: var(--fin-card); border: 2px solid var(--fin-primary); border-radius: 14px; padding: 20px 24px; }
.add-fields { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }
.field-wrap { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--fin-muted); }
.input { padding: 10px 12px; border: 1.5px solid var(--fin-border); border-radius: 8px; font-size: 14px; background: var(--fin-bg); color: var(--fin-text); transition: border-color 0.15s; width: 100%; box-sizing: border-box; }
.input:focus { outline: none; border-color: var(--fin-primary); }
.add-actions { display: flex; gap: 10px; }
.btn-primary { padding: 10px 20px; border: none; border-radius: 8px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-primary.small { padding: 8px 16px; font-size: 13px; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary:hover:not(:disabled) { opacity: 0.88; }
.btn-cancel { padding: 10px 20px; border: 1.5px solid var(--fin-border); border-radius: 8px; background: transparent; font-size: 14px; color: var(--fin-muted); cursor: pointer; }

/* 标签 */
.tag-bar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.tag-bar-label { font-size: 12px; color: var(--fin-muted); font-weight: 600; }
.tag-chip { padding: 4px 12px; border: 1.5px solid var(--fin-border); border-radius: 20px; background: transparent; font-size: 12px; cursor: pointer; color: var(--fin-text-2); transition: all 0.15s; }
.tag-chip.active { background: var(--fin-primary); border-color: var(--fin-primary); color: #fff; font-weight: 600; }
.tag-clear { padding: 4px 10px; border: none; border-radius: 20px; background: transparent; font-size: 12px; cursor: pointer; color: var(--fin-danger); }
.wl-tag { font-size: 11px; padding: 2px 8px; border-radius: 20px; background: var(--fin-primary-soft); color: var(--fin-primary); font-weight: 600; cursor: pointer; }
.wl-tag.active { background: var(--fin-primary); color: #fff; }

/* 持仓列表 */
.positions { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 10px; }
.pos-card { padding: 20px; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 14px; transition: border-color 0.15s; }
.pos-card:hover { border-color: var(--fin-primary); }
.pos-main { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.pos-info { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; flex: 0 0 auto; }
.pos-ticker { font-size: 18px; font-weight: 700; color: var(--fin-text); }
.pos-name { font-size: 13px; color: var(--fin-muted); }
.pos-metrics { display: flex; gap: 20px; flex: 1; flex-wrap: wrap; }
.metric { display: flex; flex-direction: column; gap: 3px; }
.metric-label { font-size: 11px; color: var(--fin-muted); font-weight: 600; }
.metric-val { font-size: 15px; font-weight: 600; color: var(--fin-text); }
.metric-val.na { color: var(--fin-muted); }
.pos-note { font-size: 12px; color: var(--fin-text-2); margin-top: 8px; padding: 8px 12px; background: var(--fin-bg); border-radius: 6px; }
.pos-actions { display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end; }
.btn-edit { padding: 6px 14px; border: 1.5px solid var(--fin-primary); border-radius: 8px; background: transparent; color: var(--fin-primary); font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-edit:hover { background: var(--fin-primary); color: #fff; }
.btn-remove { padding: 6px 14px; border: 1.5px solid var(--fin-border); border-radius: 8px; background: transparent; color: var(--fin-muted); font-size: 13px; cursor: pointer; }
.btn-remove:hover { border-color: var(--fin-danger); color: var(--fin-danger); }

/* 内联编辑 */
.edit-header { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.edit-badge { font-size: 11px; padding: 2px 8px; background: var(--fin-primary-soft); color: var(--fin-primary); border-radius: 20px; font-weight: 600; }
.edit-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 10px; }
.edit-label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--fin-muted); }
.edit-label.full { margin-bottom: 10px; }
.edit-note { resize: vertical; font-family: inherit; }
.edit-actions { display: flex; gap: 8px; margin-top: 12px; }

/* 动画 */
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.25s ease; overflow: hidden; }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; max-height: 0; transform: translateY(-8px); }
.slide-down-enter-to, .slide-down-leave-from { opacity: 1; max-height: 400px; transform: translateY(0); }

/* Modal */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
.modal { background: var(--fin-bg, #f7f6f4); border-radius: 8px; padding: 22px; width: min(560px, 100%); max-height: min(88vh, 720px); overflow-y: auto; box-shadow: 0 8px 40px rgba(0,0,0,0.15); }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-title { font-size: 18px; font-weight: 700; margin: 0; }
.modal-close { width: 34px; height: 34px; border: 1px solid var(--fin-border); border-radius: 8px; background: var(--fin-card); font-size: 18px; cursor: pointer; color: var(--fin-muted); }
.modal-hint { font-size: 12px; color: var(--fin-muted); margin: 0 0 14px; }
.file-row { display: flex; gap: 10px; align-items: center; margin-bottom: 12px; }
.file-label { padding: 8px 14px; border: 1.5px solid var(--fin-border); border-radius: 8px; font-size: 13px; cursor: pointer; background: var(--fin-card); }
.file-input { display: none; }
.file-hint { font-size: 12px; color: var(--fin-muted); }
.csv-area { width: 100%; box-sizing: border-box; padding: 10px; border: 1.5px solid var(--fin-border); border-radius: 8px; font-size: 13px; font-family: monospace; background: var(--fin-card); resize: vertical; margin-bottom: 14px; }
.preview { margin-top: 16px; }
.preview-stat { font-size: 13px; margin: 0 0 10px; }
.ok { color: var(--fin-success, #2d7d46); }
.fail { color: var(--fin-danger); }
.preview-list { list-style: none; padding: 0; margin: 0 0 16px; max-height: 180px; overflow-y: auto; }
.preview-list li { font-size: 12px; padding: 4px 8px; border-radius: 6px; margin-bottom: 4px; }
.row-ok { background: #f0faf4; color: #2d7d46; }
.row-err { background: #fff4f4; color: var(--fin-danger); }
.modal-actions { display: flex; gap: 10px; }

@media (max-width: 768px) {
  .summary-grid, .tool-grid { grid-template-columns: 1fr; }
  .tool-panel-head { display: grid; }
  .add-fields { grid-template-columns: 1fr 1fr; }
  .edit-grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 480px) {
  .add-fields { grid-template-columns: 1fr; }
  .edit-grid { grid-template-columns: 1fr; }
}
</style>
