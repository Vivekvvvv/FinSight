<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { WatchlistItem } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import SkeletonLoader from '@/components/SkeletonLoader.vue';

const identity = useIdentityStore();
const router = useRouter();

const items = ref<WatchlistItem[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const newTicker = ref('');
const newName = ref('');
const newTags = ref('');
const newGroup = ref('');
const newPriority = ref('');
const newWatchReason = ref('');
const addExpanded = ref(false);

const searchQ = ref('');
const sortBy = ref<'time' | 'ticker' | 'name'>('time');

const SORT_OPTIONS = [
  { value: 'time', label: '按添加时间' },
  { value: 'ticker', label: 'Ticker A-Z' },
  { value: 'name', label: '名称 A-Z' },
] as const;

const displayedItems = computed(() => {
  const q = searchQ.value.trim().toLowerCase();
  const filtered = q
    ? items.value.filter(
        (it) => it.ticker.toLowerCase().includes(q) || (it.name || '').toLowerCase().includes(q),
      )
    : [...items.value];
  if (sortBy.value === 'ticker') return [...filtered].sort((a, b) => a.ticker.localeCompare(b.ticker));
  if (sortBy.value === 'name') return [...filtered].sort((a, b) => (a.name || a.ticker).localeCompare(b.name || b.ticker));
  return filtered;
});

function goToDashboard(ticker: string) {
  void router.push(`/dashboard/${encodeURIComponent(ticker)}`);
}

async function refresh(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.listWatchlist(identity.userId);
    items.value = resp.items || [];
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function add(): Promise<void> {
  const ticker = newTicker.value.trim().toUpperCase();
  if (!ticker) return;
  const tags = newTags.value.split(',').map((t) => t.trim()).filter(Boolean);
  const priority = newPriority.value.trim() ? Number(newPriority.value) : undefined;
  try {
    await apiClient.addWatchlist({
      user_id: identity.userId,
      ticker,
      name: newName.value.trim() || undefined,
      tags: tags.length ? tags : undefined,
      group: newGroup.value.trim() || undefined,
      priority: priority,
      watch_reason: newWatchReason.value.trim() || undefined,
    });
    newTicker.value = '';
    newName.value = '';
    newTags.value = '';
    newGroup.value = '';
    newPriority.value = '';
    newWatchReason.value = '';
    addExpanded.value = false;
    await refresh();
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

async function remove(ticker: string): Promise<void> {
  try {
    await apiClient.removeWatchlist({ user_id: identity.userId, ticker });
    items.value = items.value.filter((i) => i.ticker !== ticker);
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(refresh);
watch(() => identity.userId, () => { void refresh(); });
</script>

<template>
  <section class="page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">自选清单</h1>
        <span class="badge-count">{{ items.length }} 支</span>
      </div>
      <div class="header-right">
        <button class="btn-add" @click="addExpanded = !addExpanded">
          {{ addExpanded ? '收起' : '+ 添加标的' }}
        </button>
        <button class="btn-ghost" :disabled="loading" @click="refresh">
          <span :class="{ spinning: loading }">↻</span>
        </button>
      </div>
    </div>

    <!-- 添加表单 -->
    <Transition name="slide-down">
      <div v-if="addExpanded" class="add-card">
        <div class="add-fields">
          <div class="field-wrap">
            <label class="field-label">股票代码 *</label>
            <input
              v-model="newTicker"
              placeholder="AAPL"
              class="input"
              @keyup.enter="add"
            >
          </div>
          <div class="field-wrap">
            <label class="field-label">名称（可选）</label>
            <input v-model="newName" placeholder="苹果公司" class="input">
          </div>
          <div class="field-wrap">
            <label class="field-label">标签（逗号分隔）</label>
            <input v-model="newTags" placeholder="科技,美股" class="input">
          </div>
          <div class="field-wrap">
            <label class="field-label">分组（可选）</label>
            <input v-model="newGroup" placeholder="科技股/港股/重点关注" class="input">
          </div>
          <div class="field-wrap">
            <label class="field-label">优先级（可选）</label>
            <input v-model="newPriority" placeholder="1-5，数字越大优先级越高" class="input" type="number" min="1" max="5">
          </div>
          <div class="field-wrap">
            <label class="field-label">关注原因（可选）</label>
            <textarea v-model="newWatchReason" placeholder="记录为什么关注这只股票..." class="input" rows="2"></textarea>
          </div>
        </div>
        <div class="add-actions">
          <button class="btn-primary" @click="add">确认添加</button>
          <button class="btn-cancel" @click="addExpanded = false">取消</button>
        </div>
      </div>
    </Transition>

    <!-- 搜索 + 排序 -->
    <div class="toolbar">
      <div class="search-wrap">
        <span class="search-icon">⌕</span>
        <input v-model="searchQ" class="search-input" placeholder="搜索代码或名称…">
      </div>
      <div class="sort-tabs">
        <button
          v-for="opt in SORT_OPTIONS"
          :key="opt.value"
          class="sort-tab"
          :class="{ active: sortBy === opt.value }"
          @click="sortBy = opt.value"
        >{{ opt.label }}</button>
      </div>
    </div>

    <!-- 错误 -->
    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 加载骨架屏 -->
    <SkeletonLoader v-if="loading && items.length === 0" type="list" :rows="6" />

    <!-- 空态 -->
    <div v-else-if="!loading && items.length === 0" class="empty-state">
      <div class="empty-icon">📋</div>
      <div class="empty-title">还没有自选标的</div>
      <div class="empty-hint">点击右上角「+ 添加标的」开始关注你感兴趣的股票</div>
      <button class="btn-primary" @click="addExpanded = true">立即添加</button>
    </div>

    <div v-else-if="displayedItems.length === 0" class="empty-state">
      <div class="empty-icon">🔍</div>
      <div class="empty-title">没有匹配「{{ searchQ }}」的结果</div>
    </div>

    <!-- 列表 -->
    <ul v-else class="watchlist">
      <li
        v-for="it in displayedItems"
        :key="it.ticker"
        class="wl-item"
        @click="goToDashboard(it.ticker)"
      >
        <div class="wl-left">
          <span class="wl-ticker">{{ it.ticker }}</span>
          <span v-if="it.name" class="wl-name">{{ it.name }}</span>
          <span v-for="t in it.tags" :key="t" class="wl-tag">{{ t }}</span>
          <span v-if="it.group" class="wl-group">📁 {{ it.group }}</span>
          <span v-if="it.priority && it.priority >= 4" class="wl-priority">⭐ P{{ it.priority }}</span>
        </div>
        <div class="wl-meta" v-if="it.watch_reason">
          <div class="wl-reason">💡 {{ it.watch_reason }}</div>
        </div>
        <div class="wl-right" @click.stop>
          <button class="btn-analyze" @click="goToDashboard(it.ticker)">分析 →</button>
          <button class="btn-remove" @click="remove(it.ticker)">✕</button>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 24px; font-weight: 700; margin: 0; color: var(--fin-text); }
.badge-count {
  font-size: 12px;
  font-weight: 600;
  color: var(--fin-primary);
  background: var(--fin-primary-soft);
  padding: 3px 10px;
  border-radius: 20px;
}

.header-right { display: flex; gap: 8px; align-items: center; }

.btn-add {
  padding: 9px 18px;
  border: none;
  border-radius: 10px;
  background: var(--fin-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-add:hover { opacity: 0.88; }

.btn-ghost {
  padding: 9px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 10px;
  background: var(--fin-card);
  cursor: pointer;
  font-size: 16px;
  color: var(--fin-muted);
  transition: all 0.15s;
}
.btn-ghost:hover { border-color: var(--fin-primary); color: var(--fin-primary); }

.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 添加卡片 */
.add-card {
  background: var(--fin-card);
  border: 2px solid var(--fin-primary);
  border-radius: 14px;
  padding: 20px 24px;
}

.add-fields {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  margin-bottom: 16px;
}

.field-wrap { display: flex; flex-direction: column; gap: 5px; }
.field-label { font-size: 12px; font-weight: 600; color: var(--fin-muted); }
.input {
  padding: 10px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  font-size: 14px;
  background: var(--fin-bg);
  color: var(--fin-text);
  transition: border-color 0.15s;
}
.input:focus { outline: none; border-color: var(--fin-primary); }

.add-actions { display: flex; gap: 10px; }

.btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: var(--fin-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-primary:hover { opacity: 0.88; }

.btn-cancel {
  padding: 10px 20px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: transparent;
  font-size: 14px;
  color: var(--fin-muted);
  cursor: pointer;
}

/* 工具栏 */
.toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }

.search-wrap {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 10px;
}
.search-icon { font-size: 16px; color: var(--fin-muted); }
.search-input { flex: 1; border: none; outline: none; font-size: 14px; background: transparent; color: var(--fin-text); }

.sort-tabs { display: flex; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 10px; overflow: hidden; }
.sort-tab { padding: 9px 14px; border: none; background: transparent; font-size: 13px; cursor: pointer; color: var(--fin-muted); transition: all 0.15s; }
.sort-tab.active { background: var(--fin-primary); color: #fff; font-weight: 600; }

/* 状态 */
.error-banner { padding: 12px 16px; background: #fff1f0; border: 1.5px solid #ffccc7; border-radius: 10px; color: #cf1322; font-size: 14px; }

.loading-state { display: flex; gap: 10px; align-items: center; justify-content: center; padding: 48px; color: var(--fin-muted); font-size: 14px; }
.loader { width: 20px; height: 20px; border: 2px solid var(--fin-border); border-top-color: var(--fin-primary); border-radius: 50%; animation: spin 0.8s linear infinite; }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 60px 20px; background: var(--fin-card); border: 2px dashed var(--fin-border); border-radius: 16px; text-align: center; }
.empty-icon { font-size: 40px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--fin-text); }
.empty-hint { font-size: 13px; color: var(--fin-muted); max-width: 320px; line-height: 1.6; }

/* 列表 */
.watchlist { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }

.wl-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.wl-item:hover { border-color: var(--fin-primary); transform: translateX(4px); box-shadow: 0 2px 12px rgba(204, 120, 92, 0.1); }

.wl-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; flex: 1; }
.wl-ticker { font-size: 16px; font-weight: 700; color: var(--fin-text); }
.wl-name { font-size: 13px; color: var(--fin-muted); }
.wl-tag { font-size: 11px; padding: 2px 8px; border-radius: 20px; background: var(--fin-primary-soft); color: var(--fin-primary); font-weight: 600; }
.wl-group { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: #e6f4ff; color: #0958d9; font-weight: 600; }
.wl-priority { font-size: 12px; padding: 2px 8px; border-radius: 6px; background: #fff7e6; color: #d46b08; font-weight: 600; }

.wl-meta { flex: 1 100%; padding-top: 8px; }
.wl-reason { font-size: 12px; color: var(--fin-muted); line-height: 1.5; padding-left: 4px; border-left: 2px solid var(--fin-primary-soft); }

.wl-right { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }

.btn-analyze {
  padding: 6px 14px;
  border: 1.5px solid var(--fin-primary);
  border-radius: 8px;
  background: transparent;
  color: var(--fin-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-analyze:hover { background: var(--fin-primary); color: #fff; }

.btn-remove {
  padding: 6px 10px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: transparent;
  color: var(--fin-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-remove:hover { border-color: var(--fin-danger); color: var(--fin-danger); }

/* 动画 */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  max-height: 0;
  transform: translateY(-8px);
}
.slide-down-enter-to,
.slide-down-leave-from {
  opacity: 1;
  max-height: 300px;
  transform: translateY(0);
}

@media (max-width: 640px) {
  .add-fields { grid-template-columns: 1fr; }
  .page-header { flex-wrap: wrap; }
}
</style>
