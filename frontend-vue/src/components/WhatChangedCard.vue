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
    high: '#dc2626',
    medium: 'var(--fin-primary)',
    low: 'var(--fin-success)',
  };
  return mapping[props.item.severity] || 'var(--fin-muted)';
});

const changeTypeIcon = computed(() => {
  const mapping: Record<string, string> = {
    report: 'RPT',
    note: 'NOTE',
    risk: 'RISK',
    alert: 'ALT',
    evidence: 'EVD',
    portfolio: 'PORT',
    price: 'PX',
    news: 'NEWS',
  };
  return mapping[props.item.change_type] || 'CHG';
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

const severityName = computed(() => {
  const mapping: Record<string, string> = {
    critical: '严重',
    high: '高',
    medium: '中',
    low: '低',
  };
  return mapping[props.item.severity] || props.item.severity;
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
        {{ severityName }}
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
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  padding: 16px;
  background: var(--fin-card-inset);
  cursor: pointer;
  transition: all 0.2s var(--fin-ease);
}

.what-changed-card:hover {
  border-color: var(--fin-border-strong);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.type-badge {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1.5px solid;
  border-radius: 999px;
  padding: 4px 11px;
  color: var(--fin-text);
  font-size: 13px;
  font-weight: 800;
}

.type-badge .icon {
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
}

.severity-badge {
  border-radius: 999px;
  padding: 3px 10px;
  color: var(--fin-bg);
  font-size: 12px;
  font-weight: 900;
}

.title {
  margin: 0 0 10px;
  color: var(--fin-text);
  font-size: 16px;
  font-weight: 900;
}

.symbol-tag {
  display: inline-block;
  margin-bottom: 10px;
  border-radius: 999px;
  padding: 2px 10px;
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
  font-family: var(--fin-mono);
  font-size: 12px;
  font-weight: 900;
}

.change-values {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
  color: var(--fin-text);
  font-size: 14px;
  font-weight: 800;
}

.change-values .before,
.change-values .arrow {
  color: var(--fin-muted);
}

.change-values .after,
.change-values .delta {
  color: var(--fin-primary);
}

.reason {
  margin: 0 0 12px;
  color: var(--fin-text-2);
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
  background: var(--fin-card-soft);
  color: var(--fin-text-2);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.tag.quality {
  color: var(--fin-danger);
  background: var(--fin-danger-soft);
}

.tag.freshness {
  color: var(--fin-warning);
  background: var(--fin-warning-soft);
}

.tag.citation {
  color: var(--fin-accent);
  background: var(--fin-accent-soft);
}

.footer {
  display: flex;
  justify-content: flex-end;
}

.action-hint {
  color: var(--fin-primary);
  font-size: 12px;
  font-weight: 900;
}
</style>
