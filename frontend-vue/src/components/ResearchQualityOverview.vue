<template>
  <div class="research-quality-overview">
    <!-- 健康分数卡片 -->
    <div class="health-score-card" :class="healthLevelClass">
      <div class="score-circle">
        <div class="score-value">{{ summary.health_score }}</div>
        <div class="score-label">健康分</div>
      </div>
      <div class="health-stats">
        <div class="stat-item">
          <span class="stat-label">总报告</span>
          <span class="stat-value">{{ summary.total_reports }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">复查率</span>
          <span class="stat-value">{{ (summary.reviewed_rate * 100).toFixed(0) }}%</span>
        </div>
        <div class="stat-item warning" v-if="summary.stale_reports > 0">
          <span class="stat-label">过期报告</span>
          <span class="stat-value">{{ summary.stale_reports }}</span>
        </div>
        <div class="stat-item error" v-if="summary.blocked_reports > 0">
          <span class="stat-label">阻断报告</span>
          <span class="stat-value">{{ summary.blocked_reports }}</span>
        </div>
      </div>
    </div>

    <!-- 质量问题列表 -->
    <div class="quality-issues" v-if="topIssues.length > 0">
      <h3 class="issues-title">质量问题 ({{ topIssues.length }})</h3>
      <div class="issues-list">
        <div
          v-for="issue in topIssues"
          :key="issue.id"
          class="issue-card"
          :class="`severity-${issue.severity}`"
          @click="handleIssueClick(issue)"
        >
          <div class="issue-header">
            <span class="issue-badge" :class="`badge-${issue.severity}`">
              {{ severityLabel(issue.severity) }}
            </span>
            <span class="issue-type-badge">{{ issueTypeLabel(issue.issue_type) }}</span>
          </div>
          <div class="issue-title">{{ issue.title }}</div>
          <div class="issue-reason">{{ issue.reason }}</div>
          <div class="issue-meta" v-if="issue.related_symbol">
            <span class="meta-tag">{{ issue.related_symbol }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 空态 -->
    <div class="empty-state" v-if="topIssues.length === 0 && summary.total_reports > 0">
      <div class="empty-icon">✓</div>
      <div class="empty-message">研究库健康，无需特别关注</div>
    </div>

    <div class="empty-state" v-if="summary.total_reports === 0">
      <div class="empty-icon">📚</div>
      <div class="empty-message">尚无研究报告</div>
      <div class="empty-hint">生成报告后，这里会显示研究库健康度分析</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import type { ResearchQualitySummary, ResearchQualityIssue } from '@/api/types';

const props = defineProps<{
  summary: ResearchQualitySummary;
  topIssues: ResearchQualityIssue[];
}>();

const router = useRouter();

const healthLevelClass = computed(() => {
  const score = props.summary.health_score;
  if (score >= 90) return 'health-excellent';
  if (score >= 75) return 'health-good';
  if (score >= 60) return 'health-fair';
  return 'health-poor';
});

function severityLabel(severity: string): string {
  const map: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低',
  };
  return map[severity] || severity;
}

function issueTypeLabel(type: string): string {
  const map: Record<string, string> = {
    stale_report: '过期报告',
    low_citation: '引用不足',
    blocked_report: '质量阻断',
    warn_report: '质量警告',
    unreviewed_report: '未复查',
    challenged_conclusion: '结论挑战',
    research_hygiene: '研究卫生',
    library_freshness: '库时效性',
  };
  return map[type] || type;
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

function handleIssueClick(issue: ResearchQualityIssue) {
  if (issue.target_route) {
    router.push(integratedRoute(issue.target_route));
  }
}
</script>

<style scoped>
.research-quality-overview {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* 健康分数卡片 */
.health-score-card {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 1.5rem;
  background: var(--fin-card);
  border-radius: 8px;
  border: 2px solid var(--fin-border);
  transition: border-color 0.2s;
}

.health-score-card.health-excellent {
  border-color: var(--fin-success);
}

.health-score-card.health-good {
  border-color: var(--fin-accent);
}

.health-score-card.health-fair {
  border-color: var(--fin-warning);
}

.health-score-card.health-poor {
  border-color: var(--fin-danger);
}

.score-circle {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--fin-accent-soft), var(--fin-card-soft));
}

.health-excellent .score-circle {
  background: linear-gradient(135deg, var(--fin-success-soft), var(--fin-card-soft));
}

.health-good .score-circle {
  background: linear-gradient(135deg, var(--fin-accent-soft), var(--fin-card-soft));
}

.health-fair .score-circle {
  background: linear-gradient(135deg, var(--fin-warning-soft), var(--fin-card-soft));
}

.health-poor .score-circle {
  background: linear-gradient(135deg, var(--fin-danger-soft), var(--fin-card-soft));
}

.score-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--fin-text);
  line-height: 1;
}

.score-label {
  font-size: 0.875rem;
  color: var(--fin-muted);
  margin-top: 0.25rem;
}

.health-stats {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 1rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.875rem;
  color: var(--fin-muted);
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--fin-text);
}

.stat-item.warning .stat-value {
  color: var(--fin-warning);
}

.stat-item.error .stat-value {
  color: var(--fin-danger);
}

/* 质量问题列表 */
.quality-issues {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.issues-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--fin-text);
  margin: 0;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.issue-card {
  padding: 1rem;
  background: var(--fin-card-inset);
  border-radius: 6px;
  border-left: 3px solid var(--fin-border);
  cursor: pointer;
  transition: all 0.2s;
}

.issue-card:hover {
  background: var(--fin-card-soft);
  transform: translateX(4px);
}

.issue-card.severity-critical {
  border-left-color: var(--fin-danger);
}

.issue-card.severity-high {
  border-left-color: var(--fin-warning);
}

.issue-card.severity-medium {
  border-left-color: var(--fin-primary);
}

.issue-card.severity-low {
  border-left-color: var(--fin-success);
}

.issue-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.issue-badge,
.issue-type-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  font-weight: 700;
}

.badge-critical {
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

.badge-high {
  background: var(--fin-warning-soft);
  color: var(--fin-warning);
}

.badge-medium {
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
}

.badge-low {
  background: var(--fin-success-soft);
  color: var(--fin-success);
}

.issue-type-badge {
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
}

.issue-title {
  font-size: 1rem;
  font-weight: 700;
  color: var(--fin-text);
  margin-bottom: 0.25rem;
}

.issue-reason {
  font-size: 0.9375rem;
  color: var(--fin-text-2);
  line-height: 1.55;
}

.issue-meta {
  margin-top: 0.5rem;
  display: flex;
  gap: 0.5rem;
}

.meta-tag {
  padding: 0.125rem 0.5rem;
  background: var(--fin-card-soft);
  border-radius: 4px;
  font-size: 0.8rem;
  color: var(--fin-muted);
  font-family: var(--fin-mono);
}

/* 空态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
  background: var(--fin-card-inset);
  border-radius: 8px;
  text-align: center;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.empty-message {
  font-size: 1rem;
  font-weight: 500;
  color: var(--fin-text);
  margin-bottom: 0.5rem;
}

.empty-hint {
  font-size: 0.9375rem;
  color: var(--fin-muted);
}
</style>
