<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { apiClient } from '@/api/client';
import type { TimelineEvent, WhatChangedItem } from '@/api/types';
import { useIdentityStore } from '@/stores/identity';
import EvidenceTimeline from '@/components/EvidenceTimeline.vue';
import WhatChangedCard from '@/components/WhatChangedCard.vue';

const route = useRoute();
const router = useRouter();
const identity = useIdentityStore();

const symbol = computed(() => String(route.params.symbol || '').toUpperCase());
const sessionId = computed(() => identity.sessionId || 'default_session');
const userId = computed(() => identity.userId || 'default_user');

const events = ref<TimelineEvent[]>([]);
const whatChanged = ref<WhatChangedItem[]>([]);
const loading = ref(false);
const errorMsg = ref<string | null>(null);

// 筛选参数
const eventTypeFilter = ref<string | undefined>(undefined);
const fromDate = ref<string | undefined>(undefined);
const toDate = ref<string | undefined>(undefined);

async function loadTimeline() {
  if (!symbol.value) return;

  loading.value = true;
  errorMsg.value = null;

  try {
    const [timelineResp, changesResp] = await Promise.all([
      apiClient.getTimeline({
        symbol: symbol.value,
        sessionId: sessionId.value,
        userId: userId.value,
        eventType: eventTypeFilter.value,
        from: fromDate.value,
        to: toDate.value,
        limit: 100,
      }),
      apiClient.getWhatChanged({
        sessionId: sessionId.value,
        userId: userId.value,
        symbol: symbol.value,
        limit: 3,
      }),
    ]);

    if (timelineResp.success) {
      events.value = timelineResp.events;
    } else {
      errorMsg.value = timelineResp.error || '加载失败';
    }

    whatChanged.value = changesResp.items;
  } catch (error: unknown) {
    console.error('Failed to load timeline:', error);
    errorMsg.value = (error as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail || (error as { message?: string })?.message || '加载时间线失败';
  } finally {
    loading.value = false;
  }
}

function goToDashboard() {
  if (symbol.value) {
    router.push(`/dashboard/${symbol.value}`);
  }
}

function goToNotes() {
  if (symbol.value) {
    router.push(`/notes?ticker=${symbol.value}`);
  }
}

onMounted(() => {
  loadTimeline();
});

watch(() => symbol.value, () => {
  loadTimeline();
});
</script>

<template>
  <div class="timeline-page">
    <!-- 页头 -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <button class="back-btn" @click="router.back()">← 返回</button>
          <div class="title-group">
            <p class="eyebrow">Evidence Timeline</p>
            <h1 class="page-title">{{ symbol }} 研究时间线</h1>
            <p class="subtitle">追踪研究过程中的关键事件和证据演化</p>
          </div>
        </div>
        <div class="header-actions">
          <button class="secondary-btn" @click="goToDashboard">查看标的</button>
          <button class="secondary-btn" @click="goToNotes">记录笔记</button>
          <button class="primary-btn" :disabled="loading" @click="loadTimeline">
            {{ loading ? '加载中...' : '刷新' }}
          </button>
        </div>
      </div>
    </header>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-banner">
      <span>⚠️</span>
      <p>{{ errorMsg }}</p>
    </div>

    <!-- What Changed 模块 -->
    <div v-if="whatChanged.length > 0" class="what-changed-section">
      <h2 class="section-title">🔍 {{ symbol }} 重要变化</h2>
      <div class="changes-grid">
        <WhatChangedCard v-for="item in whatChanged" :key="item.id" :item="item" />
      </div>
    </div>

    <!-- 时间线组件 -->
    <div class="timeline-container">
      <EvidenceTimeline :events="events" :loading="loading" />
    </div>

    <!-- 统计信息 -->
    <div v-if="!loading && events.length > 0" class="stats-footer">
      <p>共 {{ events.length }} 条事件记录</p>
    </div>
  </div>
</template>

<style scoped>
.timeline-page {
  min-height: 100vh;
  padding: 28px;
  background:
    radial-gradient(circle at 12% 8%, rgba(35, 88, 166, 0.14), transparent 28%),
    linear-gradient(135deg, #f7f4ec 0%, #edf3f1 52%, #e9eef7 100%);
  color: #1f2933;
}

.page-header {
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
}

.header-left {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.back-btn {
  margin-top: 24px;
  padding: 8px 12px;
  border: 1px solid #d7dde6;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
  color: #536171;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}

.back-btn:hover {
  border-color: #1f4f72;
  background: #fff;
}

.title-group {
  flex: 1;
}

.eyebrow {
  margin: 0 0 6px;
  color: #6f7c8e;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page-title {
  margin: 0 0 8px;
  font-size: 32px;
  font-weight: 900;
  color: #1f2933;
}

.subtitle {
  margin: 0;
  max-width: 600px;
  color: #5f6b7a;
  font-size: 14px;
}

.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
}

.primary-btn,
.secondary-btn {
  border: 0;
  border-radius: 999px;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 800;
  cursor: pointer;
  transition: all 0.2s;
}

.primary-btn {
  background: #1f4f72;
  color: white;
}

.primary-btn:hover:not(:disabled) {
  background: #163a54;
}

.primary-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.secondary-btn {
  background: #edf2f7;
  color: #263747;
}

.secondary-btn:hover {
  background: #dce4ec;
}

.what-changed-section {
  margin-bottom: 24px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.85);
  border: 1.5px solid rgba(43, 54, 70, 0.12);
  border-radius: 16px;
}

.section-title {
  margin: 0 0 16px;
  font-size: 18px;
  font-weight: 700;
  color: #1f2933;
}

.changes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 14px;
}

@media (max-width: 900px) {
  .changes-grid {
    grid-template-columns: 1fr;
  }
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 14px 18px;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 12px;
  color: #991b1b;
  font-weight: 600;
}

.error-banner span {
  font-size: 20px;
}

.error-banner p {
  margin: 0;
  flex: 1;
}

.timeline-container {
  margin-bottom: 32px;
}

.stats-footer {
  padding: 16px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}

.stats-footer p {
  margin: 0;
}

@media (max-width: 900px) {
  .timeline-page {
    padding: 18px;
  }

  .header-content {
    flex-direction: column;
    align-items: stretch;
  }

  .header-left {
    flex-direction: column;
    gap: 12px;
  }

  .back-btn {
    margin-top: 0;
    align-self: flex-start;
  }

  .header-actions {
    margin-top: 0;
  }

  .page-title {
    font-size: 24px;
  }
}
</style>
