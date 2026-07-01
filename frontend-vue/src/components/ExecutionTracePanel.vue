<script setup lang="ts">
import { computed } from 'vue';
import type { ExecutionTraceEvent } from '@/api/types';

const props = withDefaults(defineProps<{
  events: ExecutionTraceEvent[];
  compact?: boolean;
  running?: boolean;
}>(), {
  compact: false,
  running: false,
});

const normalized = computed(() => props.events.map((event, index) => {
  const stage = event.stage || event.type || '';
  return {
    ...event,
    id: event.id || `${event.type}-${index}`,
    title: humanTitle(event),
    message: humanMessage(event),
    status: event.status || (props.running && index === props.events.length - 1 ? 'running' : 'done'),
    detail: humanDetail(event, stage),
  };
}));

const summary = computed(() => {
  const done = normalized.value.filter((event) => event.status === 'done').length;
  const errors = normalized.value.filter((event) => event.status === 'error').length;
  return { total: normalized.value.length, done, errors };
});

const phases = computed(() => {
  const groups = new Map<string, typeof normalized.value>();
  for (const event of normalized.value) {
    const key = phaseOf(event.stage || event.type);
    const list = groups.get(key) || [];
    list.push(event);
    groups.set(key, list);
  }
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }));
});

function phaseOf(value: string): string {
  const text = value.toLowerCase();
  if (text.includes('policy') || text.includes('route') || text.includes('planner') || text.includes('plan')) return '规划策略';
  if (text.includes('confirmation') || text.includes('prepare') || text.includes('context')) return '准备空间';
  if (text.includes('agent') || text.includes('tool') || text.includes('execute') || text.includes('step')) return '执行分析';
  if (text.includes('render') || text.includes('synthesize') || text.includes('done')) return '形成结论';
  return '准备空间';
}

function normalizeText(value?: string | null): string {
  return String(value || '').trim().toLowerCase();
}

function humanTitle(event: ExecutionTraceEvent): string {
  const raw = normalizeText(event.stage || event.title || event.type || event.agent);
  if (raw.includes('policy')) return '确定可用能力';
  if (raw.includes('planner') || raw === 'planning' || raw.includes('plan_research')) return '规划研究步骤';
  if (raw.includes('plan_ready') || raw.includes('selection')) return '整理研究计划';
  if (raw.includes('confirmation')) return '检查执行条件';
  if (raw.includes('execute') || raw === 'executing') return '调用数据工具';
  if (raw.includes('step_start')) return '开始执行工具';
  if (raw.includes('step_done') || raw.includes('tool')) return '数据工具返回';
  if (raw.includes('synthesize')) return '整合分析结果';
  if (raw.includes('render')) return '生成回答';
  if (raw.includes('done')) return '完成输出';
  if (event.agent) return '智能体返回结果';
  return event.title || '记录执行进度';
}

function humanMessage(event: ExecutionTraceEvent): string {
  const raw = normalizeText(`${event.stage || ''} ${event.title || ''} ${event.message || ''}`);
  if (raw.includes('policy')) return '正在判断这个问题需要哪些数据源和工具。';
  if (raw.includes('planner') || raw.includes('planning')) return '正在把你的问题拆成可执行的研究步骤。';
  if (raw.includes('plan_ready') || raw.includes('selection summary')) return '研究计划已准备好，准备进入执行阶段。';
  if (raw.includes('confirmation')) return '正在确认是否可以直接执行，无需你额外确认。';
  if (raw.includes('execute') || raw.includes('executing')) return '正在拉取行情、财务或新闻等数据。';
  if (raw.includes('step_start')) return '某个数据工具已经开始运行。';
  if (raw.includes('step_done') || raw.includes('tool')) return '已有数据返回，正在继续处理。';
  if (raw.includes('synthesize')) return '正在把工具结果整理成中文分析。';
  if (raw.includes('render')) return '正在生成最终回答。';
  if (raw.includes('error')) return event.message || '执行过程中遇到异常。';
  if (event.message && !event.message.includes('_')) return event.message;
  return '执行进度已更新。';
}

function humanDetail(event: ExecutionTraceEvent, stage: string): string {
  const phase = phaseOf(stage || event.type || '');
  if (event.status === 'error') return '需要重试或检查数据源';
  if (event.status === 'running') return `${phase}中`;
  return phase;
}

function fmtTime(value?: string | null): string {
  if (!value) return '--:--:--';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString('zh-CN', { hour12: false });
}
</script>

<template>
  <section class="trace-panel" :class="{ compact }" data-testid="execution-trace-panel">
    <header class="trace-head">
      <div>
        <p>AGENT TRACE</p>
        <h3>研究执行过程</h3>
      </div>
      <div class="trace-stats">
        <span>{{ summary.done }}/{{ summary.total }} 完成</span>
        <span v-if="running" class="pulse">运行中</span>
        <span v-if="summary.errors" class="danger">{{ summary.errors }} 异常</span>
      </div>
    </header>

    <div v-if="normalized.length === 0" class="trace-empty">
      提交问题后，这里会展示规划、检索、分析和生成过程。
    </div>

    <div v-else class="phase-stack">
      <article v-for="phase in phases" :key="phase.name" class="phase-card">
        <div class="phase-name">{{ phase.name }}</div>
        <ol>
          <li v-for="event in phase.items" :key="event.id" :class="`s-${event.status}`">
            <span class="dot" />
            <div>
              <strong>{{ event.title }}</strong>
              <p>{{ event.message }}</p>
              <small>{{ fmtTime(event.timestamp) }} · {{ event.detail }}</small>
            </div>
          </li>
        </ol>
      </article>
    </div>
  </section>
</template>

<style scoped>
.trace-panel {
  border: 1px solid var(--fin-border);
  border-radius: 22px;
  background: var(--fin-card-inset);
  color: var(--fin-text);
  padding: 18px;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
}

.trace-panel.compact {
  padding: 10px;
  border-radius: 12px;
  max-height: 260px;
}

.trace-panel.compact .trace-head {
  margin-bottom: 8px;
}

.trace-panel.compact .trace-head h3 {
  font-size: 14px;
}

.trace-panel.compact .trace-head p {
  display: none;
}

.trace-panel.compact .phase-stack {
  gap: 8px;
}

.trace-panel.compact .phase-card {
  border-radius: 12px;
  padding: 9px;
}

.trace-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.trace-head p,
.phase-name {
  margin: 0 0 4px;
  color: var(--fin-primary);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.trace-head h3 {
  margin: 0;
  font-size: 18px;
}

.trace-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.trace-stats span {
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 12px;
  color: var(--fin-text-2);
}

.pulse {
  color: var(--fin-success) !important;
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--fin-success) 40%, transparent);
  animation: pulse 1.4s infinite;
}

.danger {
  color: var(--fin-danger) !important;
}

.trace-empty {
  color: var(--fin-muted);
  font-size: 14px;
  line-height: 1.7;
  overflow-y: auto;
}

.phase-stack {
  display: grid;
  gap: 12px;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.phase-card {
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  padding: 12px;
  background: var(--fin-card-soft);
}

ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

li {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 10px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fin-primary);
  margin-top: 8px;
  box-shadow: 0 0 18px var(--fin-primary-soft);
}

li.s-error .dot {
  background: var(--fin-danger);
}

li.s-running .dot {
  background: var(--fin-success);
  animation: pulse 1.4s infinite;
}

strong {
  display: block;
  font-size: 14px;
}

p {
  margin: 2px 0;
  color: var(--fin-text-2);
  font-size: 13px;
  line-height: 1.6;
}

small {
  color: var(--fin-muted);
  font-size: 12px;
}

@keyframes pulse {
  70% { box-shadow: 0 0 0 9px rgba(140, 255, 182, 0); }
  100% { box-shadow: 0 0 0 0 rgba(140, 255, 182, 0); }
}
</style>
