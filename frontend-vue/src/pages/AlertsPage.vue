<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { apiClient } from '@/api/client';
import type { SubscriptionItem, AlertEvent } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';

const identity = useIdentityStore();
const email = computed({
  get: () => identity.email,
  set: (value: string) => identity.setEmail(value),
});
const subs = ref<SubscriptionItem[]>([]);
const events = ref<AlertEvent[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

function fmtDate(v?: string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : d.toLocaleString('zh-CN', { hour12: false });
}

async function refresh(): Promise<void> {
  if (!email.value.trim()) { errorMsg.value = '请先填写订阅邮箱'; return; }
  loading.value = true; errorMsg.value = null;
  try {
    const [subResp, feedResp] = await Promise.all([
      apiClient.listSubscriptions(email.value.trim()),
      apiClient.alertsFeed(email.value.trim()),
    ]);
    subs.value = subResp.subscriptions || [];
    events.value = feedResp.events || [];
  } catch (e) { errorMsg.value = e instanceof Error ? e.message : String(e); } finally { loading.value = false; }
}

async function toggle(sub: SubscriptionItem): Promise<void> {
  const target = sub.disabled;
  try {
    await apiClient.toggleSubscription({ email: sub.email, ticker: sub.ticker, enabled: target });
    sub.disabled = !target;
  } catch (e) { errorMsg.value = e instanceof Error ? e.message : String(e); }
}

async function remove(sub: SubscriptionItem): Promise<void> {
  if (!window.confirm(`取消 ${sub.ticker} 的提醒?`)) return;
  try {
    await apiClient.unsubscribe({ email: sub.email, ticker: sub.ticker });
    subs.value = subs.value.filter((s) => s.ticker !== sub.ticker);
  } catch (e) { errorMsg.value = e instanceof Error ? e.message : String(e); }
}

const showNew = ref(false);
const newTicker = ref('');
const newMode = ref('price_change');
const newThreshold = ref('high');
const newError = ref<string | null>(null);
const saving = ref(false);

const ALERT_MODES = [
  { value: 'price_change', label: '价格变动', icon: '📈' },
  { value: 'news', label: '新闻提醒', icon: '📰' },
  { value: 'risk', label: '风险预警', icon: '⚠️' },
];

const RISK_THRESHOLDS = [
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
];

async function saveNew(): Promise<void> {
  const ticker = newTicker.value.trim().toUpperCase();
  if (!ticker) { newError.value = '请输入股票代码'; return; }
  if (!email.value.trim()) { newError.value = '请先在邮箱栏填写邮箱'; return; }
  saving.value = true; newError.value = null;
  try {
    await apiClient.subscribe({ email: email.value.trim(), ticker, alert_mode: newMode.value, risk_threshold: newThreshold.value });
    showNew.value = false; newTicker.value = ''; newMode.value = 'price_change'; newThreshold.value = 'high';
    await refresh();
  } catch (e) { newError.value = e instanceof Error ? e.message : String(e); } finally { saving.value = false; }
}

function closeNew() { showNew.value = false; newTicker.value = ''; newError.value = null; }

onMounted(() => { if (email.value.trim()) refresh(); });
watch(() => identity.ready, (ready) => { if (ready && email.value.trim()) void refresh(); }, { immediate: true });
</script>

<template>
  <section class="page">
    <!-- 页头 -->
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">提醒中心</h1>
        <span class="badge-count">{{ subs.length }} 条订阅</span>
      </div>
      <div class="header-right">
        <button class="btn-add" @click="showNew = true">+ 新建提醒</button>
        <button class="btn-ghost" :disabled="loading" @click="refresh">
          <span :class="{ spinning: loading }">↻</span>
        </button>
      </div>
    </div>

    <!-- 邮箱行 -->
    <div class="email-card">
      <div class="email-icon">✉️</div>
      <div class="email-info">
        <div class="email-label">订阅邮箱</div>
        <div class="email-desc">提醒会发送到此邮箱，也用于加载您的订阅列表</div>
      </div>
      <input v-model="email" placeholder="your@email.com" class="email-input" @keyup.enter="refresh">
      <button class="btn-load" @click="refresh">加载</button>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 订阅列表 -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">当前订阅</h2>
        <span class="section-count">{{ subs.length }}</span>
      </div>

      <div v-if="loading" class="loading-state">
        <span class="loader" /><span>加载中…</span>
      </div>

      <div v-else-if="subs.length === 0" class="empty-state">
        <div class="empty-icon">🔔</div>
        <div class="empty-title">还没有提醒订阅</div>
        <div class="empty-hint">点击「新建提醒」选择股票和触发条件，异常时将第一时间通知你</div>
        <button class="btn-primary" @click="showNew = true">创建第一个提醒</button>
      </div>

      <div v-else class="sub-list">
        <div v-for="s in subs" :key="s.ticker" class="sub-card" :class="{ disabled: s.disabled }">
          <div class="sub-main">
            <div class="sub-ticker">{{ s.ticker }}</div>
            <div class="sub-mode">{{ (s.alert_types || []).join('/') || s.alert_mode || '—' }}</div>
            <div class="sub-threshold">风险: {{ s.risk_threshold || '—' }}</div>
            <span class="sub-status" :class="{ off: s.disabled }">{{ s.disabled ? '已禁用' : '启用中' }}</span>
          </div>
          <div class="sub-meta">上次触发: {{ fmtDate(s.last_triggered_at) }}</div>
          <div class="sub-actions">
            <button class="btn-toggle" @click="toggle(s)">{{ s.disabled ? '启用' : '暂停' }}</button>
            <button class="btn-del" @click="remove(s)">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 触发历史 -->
    <div class="section">
      <div class="section-header">
        <h2 class="section-title">触发历史</h2>
        <span class="section-count">{{ events.length }}</span>
      </div>

      <div v-if="events.length === 0" class="empty-state compact">
        <div class="empty-icon">📭</div>
        <div class="empty-title">暂无告警记录</div>
      </div>

      <ul v-else class="event-list">
        <li v-for="ev in events" :key="ev.id" class="event-item">
          <span class="event-ticker">{{ ev.ticker }}</span>
          <span class="event-title">{{ ev.title }}</span>
          <span class="event-time">{{ fmtDate(ev.triggered_at) }}</span>
        </li>
      </ul>
    </div>

    <!-- 新建提醒 Modal -->
    <Teleport to="body">
      <div v-if="showNew" class="modal-backdrop" @click.self="closeNew">
        <div class="modal">
          <div class="modal-head">
            <h2 class="modal-title">新建提醒</h2>
            <button class="modal-close" @click="closeNew">✕</button>
          </div>

          <div class="form-row">
            <label class="form-label">股票代码</label>
            <input v-model="newTicker" placeholder="AAPL" class="input">
          </div>

          <div class="form-row">
            <label class="form-label">告警模式</label>
            <div class="mode-grid">
              <button
                v-for="m in ALERT_MODES"
                :key="m.value"
                class="mode-btn"
                :class="{ active: newMode === m.value }"
                @click="newMode = m.value"
              >
                <span class="mode-icon">{{ m.icon }}</span>
                <span class="mode-label">{{ m.label }}</span>
              </button>
            </div>
          </div>

          <div class="form-row">
            <label class="form-label">风险级别</label>
            <div class="threshold-group">
              <button
                v-for="r in RISK_THRESHOLDS"
                :key="r.value"
                class="threshold-btn"
                :class="{ active: newThreshold === r.value }"
                @click="newThreshold = r.value"
              >{{ r.label }}</button>
            </div>
          </div>

          <div v-if="newError" class="error-banner">{{ newError }}</div>

          <div class="modal-actions">
            <button class="btn-primary" :disabled="saving" @click="saveNew">
              {{ saving ? '保存中…' : '创建提醒' }}
            </button>
            <button class="btn-cancel" @click="closeNew">取消</button>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: 20px; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 24px; font-weight: 700; margin: 0; }
.badge-count { font-size: 12px; font-weight: 600; color: var(--fin-primary); background: var(--fin-primary-soft); padding: 3px 10px; border-radius: 20px; }
.header-right { display: flex; gap: 8px; align-items: center; }
.btn-add { padding: 9px 18px; border: none; border-radius: 10px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-add:hover { opacity: 0.88; }
.btn-ghost { padding: 9px 12px; border: 1.5px solid var(--fin-border); border-radius: 10px; background: var(--fin-card); cursor: pointer; font-size: 16px; color: var(--fin-muted); }
.spinning { display: inline-block; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 邮箱卡片 */
.email-card { display: flex; align-items: center; gap: 14px; padding: 16px 20px; background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 14px; flex-wrap: wrap; }
.email-icon { font-size: 24px; }
.email-info { flex: 1; min-width: 120px; }
.email-label { font-size: 13px; font-weight: 700; color: var(--fin-text); }
.email-desc { font-size: 12px; color: var(--fin-muted); margin-top: 2px; }
.email-input { flex: 1; min-width: 200px; padding: 10px 14px; border: 1.5px solid var(--fin-border); border-radius: 8px; font-size: 14px; background: var(--fin-bg); color: var(--fin-text); }
.email-input:focus { outline: none; border-color: var(--fin-primary); }
.btn-load { padding: 10px 18px; border: none; border-radius: 8px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; }

.error-banner { padding: 12px 16px; background: #fff1f0; border: 1.5px solid #ffccc7; border-radius: 10px; color: #cf1322; font-size: 14px; }

/* 区块 */
.section { background: var(--fin-card); border: 1.5px solid var(--fin-border); border-radius: 16px; padding: 20px; }
.section-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.section-title { font-size: 16px; font-weight: 700; margin: 0; }
.section-count { font-size: 12px; color: var(--fin-muted); background: var(--fin-bg); padding: 2px 8px; border-radius: 12px; }

.loading-state { display: flex; gap: 10px; align-items: center; justify-content: center; padding: 32px; color: var(--fin-muted); }
.loader { width: 18px; height: 18px; border: 2px solid var(--fin-border); border-top-color: var(--fin-primary); border-radius: 50%; animation: spin 0.8s linear infinite; }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 40px 20px; text-align: center; }
.empty-state.compact { padding: 24px; }
.empty-icon { font-size: 36px; }
.empty-title { font-size: 15px; font-weight: 600; color: var(--fin-text); }
.empty-hint { font-size: 13px; color: var(--fin-muted); max-width: 280px; line-height: 1.6; }
.btn-primary { padding: 10px 20px; border: none; border-radius: 8px; background: var(--fin-primary); color: #fff; font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* 订阅卡片 */
.sub-list { display: flex; flex-direction: column; gap: 10px; }
.sub-card { padding: 16px; background: var(--fin-bg); border: 1.5px solid var(--fin-border); border-radius: 12px; transition: border-color 0.15s; }
.sub-card:hover { border-color: var(--fin-primary); }
.sub-card.disabled { opacity: 0.6; }
.sub-main { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-bottom: 6px; }
.sub-ticker { font-size: 16px; font-weight: 700; color: var(--fin-text); }
.sub-mode { font-size: 13px; color: var(--fin-text-2); }
.sub-threshold { font-size: 12px; color: var(--fin-muted); }
.sub-status { font-size: 11px; padding: 2px 8px; border-radius: 20px; background: #e6f4ec; color: #2d7d46; font-weight: 600; }
.sub-status.off { background: #f3eee3; color: var(--fin-muted); }
.sub-meta { font-size: 12px; color: var(--fin-muted); margin-bottom: 10px; }
.sub-actions { display: flex; gap: 8px; }
.btn-toggle { padding: 5px 12px; border: 1.5px solid var(--fin-primary); border-radius: 6px; background: transparent; color: var(--fin-primary); font-size: 12px; font-weight: 600; cursor: pointer; }
.btn-del { padding: 5px 12px; border: 1.5px solid var(--fin-border); border-radius: 6px; background: transparent; color: var(--fin-danger); font-size: 12px; cursor: pointer; }

/* 事件列表 */
.event-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.event-item { display: flex; gap: 12px; align-items: center; padding: 12px 16px; background: var(--fin-bg); border: 1.5px solid var(--fin-border); border-radius: 10px; }
.event-ticker { font-size: 14px; font-weight: 700; color: var(--fin-primary); min-width: 60px; }
.event-title { flex: 1; font-size: 13px; color: var(--fin-text); }
.event-time { font-size: 12px; color: var(--fin-muted); white-space: nowrap; }

/* Modal */
.modal-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--fin-bg); border-radius: 16px; padding: 28px; width: min(460px, 94vw); box-shadow: 0 8px 40px rgba(0,0,0,0.15); }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.modal-title { font-size: 18px; font-weight: 700; margin: 0; }
.modal-close { border: none; background: transparent; font-size: 20px; cursor: pointer; color: var(--fin-muted); }
.form-row { margin-bottom: 18px; }
.form-label { display: block; font-size: 12px; font-weight: 700; color: var(--fin-muted); margin-bottom: 8px; }
.input { width: 100%; box-sizing: border-box; padding: 11px 14px; border: 1.5px solid var(--fin-border); border-radius: 8px; font-size: 14px; background: var(--fin-card); }
.input:focus { outline: none; border-color: var(--fin-primary); }
.mode-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.mode-btn { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 8px; border: 1.5px solid var(--fin-border); border-radius: 10px; background: var(--fin-card); cursor: pointer; transition: all 0.15s; }
.mode-btn.active { border-color: var(--fin-primary); background: var(--fin-primary-soft); }
.mode-icon { font-size: 20px; }
.mode-label { font-size: 12px; font-weight: 600; color: var(--fin-text-2); }
.mode-btn.active .mode-label { color: var(--fin-primary); }
.threshold-group { display: flex; gap: 8px; }
.threshold-btn { flex: 1; padding: 10px; border: 1.5px solid var(--fin-border); border-radius: 8px; background: var(--fin-card); font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.15s; color: var(--fin-text-2); }
.threshold-btn.active { border-color: var(--fin-primary); background: var(--fin-primary); color: #fff; }
.modal-actions { display: flex; gap: 10px; margin-top: 24px; }
.btn-cancel { padding: 10px 20px; border: 1.5px solid var(--fin-border); border-radius: 8px; background: transparent; font-size: 14px; color: var(--fin-muted); cursor: pointer; }
</style>
