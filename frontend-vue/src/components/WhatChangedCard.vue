<script setup lang="ts">
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import type { WhatChangedItem } from '@/api/types';

const props = defineProps<{
  item: WhatChangedItem;
}>();

const router = useRouter();

const severityColor = computed(() => {
  const mapping: Record<string, string> = {
    critical: '#dc2626',
    high: '#ea580c',
    medium: '#d97706',
    low: '#84cc16',
  };
  return mapping[props.item.severity] || '#6b7280';
});

const changeTypeIcon = computed(() => {
  const mapping: Record<string, string> = {
    report: '📄',
    note: '📝',
    risk: '⚠️',
    alert: '🔔',
    evidence: '🔍',
    portfolio: '💼',
    price: '📈',
    news: '📰',
  };
  return mapping[props.item.change_type] || '📌';
});

const changeTypeName = computed(() => {
  const mapping: Record<string, string> = {
    report: '报告',
    note: '笔记',
    risk: '风险',
    alert: '告警',
    evidence: '证据',
    portfolio: '持仓',
    price: '价格',
    news: '新闻',
  };
  return mapping[props.item.change_type] || '变化';
});

function handleClick() {
  if (props.item.target_route) {
    void router.push(props.item.target_route);
  }
}
</script>

<template>
  <div class="what-changed-card" data-testid="what-changed-card" @click="handleClick">
    <div class="card-header">
      <div class="type-badge" :style="{ borderColor: severityColor }">
        <span class="icon">{{ changeTypeIcon }}</span>
        <span class="label">{{ changeTypeName }}</span>
      </div>
      <div class="severity-badge" data-testid="severity-badge" :style="{ backgroundColor: severityColor }">
        {{ item.severity === 'critical' ? '严重' : item.severity === 'high' ? '高' : item.severity === 'medium' ? '中' : '低' }}
      </div>
    </div>

    <h3 class="title" data-testid="change-title">{{ item.title }}</h3>

    <div v-if="item.symbol" class="symbol-tag">{{ item.symbol }}</div>

    <div v-if="item.before !== undefined && item.after !== undefined" class="change-values">
      <span class="before">{{ item.before }}</span>
      <span class="arrow">→</span>
      <span class="after">{{ item.after }}</span>
      <span v-if="item.delta" class="delta">{{ item.delta }}</span>
    </div>

    <p class="reason">{{ item.reason }}</p>

    <div v-if="item.evidence" class="evidence-tags">
      <span v-if="item.evidence.quality_state" class="tag quality">{{ item.evidence.quality_state }}</span>
      <span v-if="item.evidence.freshness_status" class="tag freshness">{{ item.evidence.freshness_status }}</span>
      <span v-if="item.evidence.citation_quality" class="tag citation">引用: {{ item.evidence.citation_quality }}</span>
    </div>

    <div class="footer">
      <span class="action-hint">点击查看详情 →</span>
    </div>
  </div>
</template>

<style scoped>
.what-changed-card {
  border: 1px solid rgba(43, 54, 70, 0.12);
  border-radius: 16px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  transition: all 0.2s ease;
}

.what-changed-card:hover {
  border-color: #1f4f72;
  box-shadow: 0 4px 12px rgba(31, 79, 114, 0.15);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.type-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1.5px solid;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 13px;
  font-weight: 700;
}

.type-badge .icon {
  font-size: 16px;
}

.severity-badge {
  border-radius: 999px;
  padding: 3px 10px;
  color: white;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.title {
  margin: 0 0 10px;
  color: #1f2933;
  font-size: 16px;
  font-weight: 900;
}

.symbol-tag {
  display: inline-block;
  margin-bottom: 10px;
  border-radius: 999px;
  padding: 2px 10px;
  background: #e7f0f7;
  color: #1f4f72;
  font-size: 12px;
  font-weight: 800;
}

.change-values {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
}

.change-values .before {
  color: #6b7280;
}

.change-values .arrow {
  color: #9ca3af;
}

.change-values .after {
  color: #1f4f72;
}

.change-values .delta {
  color: #ea580c;
  font-weight: 900;
}

.reason {
  margin: 0 0 12px;
  color: #52606d;
  font-size: 14px;
  line-height: 1.5;
}

.evidence-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.evidence-tags .tag {
  border-radius: 999px;
  padding: 2px 8px;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.evidence-tags .tag.quality {
  background: #fee2e2;
  color: #991b1b;
}

.evidence-tags .tag.freshness {
  background: #fef3c7;
  color: #92400e;
}

.evidence-tags .tag.citation {
  background: #dbeafe;
  color: #1e40af;
}

.footer {
  display: flex;
  justify-content: flex-end;
}

.action-hint {
  color: #1f4f72;
  font-size: 12px;
  font-weight: 700;
}
</style>
