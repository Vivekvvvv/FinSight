<script setup lang="ts">
import type { EvidenceInfo } from '@/api/types';

interface Props extends EvidenceInfo {
  compact?: boolean;
}

const props = withDefaults(defineProps<Props>(), { compact: false });

function fmtTime(value?: string | null): string {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const minutes = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return days < 7
    ? `${days} 天前`
    : date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

const freshnessMap: Record<string, { label: string; tone: string; pulse?: boolean }> = {
  live: { label: '实时', tone: 'live', pulse: true },
  delayed_15min: { label: '延迟', tone: 'warn' },
  cached: { label: '缓存', tone: 'warn' },
  stale: { label: '过期', tone: 'danger' },
  demo: { label: '演示', tone: 'demo' },
  unknown: { label: '未知', tone: 'muted' },
};

const freshness = freshnessMap[props.freshnessStatus || 'unknown'] ?? freshnessMap.unknown;
const confidencePct = props.confidence != null ? Math.round(props.confidence * 100) : null;
const confClass = confidencePct == null ? '' : confidencePct >= 70 ? 'high' : confidencePct >= 40 ? 'mid' : 'low';

interface Warning {
  text: string;
  level: 'error' | 'warn' | 'info';
}

const warnings: Warning[] = [];

if (props.staleData || props.freshnessStatus === 'stale') {
  warnings.push({ text: '数据可能已超过 24 小时，请复查来源。', level: 'error' });
}
if ((props.fallbackLevel ?? 0) >= 1) {
  warnings.push({
    text: props.fallbackLevel === 2 ? '当前使用演示或缓存兜底数据。' : '主数据源不可用，已自动降级到备用源。',
    level: props.fallbackLevel === 2 ? 'warn' : 'info',
  });
}
if (props.degraded) {
  warnings.push({ text: '证据不足，结论表述已降低确定性。', level: 'warn' });
}
if (props.modelGenerated === false) {
  warnings.push({ text: '该结论由规则生成，并非 LLM 推理。', level: 'info' });
}
if (props.citationQuality === 'low') {
  warnings.push({ text: '引用来源不足，建议结合更多证据复查。', level: 'warn' });
}
if (confidencePct != null && confidencePct < 40) {
  warnings.push({ text: `置信度偏低（${confidencePct}%），不宜单独使用。`, level: 'error' });
}
if (props.qualityState === 'block') {
  warnings.push({ text: '未通过质检，请优先复查。', level: 'error' });
}

const citationText = props.citationCount != null ? `${props.citationCount} 条引用` : null;
</script>

<template>
  <div
    class="evidence"
    :class="{ compact, 'has-warnings': warnings.length > 0 }"
  >
    <div class="ev-row">
      <span
        class="ev-badge"
        :class="freshness.tone"
      >
        <span
          class="ev-dot"
          :class="{ pulse: freshness.pulse }"
        />
        {{ freshness.label }}
      </span>

      <span
        v-if="source"
        class="ev-item"
      >
        <span class="ev-label">来源</span>
        <span class="ev-val">{{ source }}</span>
      </span>

      <span
        v-if="asOf"
        class="ev-item"
      >
        <span class="ev-label">时间</span>
        <span class="ev-val">{{ fmtTime(asOf) }}</span>
      </span>

      <span
        v-if="fallbackLevel != null"
        class="ev-item"
      >
        <span class="ev-label">降级</span>
        <span class="ev-val">L{{ fallbackLevel }}</span>
      </span>

      <span
        v-if="confidencePct != null"
        class="ev-item"
      >
        <span class="ev-label">置信度</span>
        <span
          class="ev-val conf"
          :class="confClass"
        >{{ confidencePct }}%</span>
      </span>

      <span
        v-if="citationText"
        class="ev-item"
      >
        <span class="ev-val">{{ citationText }}</span>
      </span>

      <span
        v-if="modelGenerated === true"
        class="ev-item ev-subtle"
      >
        <span class="ev-val">AI 生成</span>
      </span>

      <span
        v-if="qualityState === 'pass'"
        class="ev-item ev-pass"
      >
        <span class="ev-val">质检通过</span>
      </span>
    </div>

    <div
      v-if="!compact && warnings.length > 0"
      class="ev-warnings"
    >
      <div
        v-for="(warning, index) in warnings"
        :key="index"
        class="ev-warning"
        :class="`level-${warning.level}`"
      >
        {{ warning.text }}
      </div>
    </div>

    <span
      v-if="compact && warnings.length > 0"
      class="ev-compact-warn"
      :class="`cw-${warnings[0].level}`"
    >
      {{ warnings.length === 1 ? warnings[0].text : `${warnings.length} 条注意事项` }}
    </span>
  </div>
</template>

<style scoped>
.evidence {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 13px;
  background: var(--fin-card-inset);
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  font-size: 13px;
}

.evidence.compact {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  padding: 6px 10px;
  gap: 8px;
}

.ev-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ev-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  border: 1px solid var(--fin-border);
  font-weight: 900;
  font-size: 12px;
}

.ev-badge.live { color: var(--fin-success); background: var(--fin-success-soft); }
.ev-badge.warn { color: var(--fin-warning); background: var(--fin-warning-soft); }
.ev-badge.danger { color: var(--fin-danger); background: var(--fin-danger-soft); }
.ev-badge.demo { color: var(--fin-accent); background: var(--fin-accent-soft); }
.ev-badge.muted { color: var(--fin-muted); background: var(--fin-card-soft); }

.ev-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.ev-dot.pulse {
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.7); }
}

.ev-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--fin-muted);
}

.ev-label::after {
  content: ':';
}

.ev-val {
  color: var(--fin-text);
  font-weight: 750;
}

.conf.high { color: var(--fin-success); }
.conf.mid { color: var(--fin-warning); }
.conf.low { color: var(--fin-danger); }
.ev-subtle { opacity: 0.72; }
.ev-pass .ev-val { color: var(--fin-success); }

.ev-warnings {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ev-warning {
  padding: 7px 10px;
  border-radius: 10px;
  line-height: 1.45;
}

.level-error,
.cw-error {
  color: var(--fin-danger);
  background: var(--fin-danger-soft);
}

.level-warn,
.cw-warn {
  color: var(--fin-warning);
  background: var(--fin-warning-soft);
}

.level-info,
.cw-info {
  color: var(--fin-accent);
  background: var(--fin-accent-soft);
}

.ev-compact-warn {
  padding: 4px 8px;
  border-radius: 999px;
  font-weight: 800;
  font-size: 12px;
}
</style>
