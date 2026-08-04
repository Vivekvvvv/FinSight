<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { API_BASE_URL } from '@/config/runtime';
import { apiClient } from '@/api/client';
import type { ResearchNote } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import ActionButton from '@/components/ActionButton.vue';
import EmptyState from '@/components/EmptyState.vue';
import LoadingState from '@/components/LoadingState.vue';
import MarkdownEditor from '@/components/MarkdownEditor.vue';
import StatusBanner from '@/components/StatusBanner.vue';
import { reportFriendlyError } from '@/utils/error';

const identity = useIdentityStore();
const route = useRoute();
const router = useRouter();

const notes = ref<ResearchNote[]>([]);
const selected = ref<ResearchNote | null>(null);
const loading = ref(false);
const saving = ref(false);
const uploading = ref(false);
const errorMsg = ref<string | null>(null);
const successMsg = ref<string | null>(null);

const query = ref('');
const tickerFilter = ref(String(route.query.ticker || ''));

const title = ref('');
const ticker = ref('');
const tagsInput = ref('');
const content = ref('');

const filteredNotes = computed(() => notes.value);

function fmtDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString('zh-CN', { hour12: false, month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function parseTags(): string[] {
  return tagsInput.value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeImageUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('/')) return `${API_BASE_URL}${url}`;
  return url;
}

function setForm(note: ResearchNote | null): void {
  selected.value = note;
  title.value = note?.title || '';
  ticker.value = note?.ticker || '';
  tagsInput.value = (note?.tags || []).join(', ');
  content.value = note?.content || '';
}

let refreshSeq = 0;

async function refresh(): Promise<void> {
  const seq = ++refreshSeq;
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.listNotes(
      identity.sessionId,
      identity.userId,
      tickerFilter.value.trim() || undefined,
      query.value.trim() || undefined,
    );
    if (seq !== refreshSeq) return;
    notes.value = resp.notes || [];
    if (selected.value) {
      const latest = notes.value.find((item) => item.note_id === selected.value?.note_id);
      if (latest) selected.value = latest;
    }
  } catch (error) {
    if (seq !== refreshSeq) return;
    errorMsg.value = reportFriendlyError(error, '笔记列表加载失败，请刷新重试。');
  } finally {
    if (seq === refreshSeq) loading.value = false;
  }
}

function createNew(): void {
  setForm(null);
  successMsg.value = null;
  errorMsg.value = null;
}

function openNote(note: ResearchNote): void {
  setForm(note);
  successMsg.value = null;
  errorMsg.value = null;
}

async function saveNote(): Promise<ResearchNote | null> {
  const normalizedTitle = title.value.trim();
  if (!normalizedTitle) {
    errorMsg.value = '标题不能为空';
    return null;
  }

  saving.value = true;
  errorMsg.value = null;
  successMsg.value = null;
  try {
    if (selected.value) {
      const resp = await apiClient.updateNote(selected.value.note_id, {
        title: normalizedTitle,
        content: content.value,
        ticker: ticker.value.trim().toUpperCase() || null,
        tags: parseTags(),
      });
      if (!resp.success) throw new Error(resp.error || '保存失败');
      await refresh();
      const updated = notes.value.find((item) => item.note_id === selected.value?.note_id) || selected.value;
      setForm(updated);
      successMsg.value = '笔记已保存';
      return updated;
    }

    const resp = await apiClient.createNote({
      session_id: identity.sessionId,
      user_id: identity.userId,
      title: normalizedTitle,
      content: content.value,
      ticker: ticker.value.trim().toUpperCase() || null,
      tags: parseTags(),
    });
    if (!resp.success || !resp.note_id) throw new Error(resp.error || '创建失败');
    await refresh();
    const created = notes.value.find((item) => item.note_id === resp.note_id) || null;
    setForm(created);
    successMsg.value = '笔记已创建';
    return created;
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '笔记保存失败，请稍后重试。');
    return null;
  } finally {
    saving.value = false;
  }
}

async function deleteSelected(): Promise<void> {
  if (!selected.value) return;
  const noteId = selected.value.note_id;
  saving.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.deleteNote(noteId);
    if (!resp.success) throw new Error(resp.error || '删除失败');
    createNew();
    await refresh();
    successMsg.value = '笔记已删除';
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '笔记删除失败，请稍后重试。');
  } finally {
    saving.value = false;
  }
}

async function handleImageUpload(file: File): Promise<void> {
  let note = selected.value;
  if (!note) {
    note = await saveNote();
    if (!note) return;
  }

  uploading.value = true;
  errorMsg.value = null;
  try {
    const resp = await apiClient.uploadNoteImage(note.note_id, file);
    if (!resp.success || !resp.url) throw new Error(resp.error || '图片上传失败');
    const imageUrl = normalizeImageUrl(resp.url);
    const markdown = `\n![${file.name}](${imageUrl})\n`;
    content.value = `${content.value}${markdown}`;
    await saveNote();
    successMsg.value = '图片已上传并插入笔记';
  } catch (error) {
    errorMsg.value = reportFriendlyError(error, '图片上传失败，请稍后重试。');
  } finally {
    uploading.value = false;
  }
}

function goDashboard(): void {
  const symbol = ticker.value.trim().toUpperCase();
  if (symbol) void router.push(`/dossier/${encodeURIComponent(symbol)}`);
}

onMounted(refresh);
watch(() => identity.sessionId, () => { void refresh(); });
</script>

<template>
  <section class="notes-page">
    <header class="hero">
      <div>
        <p class="eyebrow">
          Research Notebook
        </p>
        <h1>研究笔记</h1>
        <p class="subtitle">
          把报告假设、事件观察和人工判断沉淀下来，避免研究过程只停留在一次性输出。
        </p>
      </div>
      <div class="hero-actions">
        <ActionButton
          variant="ghost"
          :loading="loading"
          loading-text="刷新中..."
          @click="refresh"
        >
          刷新
        </ActionButton>
        <ActionButton @click="createNew">
          新建笔记
        </ActionButton>
      </div>
    </header>

    <StatusBanner
      v-if="errorMsg"
      variant="error"
      :message="errorMsg"
      dismissible
      @dismiss="errorMsg = null"
    />
    <StatusBanner
      v-if="successMsg"
      variant="success"
      :message="successMsg"
      dismissible
      @dismiss="successMsg = null"
    />

    <div class="workspace">
      <aside class="notes-list">
        <div class="filters">
          <input
            v-model="query"
            class="input"
            placeholder="搜索标题或正文…"
            @keyup.enter="refresh"
          >
          <input
            v-model="tickerFilter"
            class="input"
            placeholder="按 ticker 筛选，如 AAPL"
            @keyup.enter="refresh"
          >
          <ActionButton
            variant="secondary"
            :loading="loading"
            loading-text="筛选中..."
            @click="refresh"
          >
            应用筛选
          </ActionButton>
        </div>

        <LoadingState
          v-if="loading && notes.length === 0"
          label="正在加载研究笔记..."
        />
        <EmptyState
          v-else-if="!loading && filteredNotes.length === 0"
          title="暂无研究笔记"
          hint="先写下一个研究假设，后续报告和标的证据可以沉淀到这里。"
          compact
        />
        <button
          v-for="note in filteredNotes"
          v-else
          :key="note.note_id"
          class="note-card"
          :class="{ active: selected?.note_id === note.note_id }"
          @click="openNote(note)"
        >
          <div class="note-card-title">
            {{ note.title }}
          </div>
          <div class="note-card-meta">
            <span
              v-if="note.ticker"
              class="ticker"
            >{{ note.ticker }}</span>
            <span>{{ fmtDate(note.updated_at) }}</span>
          </div>
          <div
            v-if="note.tags.length"
            class="tag-row"
          >
            <span
              v-for="tag in note.tags.slice(0, 3)"
              :key="tag"
              class="tag"
            >{{ tag }}</span>
          </div>
          <p class="note-snippet">
            {{ note.content || '空白笔记' }}
          </p>
        </button>
      </aside>

      <main class="editor-panel">
        <div class="editor-header">
          <div>
            <p class="editor-kicker">
              {{ selected ? '编辑笔记' : '新建笔记' }}
            </p>
            <h2>{{ selected?.title || '未命名笔记' }}</h2>
          </div>
          <div class="editor-actions">
            <button
              class="secondary-btn"
              :disabled="!ticker.trim()"
              @click="goDashboard"
            >
              查看标的
            </button>
            <button
              class="secondary-btn"
              :disabled="!ticker.trim()"
              @click="router.push(`/dossier/${ticker.trim().toUpperCase()}`)"
            >
              查看时间线
            </button>
            <ActionButton
              v-if="selected"
              variant="danger"
              :loading="saving"
              loading-text="删除中..."
              @click="deleteSelected"
            >
              删除
            </ActionButton>
            <ActionButton
              :loading="saving || uploading"
              :loading-text="uploading ? '上传中...' : '保存中...'"
              @click="saveNote"
            >
              保存
            </ActionButton>
          </div>
        </div>

        <div class="form-grid">
          <label class="field">
            <span>标题</span>
            <input
              v-model="title"
              class="input"
              placeholder="例如：AAPL 财报后复盘"
            >
          </label>
          <label class="field">
            <span>Ticker</span>
            <input
              v-model="ticker"
              class="input"
              placeholder="AAPL"
            >
          </label>
          <label class="field wide">
            <span>标签</span>
            <input
              v-model="tagsInput"
              class="input"
              placeholder="逗号分隔，例如 财报,风险,待验证"
            >
          </label>
        </div>

        <MarkdownEditor
          v-model="content"
          placeholder="记录你的假设、证据、反证和下一步验证动作…"
          @image-upload="handleImageUpload"
        />

        <p class="hint">
          图片上传需要先有笔记 ID；新笔记会自动先保存再上传。Markdown 预览仅支持基础语法。
        </p>
      </main>
    </div>
  </section>
</template>

<style scoped>
.notes-page {
  min-height: 100vh;
  padding: 28px;
  background: var(--fin-bg);
  color: var(--fin-text);
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-end;
  margin-bottom: 18px;
}

.eyebrow,
.editor-kicker {
  margin: 0 0 6px;
  color: var(--fin-primary);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
}

.subtitle {
  max-width: 760px;
  margin: 10px 0 0;
  color: var(--fin-text-2);
}

.hero-actions,
.editor-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  gap: 18px;
}

.notes-list,
.editor-panel {
  border: 1px solid var(--fin-border);
  border-radius: var(--fin-radius-lg);
  background: var(--fin-card);
  box-shadow: var(--fin-shadow);
}

.notes-list {
  padding: 14px;
  max-height: calc(100vh - 150px);
  overflow: auto;
}

.editor-panel {
  padding: 20px;
}

.filters {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--fin-input);
  color: var(--fin-text);
}

.filter-btn,
.primary-btn,
.secondary-btn,
.danger-btn {
  border: 0;
  border-radius: 999px;
  padding: 10px 16px;
  font-weight: 800;
  cursor: pointer;
}

.primary-btn {
  background: var(--fin-primary);
  color: #fff;
}

.secondary-btn,
.filter-btn {
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
}

.danger-btn {
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.note-card {
  width: 100%;
  margin-bottom: 10px;
  border: 1px solid var(--fin-border);
  border-radius: 16px;
  padding: 12px;
  background: var(--fin-card);
  text-align: left;
  cursor: pointer;
}

.note-card.active {
  border-color: var(--fin-primary);
  box-shadow: inset 4px 0 0 var(--fin-primary);
}

.note-card-title {
  font-weight: 900;
  color: var(--fin-text);
}

.note-card-meta,
.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  color: var(--fin-muted);
  font-size: 12px;
}

.ticker,
.tag {
  border-radius: 999px;
  padding: 2px 8px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary-deep);
  font-weight: 800;
}

.tag {
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
}

.note-snippet {
  display: -webkit-box;
  margin: 10px 0 0;
  overflow: hidden;
  color: var(--fin-text-2);
  font-size: 13px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.empty {
  border: 1px dashed var(--fin-border);
  border-radius: 16px;
  padding: 22px;
  color: var(--fin-muted);
  text-align: center;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 180px;
  gap: 12px;
  margin-bottom: 14px;
}

.field {
  display: grid;
  gap: 6px;
  color: var(--fin-text-2);
  font-size: 13px;
  font-weight: 800;
}

.field.wide {
  grid-column: 1 / -1;
}

.message {
  margin-bottom: 12px;
  border-radius: 14px;
  padding: 10px 14px;
  font-weight: 700;
}

.message.error {
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

.message.success {
  background: var(--fin-success-soft);
  color: var(--fin-success);
}

.hint {
  color: var(--fin-muted);
  font-size: 12px;
}

@media (max-width: 900px) {
  .notes-page {
    padding: 18px;
  }

  .hero,
  .editor-header {
    align-items: stretch;
    flex-direction: column;
  }

  .workspace,
  .form-grid {
    grid-template-columns: 1fr;
  }

  .notes-list {
    max-height: none;
  }
}
</style>
