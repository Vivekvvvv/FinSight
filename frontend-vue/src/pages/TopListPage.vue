<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient, http } from '@/api/client';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

interface TopListRecord {
  date: string;
  reason: string;
  close_price: number;
  change_percent: number;
  buy_amount: number;
  sell_amount: number;
  net_buy: number;
  turnover_rate: number;
}

interface Seat {
  rank: number;
  seat_name: string;
  buy_amount: number;
  sell_amount: number;
  net_amount: number;
  is_institution: boolean;
}

interface TopListDetail {
  symbol: string;
  stock_code: string;
  stock_name: string;
  date: string;
  reason: string;
  buy_seats: Seat[];
  sell_seats: Seat[];
  buy_amount: number;
  sell_amount: number;
  net_buy: number;
}

const route = useRoute();
const ticker = ref(String(route.params.ticker || '600519.SS'));
const days = ref(7);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const records = ref<TopListRecord[]>([]);
const selectedDetail = ref<TopListDetail | null>(null);
const showSeatModal = ref(false);

const buyChartContainer = ref<HTMLElement | null>(null);
const institutionChartContainer = ref<HTMLElement | null>(null);
let buyChartInstance: echarts.ECharts | null = null;
let institutionChartInstance: echarts.ECharts | null = null;

const totalRecords = computed(() => records.value.length);
const avgNetBuy = computed(() => {
  if (records.value.length === 0) return 0;
  const sum = records.value.reduce((acc, r) => acc + r.net_buy, 0);
  return sum / records.value.length;
});

function formatMoney(value: number): string {
  if (value >= 100000000) {
    return (value / 100000000).toFixed(2) + '亿';
  } else if (value >= 10000) {
    return (value / 10000).toFixed(2) + '万';
  }
  return value.toFixed(2);
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
}

async function loadHistory(): Promise<void> {
  loading.value = true;
  errorMsg.value = null;
  try {
    const resp = await http.get(`/api/stock/top-list/${ticker.value}/history?days=${days.value}`);
    records.value = resp.data.records || [];

    if (records.value.length > 0) {
      renderBuyVsSellChart();
    }
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function viewDetail(record: TopListRecord): Promise<void> {
  try {
    const resp = await http.get(`/api/stock/top-list/${ticker.value}?include_seats=true`);
    selectedDetail.value = resp.data;
    showSeatModal.value = true;

    setTimeout(() => {
      renderInstitutionChart();
    }, 100);
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e);
  }
}

function closeModal(): void {
  showSeatModal.value = false;
  selectedDetail.value = null;
}

function renderBuyVsSellChart(): void {
  if (!buyChartContainer.value || records.value.length === 0) return;

  if (!buyChartInstance) {
    buyChartInstance = echarts.init(buyChartContainer.value);
  }

  const dates = records.value.map(r => formatDate(r.date)).reverse();
  const buyAmounts = records.value.map(r => r.buy_amount / 100000000).reverse();  // 转为亿元
  const sellAmounts = records.value.map(r => r.sell_amount / 100000000).reverse();

  const option: EChartsOption = {
    title: {
      text: '买卖金额对比',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: any) => {
        const date = params[0].name;
        const buy = params[0].value.toFixed(2);
        const sell = params[1].value.toFixed(2);
        return `${date}<br/>买入: ${buy}亿<br/>卖出: ${sell}亿`;
      }
    },
    legend: {
      data: ['买入金额', '卖出金额'],
      top: 30
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 80,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLabel: { fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      name: '金额（亿元）',
      axisLabel: { formatter: '{value}' }
    },
    series: [
      {
        name: '买入金额',
        type: 'bar',
        data: buyAmounts,
        itemStyle: { color: '#52c41a' }
      },
      {
        name: '卖出金额',
        type: 'bar',
        data: sellAmounts,
        itemStyle: { color: '#ff4d4f' }
      }
    ]
  };

  buyChartInstance.setOption(option);
}

function renderInstitutionChart(): void {
  if (!institutionChartContainer.value || !selectedDetail.value) return;

  if (!institutionChartInstance) {
    institutionChartInstance = echarts.init(institutionChartContainer.value);
  }

  const buySeats = selectedDetail.value.buy_seats || [];
  const institutionCount = buySeats.filter(s => s.is_institution).length;
  const otherCount = buySeats.length - institutionCount;

  const option: EChartsOption = {
    title: {
      text: '买入席位机构占比',
      left: 'center',
      textStyle: { fontSize: 14, fontWeight: 600 }
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 50
    },
    series: [
      {
        name: '席位类型',
        type: 'pie',
        radius: '60%',
        center: ['50%', '60%'],
        data: [
          { value: institutionCount, name: '机构专用', itemStyle: { color: '#1890ff' } },
          { value: otherCount, name: '普通席位', itemStyle: { color: '#d9d9d9' } }
        ],
        label: {
          formatter: '{b}: {c}席\n({d}%)'
        }
      }
    ]
  };

  institutionChartInstance.setOption(option);
}

onMounted(() => {
  void loadHistory();
});
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1 class="page-title">龙虎榜</h1>
        <p class="subtitle">大额交易与机构席位追踪</p>
      </div>
      <div class="controls">
        <label>
          股票代码
          <input v-model="ticker" class="input" placeholder="600519.SS">
        </label>
        <label>
          时间范围
          <select v-model="days" class="select">
            <option :value="7">最近7天</option>
            <option :value="30">最近30天</option>
            <option :value="90">最近90天</option>
          </select>
        </label>
        <button class="btn-primary" :disabled="loading" @click="loadHistory">
          {{ loading ? '查询中...' : '查询' }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <div v-if="totalRecords > 0" class="stats-row">
      <div class="stat-card">
        <div class="stat-label">上榜次数</div>
        <div class="stat-value">{{ totalRecords }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">平均净买额</div>
        <div class="stat-value" :class="{ positive: avgNetBuy > 0, negative: avgNetBuy < 0 }">
          {{ formatMoney(avgNetBuy) }}
        </div>
      </div>
    </div>

    <div v-if="records.length > 0" class="chart-card">
      <div ref="buyChartContainer" class="chart-container" />
    </div>

    <div v-if="records.length > 0" class="table-card">
      <h3>历史记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>日期</th>
            <th>上榜原因</th>
            <th>收盘价</th>
            <th>涨跌幅</th>
            <th>买入金额</th>
            <th>卖出金额</th>
            <th>净买额</th>
            <th>换手率</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in records" :key="record.date">
            <td>{{ record.date }}</td>
            <td>{{ record.reason }}</td>
            <td>{{ record.close_price.toFixed(2) }}</td>
            <td :class="{ positive: record.change_percent > 0, negative: record.change_percent < 0 }">
              {{ record.change_percent.toFixed(2) }}%
            </td>
            <td>{{ formatMoney(record.buy_amount) }}</td>
            <td>{{ formatMoney(record.sell_amount) }}</td>
            <td :class="{ positive: record.net_buy > 0, negative: record.net_buy < 0 }">
              {{ formatMoney(record.net_buy) }}
            </td>
            <td>{{ record.turnover_rate.toFixed(2) }}%</td>
            <td>
              <button class="btn-link" @click="viewDetail(record)">席位详情</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="!loading" class="empty-state">
      暂无龙虎榜数据
    </div>

    <!-- 席位详情弹窗 -->
    <div v-if="showSeatModal" class="modal-overlay" @click="closeModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>席位明细 - {{ selectedDetail?.stock_name }}</h3>
          <button class="btn-close" @click="closeModal">✕</button>
        </div>

        <div class="modal-body">
          <div class="chart-row">
            <div ref="institutionChartContainer" class="small-chart" />
          </div>

          <div class="seats-section">
            <h4>买入前5席位</h4>
            <table class="seat-table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>席位名称</th>
                  <th>买入金额</th>
                  <th>卖出金额</th>
                  <th>净买额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="seat in selectedDetail?.buy_seats" :key="seat.rank" :class="{ institution: seat.is_institution }">
                  <td>{{ seat.rank }}</td>
                  <td>
                    {{ seat.seat_name }}
                    <span v-if="seat.is_institution" class="badge">机构</span>
                  </td>
                  <td>{{ formatMoney(seat.buy_amount) }}</td>
                  <td>{{ formatMoney(seat.sell_amount) }}</td>
                  <td :class="{ positive: seat.net_amount > 0 }">{{ formatMoney(seat.net_amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="seats-section">
            <h4>卖出前5席位</h4>
            <table class="seat-table">
              <thead>
                <tr>
                  <th>排名</th>
                  <th>席位名称</th>
                  <th>买入金额</th>
                  <th>卖出金额</th>
                  <th>净买额</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="seat in selectedDetail?.sell_seats" :key="seat.rank" :class="{ institution: seat.is_institution }">
                  <td>{{ seat.rank }}</td>
                  <td>
                    {{ seat.seat_name }}
                    <span v-if="seat.is_institution" class="badge">机构</span>
                  </td>
                  <td>{{ formatMoney(seat.buy_amount) }}</td>
                  <td>{{ formatMoney(seat.sell_amount) }}</td>
                  <td :class="{ negative: seat.net_amount < 0 }">{{ formatMoney(seat.net_amount) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  flex-wrap: wrap;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0;
  color: var(--fin-text);
}

.subtitle {
  margin: 4px 0 0;
  color: var(--fin-muted);
  font-size: 14px;
}

.controls {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
}

.controls label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--fin-muted);
}

.input,
.select {
  padding: 9px 12px;
  border: 1.5px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 13px;
}

.btn-primary {
  padding: 9px 16px;
  border: 0;
  border-radius: 8px;
  background: var(--fin-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  padding: 12px 16px;
  background: #fff1f0;
  border: 1.5px solid #ffccc7;
  border-radius: 10px;
  color: #cf1322;
  font-size: 14px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
}

.stat-card {
  padding: 16px 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
}

.stat-label {
  font-size: 12px;
  color: var(--fin-muted);
  font-weight: 600;
  margin-bottom: 8px;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--fin-text);
}

.stat-value.positive { color: #52c41a; }
.stat-value.negative { color: #ff4d4f; }

.chart-card,
.table-card {
  padding: 20px;
  background: var(--fin-card);
  border: 1.5px solid var(--fin-border);
  border-radius: 14px;
}

.chart-container {
  width: 100%;
  height: 350px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid var(--fin-border);
}

.data-table th {
  font-weight: 700;
  color: var(--fin-muted);
  background: var(--fin-card-inset);
}

.data-table td.positive { color: #52c41a; font-weight: 600; }
.data-table td.negative { color: #ff4d4f; font-weight: 600; }

.btn-link {
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: var(--fin-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: underline;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--fin-muted);
  font-size: 14px;
}

/* 弹窗样式 */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  width: 90%;
  max-width: 900px;
  max-height: 90vh;
  overflow: auto;
  background: var(--fin-card);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1.5px solid var(--fin-border);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
}

.btn-close {
  padding: 8px 12px;
  border: 0;
  background: transparent;
  color: var(--fin-muted);
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}

.modal-body {
  padding: 20px;
}

.chart-row {
  margin-bottom: 24px;
}

.small-chart {
  width: 100%;
  height: 280px;
}

.seats-section {
  margin-bottom: 24px;
}

.seats-section h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 700;
}

.seat-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.seat-table th,
.seat-table td {
  padding: 10px;
  text-align: left;
  border-bottom: 1px solid var(--fin-border);
}

.seat-table th {
  font-weight: 700;
  color: var(--fin-muted);
  background: var(--fin-card-inset);
}

.seat-table tr.institution {
  background: rgba(24, 144, 255, 0.05);
}

.badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  background: #1890ff;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  margin-left: 6px;
}

.seat-table td.positive { color: #52c41a; font-weight: 600; }
.seat-table td.negative { color: #ff4d4f; font-weight: 600; }

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .controls {
    width: 100%;
  }

  .modal-content {
    width: 95%;
    max-height: 95vh;
  }
}
</style>
