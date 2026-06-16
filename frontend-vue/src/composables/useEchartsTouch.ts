/**
 * ECharts 全局触摸优化配置
 */
import type { EChartsOption } from 'echarts';

/** 移动端触摸友好的 tooltip 配置 */
export const touchTooltip = {
  trigger: 'axis' as const,
  axisPointer: {
    type: 'cross' as const,
    label: { backgroundColor: '#5470c6' },
  },
};

/** 移动端工具栏（仅缩放） */
export const touchToolbox = {
  show: true,
  right: '2%',
  top: '2%',
  feature: {
    dataZoom: { yAxisIndex: false },
    restore: {},
  },
};

/** 移动端数据缩放（手指捏合） */
export const touchDataZoom: EChartsOption['dataZoom'] = [
  { type: 'inside', start: 0, end: 100 },
];

/**
 * 合并移动端触摸优化到现有 ECharts option
 * 桌面端不影响原始配置
 */
export function withTouchSupport(option: EChartsOption): EChartsOption {
  if (typeof window === 'undefined' || window.innerWidth >= 768) return option;
  return {
    ...option,
    tooltip: { ...touchTooltip, ...(option.tooltip as object || {}) } as any,
    toolbox: touchToolbox as any,
    dataZoom: [...(touchDataZoom as any[]), ...((option.dataZoom as any[]) || [])],
  };
}
