<script setup lang="ts">
import { computed } from 'vue';
import VChart from 'vue-echarts';
import type { EChartsOption } from 'echarts';
import type { RiskSnapshot } from '@/api/types';

interface Props {
  snapshots: RiskSnapshot[];
  metric: 'risk_score' | 'total_value' | 'concentration_risk_count' | 'loss_positions_count';
  label?: string;
  color?: string;
}

const props = withDefaults(defineProps<Props>(), {
  label: '风险评分',
  color: '#ef4444',
});

const chartOption = computed<EChartsOption>(() => {
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
          backgroundColor: '#6a7985',
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
          color: '#e5e7eb',
        },
      },
      axisLabel: {
        color: '#6b7280',
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
        color: '#6b7280',
        fontSize: 11,
      },
      splitLine: {
        lineStyle: {
          color: '#f3f4f6',
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
          color: props.color,
        },
        itemStyle: {
          color: props.color,
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
                color: props.color + '40',
              },
              {
                offset: 1,
                color: props.color + '10',
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
    <div v-else class="text-gray-500 text-center py-12 text-sm">
      暂无历史数据
    </div>
  </div>
</template>

<style scoped>
.risk-trend-chart {
  width: 100%;
}
</style>
