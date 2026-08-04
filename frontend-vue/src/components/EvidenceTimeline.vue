<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import type { TimelineEvent } from '@/api/types';

interface Props {
  events: TimelineEvent[];
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

const router = useRouter();

// 事件类型筛选
const selectedType = ref<string>('all');
const eventTypes = [
  { value: 'all', label: '全部' },
  { value: 'report', label: '报告' },
  { value: 'note', label: '笔记' },
  { value: 'alert', label: '告警' },
  { value: 'risk', label: '风险' },
  { value: 'evidence', label: '证据' },
];

// 过滤后的事件
const filteredEvents = computed(() => {
  if (selectedType.value === 'all') {
    return props.events;
  }
  return props.events.filter(e => e.event_type === selectedType.value);
});

// 严重度颜色（走主题 token，随明暗切换）
function getSeverityColor(severity: string): string {
  switch (severity) {
    case 'critical': return 'var(--fin-danger)';
    case 'high': return 'var(--fin-primary)';
    case 'medium': return 'var(--fin-warning)';
    case 'low': return 'var(--fin-success)';
    default: return 'var(--fin-muted)';
  }
}

// 事件类型图标
function getEventTypeIcon(type: string): string {
  switch (type) {
    case 'report': return '📊';
    case 'note': return '📝';
    case 'alert': return '🔔';
    case 'risk': return '⚠️';
    case 'evidence': return '🔍';
    case 'watchlist': return '⭐';
    default: return '•';
  }
}

// 格式化时间
function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  } else if (diffDays === 1) {
    return '昨天';
  } else if (diffDays < 7) {
    return `${diffDays} 天前`;
  } else {
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
  }
}

function integratedRoute(path: string): string {
  if (path.startsWith('/dashboard/')) return path.replace('/dashboard/', '/dossier/');
  if (path === '/dashboard') return '/dossier/AAPL';
  if (path.startsWith('/timeline/')) return path.replace('/timeline/', '/dossier/');
  if (path === '/watchlist') return '/stocks?tab=watchlist';
  if (path === '/alerts') return '/welcome';
  if (path === '/backtest') return '/portfolio?tool=backtest';
  if (path === '/portfolio/optimize') return '/portfolio?tool=optimize';
  if (path === '/portfolio/risk-lens') return '/portfolio?tool=risk';
  if (path.startsWith('/research/qa')) return '/chat?mode=qa';
  if (path.startsWith('/research/report')) return '/reports?tool=generate';
  if (path.startsWith('/research/financials')) return '/reports?tool=financials';
  return path;
}

// 点击事件跳转
function handleEventClick(event: TimelineEvent) {
  if (event.target_route) {
    router.push(integratedRoute(event.target_route));
  }
}

// 质量标识
function getQualityBadge(event: TimelineEvent): string | null {
  if (!event.evidence) return null;

  const { quality_state, freshness_status, confidence } = event.evidence;

  if (quality_state === 'block') return 'blocked';
  if (quality_state === 'warn') return 'warning';
  if (freshness_status === 'stale') return 'stale';
  if (confidence != null && confidence < 0.6) return 'low-confidence'; // 0 是最该警示的置信度，不能被 falsy 吞掉

  return null;
}

function getQualityBadgeLabel(badge: string): string {
  switch (badge) {
    case 'blocked': return '质量阻断';
    case 'warning': return '质量警告';
    case 'stale': return '数据过期';
    case 'low-confidence': return '低置信度';
    default: return '';
  }
}
</script>

<template>
  <div class="evidence-timeline">
    <!-- 类型筛选 -->
    <div class="filter-bar">
      <button
        v-for="type in eventTypes"
        :key="type.value"
        :class="['filter-btn', { active: selectedType === type.value }]"
        @click="selectedType = type.value"
      >
        {{ type.label }}
      </button>
    </div>

    <!-- 加载状态 -->
    <div
      v-if="loading"
      class="loading-state"
    >
      <div class="spinner" />
      <p>加载时间线中...</p>
    </div>

    <!-- 空态 -->
    <div
      v-else-if="filteredEvents.length === 0"
      class="empty-state"
    >
      <div class="empty-icon">
        📅
      </div>
      <h3>暂无事件记录</h3>
      <p>该标的还没有研究活动。开始生成报告或记录笔记，事件将自动出现在时间线中。</p>
    </div>

    <!-- 时间线列表 -->
    <div
      v-else
      class="timeline-list"
    >
      <div
        v-for="event in filteredEvents"
        :key="event.id"
        class="timeline-item"
        :class="{ clickable: !!event.target_route }"
        @click="handleEventClick(event)"
      >
        <!-- 左侧时间轴 -->
        <div class="timeline-axis">
          <div
            class="timeline-dot"
            :style="{ backgroundColor: getSeverityColor(event.severity) }"
          />
          <div class="timeline-line" />
        </div>

        <!-- 右侧事件卡片 -->
        <div
          class="event-card"
          data-testid="event-card"
          :style="{ borderLeftColor: getSeverityColor(event.severity) }"
        >
          <div class="event-header">
            <span class="event-icon">{{ getEventTypeIcon(event.event_type) }}</span>
            <span class="event-time">{{ formatDate(event.occurred_at) }}</span>
          </div>

          <h4
            class="event-title"
            data-testid="event-title"
          >
            {{ event.title }}
          </h4>

          <p
            v-if="event.summary"
            class="event-summary"
          >
            {{ event.summary }}
          </p>

          <!-- 质量标识 -->
          <div
            v-if="getQualityBadge(event)"
            class="quality-badges"
          >
            <span
              class="quality-badge"
              :class="getQualityBadge(event)"
            >
              {{ getQualityBadgeLabel(getQualityBadge(event)!) }}
            </span>
          </div>

          <!-- 证据指标 -->
          <div
            v-if="event.evidence"
            class="evidence-info"
          >
            <span
              v-if="event.evidence.confidence != null"
              class="evidence-item"
            >
              置信度：{{ (event.evidence.confidence * 100).toFixed(0) }}%
            </span>
            <span
              v-if="event.evidence.citation_count"
              class="evidence-item"
            >
              引用：{{ event.evidence.citation_count }} 条
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.evidence-timeline {
  width: 100%;
  max-width: none;
  margin: 0;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 24px;
  padding: 12px;
  background: var(--fin-card-soft);
  border-radius: 12px;
  border: 1px solid var(--fin-border);
}

.filter-btn {
  padding: 6px 14px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card);
  color: var(--fin-text-2);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: var(--fin-primary);
  background: var(--fin-primary-soft);
}

.filter-btn.active {
  border-color: var(--fin-primary);
  background: var(--fin-primary);
  color: #fff;
}

.loading-state,
.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--fin-muted);
}

.spinner {
  width: 40px;
  height: 40px;
  margin: 0 auto 16px;
  border: 3px solid var(--fin-border);
  border-top-color: var(--fin-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state .empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-state h3 {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 800;
  color: var(--fin-text);
}

.empty-state p {
  max-width: 400px;
  margin: 0 auto;
  font-size: 14px;
  color: var(--fin-muted);
}

.timeline-list {
  position: relative;
}

.timeline-item {
  position: relative;
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}

.timeline-item.clickable {
  cursor: pointer;
}

.timeline-axis {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 24px;
  flex-shrink: 0;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  border: 3px solid var(--fin-card);
  box-shadow: var(--fin-shadow);
  z-index: 2;
}

.timeline-line {
  position: absolute;
  top: 12px;
  width: 2px;
  height: calc(100% + 24px);
  background: var(--fin-border);
  z-index: 1;
}

.timeline-item:last-child .timeline-line {
  display: none;
}

.event-card {
  flex: 1;
  padding: 16px 18px;
  background: var(--fin-card);
  border-left: 4px solid var(--fin-primary);
  border-radius: 12px;
  box-shadow: var(--fin-shadow);
  transition: all 0.2s;
}

.timeline-item.clickable .event-card:hover {
  box-shadow: var(--fin-shadow);
  transform: translateY(-2px);
}

.event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.event-icon {
  font-size: 16px;
}

.event-time {
  font-size: 12px;
  font-weight: 700;
  color: var(--fin-muted);
}

.event-title {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 800;
  color: var(--fin-text);
  line-height: 1.4;
}

.event-summary {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--fin-text-2);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.quality-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.quality-badge {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 800;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.quality-badge.blocked {
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

.quality-badge.warning {
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.quality-badge.stale {
  background: var(--fin-accent-soft);
  color: var(--fin-accent);
}

.quality-badge.low-confidence {
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.evidence-info {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--fin-border);
}

.evidence-item {
  font-size: 12px;
  font-weight: 600;
  color: var(--fin-muted);
}

@media (max-width: 640px) {
  .timeline-axis {
    width: 16px;
  }

  .timeline-dot {
    width: 8px;
    height: 8px;
  }

  .event-card {
    padding: 12px 14px;
  }
}
</style>
