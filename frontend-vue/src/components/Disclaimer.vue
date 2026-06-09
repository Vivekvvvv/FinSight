<script setup lang="ts">
import { computed } from 'vue';

type Variant = 'info' | 'report' | 'action';

const props = withDefaults(defineProps<{ variant?: Variant; asOf?: string }>(), {
  variant: 'info',
  asOf: '',
});

const STYLE: Record<Variant, { bg: string; border: string; fg: string; label: string }> = {
  info: { bg: '#fbf8f3', border: '#ece6d8', fg: '#7a6e5d', label: '信息提示' },
  report: { bg: '#fff8f0', border: '#e9b69f', fg: '#6e4b3a', label: '研究报告免责声明' },
  action: { bg: '#fff1ea', border: '#f0c4ad', fg: '#7a3f29', label: '执行前提醒' },
};

const BODY =
  '本平台提供的所有分析、报告与建议仅供研究与学习用途,不构成任何投资建议、要约或承诺。' +
  '金融市场有风险,过往业绩不预示未来表现。请在做出投资决策前,咨询持牌专业顾问并独立核实数据。';

const palette = computed(() => STYLE[props.variant]);
const asOfText = computed(() => {
  const d = props.asOf ? new Date(props.asOf) : new Date();
  return Number.isNaN(d.getTime()) ? props.asOf : d.toLocaleString('zh-CN', { hour12: false });
});
</script>

<template>
  <div
    class="disclaimer"
    role="note"
    :aria-label="palette.label"
    :style="{ background: palette.bg, border: `1px solid ${palette.border}`, color: palette.fg }"
  >
    <div class="title">
      {{ palette.label }}
    </div>
    <div>{{ BODY }}</div>
    <div class="as-of">
      数据时效: {{ asOfText }}
    </div>
  </div>
</template>

<style scoped>
.disclaimer {
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.55;
}
.title {
  font-weight: 600;
  margin-bottom: 2px;
}
.as-of {
  margin-top: 4px;
  font-size: 11px;
  opacity: 0.8;
}
</style>
