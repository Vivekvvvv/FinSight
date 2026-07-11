<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import type { EChartsOption } from 'echarts';
import type { RiskSnapshot } from '@/api/types';
import { useThemeStore } from '@/stores/theme';

interface Props {
  snapshots: RiskSnapshot[];
  metric: 'risk_score' | 'total_value' | 'concentration_risk_count' | 'loss_positions_count';
  label?: string;
  color?: string;
}

const props = withDefaults(defineProps<Props>(), {
  label: '风险评分',
  color: '',
});

const theme = useThemeStore();

/** 读取当前主题下的 CSS 变量实际值（echarts 在 canvas 里画，吃不到 CSS 变量，
 *  必须解析成具体色值；依赖 theme.resolved 使切换主题时重新计算）。 */
function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

const chartOption = computed<EChartsOption>(() => {
  // 触达 theme.resolved 建立响应依赖：主题切换 → 重算轴线/网格/线色
  const _themeKey = theme.resolved;
  const axisColor = cssVar('--fin-chart-axis', '#8c887e');
  const gridColor = cssVar('--fin-chart-grid', 'rgba(28,25,23,0.08)');
  const seriesColor = props.color || cssVar('--fin-danger', '#d1493f');
  const tooltipBg = cssVar('--fin-text-2', '#5a5751');

  const labels = props.snapshots.map((s) => {
    const date = new Date(s.snapshot_date);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  });

  const values = props.snapshots.map((s) => {
    const val = s[props.metric];
    return val === null ? 0 : val;
  });

  return {
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        label: {
          backgroundColor: tooltipBg,
        },
      },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '10%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLine: {
        lineStyle: {
          color: gridColor,
        },
      },
      axisLabel: {
        color: axisColor,
        fontSize: 11,
      },
    },
    yAxis: {
      type: 'value',
      axisLine: {
        show: false,
      },
      axisTick: {
        show: false,
      },
      axisLabel: {
        color: axisColor,
        fontSize: 11,
      },
      splitLine: {
        lineStyle: {
          color: gridColor,
        },
      },
    },
    series: [
      {
        name: props.label,
        type: 'line',
        smooth: true,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          width: 2,
          color: seriesColor,
        },
        itemStyle: {
          color: seriesColor,
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              {
                offset: 0,
                color: seriesColor + '40',
              },
              {
                offset: 1,
                color: seriesColor + '10',
              },
            ],
          },
        },
        data: values,
      },
    ],
  };
});
</script>

<template>
  <div class="risk-trend-chart">
    <VChart v-if="snapshots.length > 0" :option="chartOption" autoresize style="height: 220px" />
    <div v-else class="risk-trend-empty">
      暂无历史数据
    </div>
  </div>
</template>

<style scoped>
.risk-trend-chart {
  width: 100%;
}
.risk-trend-empty {
  text-align: center;
  padding: 48px 0;
  font-size: 13px;
  color: var(--fin-muted);
}
</style>
