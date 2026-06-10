<script setup lang="ts">
/**
 * EvidencePanel — 统一数据可信度展示
 *
 * 降级规则（"证据不足时如何表达"）：
 *   fallbackLevel >= 1    → 橙色警告 "数据源降级"
 *   staleData = true      → 红色    "数据已过期（>24h）"
 *   degraded = true       → 黄色    "结论保守（数据不足）"
 *   confidence < 0.4      → 红色置信度 + 文字说明
 *   citationQuality = low → 黄色    "引用不足"
 *   modelGenerated = false→ 橙色    "规则生成（非 AI）"
 *   qualityState = block  → 红色    "未通过质检"
 */
import type { EvidenceInfo } from '@/api/types';

interface Props extends EvidenceInfo {
  compact?: boolean; // 单行紧凑模式
}

const props = withDefaults(defineProps<Props>(), { compact: false });

// ── 时间格式 ────────────────────────────────────────────────
function fmtTime(v?: string | null): string {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  const diffMs = Date.now() - d.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} 小时前`;
  const days = Math.floor(hrs / 24);
  return days < 7
    ? `${days} 天前`
    : d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

// ── 新鲜度映射 ──────────────────────────────────────────────
const FRESHNESS: Record<string, { label: string; color: string; pulse?: boolean }> = {
  live:          { label: '实时',       color: '#27ae60', pulse: true },
  delayed_15min: { label: '延迟 15min', color: '#d97706' },
  cached:        { label: '已缓存',     color: '#8c887e' },
  stale:         { label: '数据过期',   color: '#e74c3c' },
  unknown:       { label: '来源未知',   color: '#bfb6a3' },
};

const freshness = (props.freshnessStatus && FRESHNESS[props.freshnessStatus]) ?? FRESHNESS.unknown;

// ── 置信度 ──────────────────────────────────────────────────
const confidencePct = props.confidence != null ? Math.round(props.confidence * 100) : null;
const confClass = confidencePct == null ? '' : confidencePct >= 70 ? 'high' : confidencePct >= 40 ? 'mid' : 'low';

// ── 降级警告列表 ─────────────────────────────────────────────
interface Warning { icon: string; text: string; level: 'error' | 'warn' | 'info' }
const warnings: Warning[] = [];

if (props.staleData) {
  warnings.push({ icon: '⏰', text: '数据超过 24 小时，结论仅供参考', level: 'error' });
}
if ((props.fallbackLevel ?? 0) >= 1) {
  const text = props.fallbackLevel === 2 ? '使用缓存回退数据，可能非最新' : '主数据源不可用，已自动降级';
  warnings.push({ icon: '⚠', text, level: 'warn' });
}
if (props.degraded) {
  warnings.push({ icon: '⚡', text: '证据不足，结论表述已降低确定性', level: 'warn' });
}
if (props.modelGenerated === false) {
  warnings.push({ icon: '🔧', text: '本结论由确定性规则生成，非 LLM 推理', level: 'warn' });
}
if (props.citationQuality === 'low') {
  warnings.push({ icon: '📄', text: '引用来源不足（< 2 条），请谨慎参考', level: 'warn' });
}
if (confidencePct != null && confidencePct < 40) {
  warnings.push({ icon: '❓', text: `置信度偏低（${confidencePct}%），建议结合多方数据判断`, level: 'error' });
}
if (props.qualityState === 'block') {
  warnings.push({ icon: '🚫', text: '该结论未通过质检，内容可能存在问题', level: 'error' });
}

// ── citation 质量标签 ────────────────────────────────────────
const citationBadge = props.citationCount != null ? {
  high:   { label: `${props.citationCount} 条引用`, color: '#27ae60' },
  medium: { label: `${props.citationCount} 条引用`, color: '#d97706' },
  low:    { label: `${props.citationCount} 条引用`, color: '#e74c3c' },
}[props.citationQuality ?? 'medium'] ?? { label: `${props.citationCount} 条引用`, color: '#8c887e' }
: null;
</script>

<template>
  <div class="evidence" :class="{ compact, 'has-warnings': warnings.length > 0 }">
    <!-- 主 meta 行 -->
    <div class="ev-row">
      <!-- 新鲜度 badge -->
      <span
        class="ev-badge"
        :style="{ background: freshness.color + '15', color: freshness.color, borderColor: freshness.color + '35' }"
      >
        <span class="ev-dot" :class="{ pulse: freshness.pulse }" :style="{ background: freshness.color }" />
        {{ freshness.label }}
      </span>

      <!-- 数据来源 -->
      <span v-if="source" class="ev-item">
        <span class="ev-label">来源</span>
        <span class="ev-val">{{ source }}</span>
      </span>

      <!-- 时间 -->
      <span v-if="asOf" class="ev-item">
        <span class="ev-label">时间</span>
        <span class="ev-val">{{ fmtTime(asOf) }}</span>
      </span>

      <!-- 置信度 -->
      <span v-if="confidencePct != null" class="ev-item">
        <span class="ev-label">置信度</span>
        <span class="ev-val conf" :class="confClass">{{ confidencePct }}%</span>
      </span>

      <!-- citation 质量 -->
      <span v-if="citationBadge" class="ev-item">
        <span class="ev-val" :style="{ color: citationBadge.color, fontWeight: '700' }">
          {{ citationBadge.label }}
        </span>
      </span>

      <!-- AI 生成标志 -->
      <span v-if="modelGenerated === true" class="ev-item ev-subtle">
        <span>🤖</span><span class="ev-val">AI 生成</span>
      </span>

      <!-- 质检通过 -->
      <span v-if="qualityState === 'pass'" class="ev-item ev-pass">
        <span>✓</span><span class="ev-val">质检通过</span>
      </span>
    </div>

    <!-- 降级警告行（完整模式） -->
    <div v-if="!compact && warnings.length > 0" class="ev-warnings">
      <div
        v-for="(w, i) in warnings"
        :key="i"
        class="ev-warning"
        :class="`level-${w.level}`"
      >
        <span class="w-icon">{{ w.icon }}</span>
        <span class="w-text">{{ w.text }}</span>
      </div>
    </div>

    <!-- compact 模式：用 badge 指示最高级警告 -->
    <span
      v-if="compact && warnings.length > 0"
      class="ev-compact-warn"
      :class="`cw-${warnings[0].level}`"
      :title="warnings.map(w => w.text).join(' · ')"
    >
      {{ warnings[0].icon }} {{ warnings.length === 1 ? warnings[0].text : `${warnings.length} 条注意` }}
    </span>
  </div>
</template>

<style scoped>
.evidence {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 9px 13px;
  background: var(--fin-card-inset);
  border-radius: 8px;
  border: 1px solid var(--fin-border);
  font-size: 12px;
}

.evidence.compact {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  padding: 4px 10px;
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
  gap: 5px;
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid;
  font-weight: 700;
  font-size: 12px;
  white-space: nowrap;
}

.ev-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ev-dot.pulse {
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(0.7); }
}

.ev-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--fin-muted);
}

.ev-label { opacity: 0.65; }
.ev-label::after { content: ':'; }

.ev-val {
  color: var(--fin-text);
  font-weight: 650;
}

.conf.high { color: var(--fin-success); font-weight: 800; }
.conf.mid  { color: var(--fin-warning); font-weight: 800; }
.conf.low  { color: var(--fin-danger); font-weight: 800; }

.ev-subtle { opacity: 0.6; }
.ev-pass .ev-val { color: var(--fin-success); font-weight: 800; }

/* 降级警告 */
.ev-warnings {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.ev-warning {
  display: flex;
  align-items: flex-start;
  gap: 5px;
  padding: 6px 9px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.4;
}

.ev-warning.level-error { background: var(--fin-danger-soft); color: var(--fin-danger); border: 1px solid color-mix(in srgb, var(--fin-danger) 45%, transparent); }
.ev-warning.level-warn  { background: var(--fin-warning-soft); color: var(--fin-warning); border: 1px solid color-mix(in srgb, var(--fin-warning) 45%, transparent); }
.ev-warning.level-info  { background: var(--fin-accent-soft); color: var(--fin-accent); border: 1px solid color-mix(in srgb, var(--fin-accent) 42%, transparent); }

.w-icon { flex-shrink: 0; }
.w-text { flex: 1; }

/* compact 降级 badge */
.ev-compact-warn {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 8px;
  border: 1px solid;
  white-space: nowrap;
  cursor: default;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cw-error { background: var(--fin-danger-soft); color: var(--fin-danger); border-color: color-mix(in srgb, var(--fin-danger) 45%, transparent); }
.cw-warn  { background: var(--fin-warning-soft); color: var(--fin-warning); border-color: color-mix(in srgb, var(--fin-warning) 45%, transparent); }
.cw-info  { background: var(--fin-accent-soft); color: var(--fin-accent); border-color: color-mix(in srgb, var(--fin-accent) 42%, transparent); }
</style>
