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

const normalized = computed(() => props.events.map((event, index) => ({
  ...event,
  id: event.id || `${event.type}-${index}`,
  title: event.title || event.agent || event.stage || event.type,
  message: event.message || describeEvent(event),
  status: event.status || (props.running && index === props.events.length - 1 ? 'running' : 'done'),
})));

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
  if (text.includes('plan') || text.includes('policy') || text.includes('route')) return '规划策略';
  if (text.includes('agent') || text.includes('tool') || text.includes('execute')) return '执行分析';
  if (text.includes('render') || text.includes('synthesize') || text.includes('done')) return '形成结论';
  return '准备空间';
}

function describeEvent(event: ExecutionTraceEvent): string {
  if (event.stage) return `阶段 ${event.stage} 已记录`;
  if (event.agent) return `${event.agent} 返回执行状态`;
  return '执行事件已记录';
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
              <small>{{ fmtTime(event.timestamp) }} · {{ event.type }}</small>
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
}

.trace-panel.compact {
  padding: 14px;
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
}

.phase-stack {
  display: grid;
  gap: 12px;
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
