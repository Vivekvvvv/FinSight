<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '@/api/client';
import { marked } from 'marked';

interface ReportRequest {
  ticker: string;
  report_type: 'fundamental' | 'technical' | 'comprehensive';
  include_news: boolean;
  include_technical: boolean;
}

interface ReportResponse {
  report_id: string;
  ticker: string;
  report_type: string;
  title: string;
  content: string;
  generated_at: string;
  data_sources: string[];
}

const route = useRoute();
const ticker = ref('AAPL');
const reportType = ref<'fundamental' | 'technical' | 'comprehensive'>('comprehensive');
const includeNews = ref(true);
const includeTechnical = ref(true);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const report = ref<ReportResponse | null>(null);
const progress = ref(0);

const reportTypeOptions = [
  { value: 'comprehensive', label: '综合分析报告', desc: '结合基本面、技术面和市场情绪的全面分析' },
  { value: 'fundamental', label: '基本面分析报告', desc: '财务健康、估值分析和投资建议' },
  { value: 'technical', label: '技术面分析报告', desc: '价格趋势、技术指标和交易建议' },
];

const renderedContent = ref('');

async function generateReport(): Promise<void> {
  if (!ticker.value.trim()) {
    errorMsg.value = '请输入股票代码';
    return;
  }

  loading.value = true;
  errorMsg.value = null;
  report.value = null;
  progress.value = 0;

  // 模拟进度
  const progressInterval = setInterval(() => {
    if (progress.value < 90) {
      progress.value += 10;
    }
  }, 500);

  try {
    const requestData: ReportRequest = {
      ticker: ticker.value.trim().toUpperCase(),
      report_type: reportType.value,
      include_news: includeNews.value,
      include_technical: includeTechnical.value,
    };

    const response = await apiClient.post('/api/research/report/generate', requestData);
    report.value = response.data;

    // 渲染Markdown内容
    if (report.value) {
      renderedContent.value = marked(report.value.content) as string;
    }

    progress.value = 100;
  } catch (e: any) {
    errorMsg.value = e.response?.data?.detail || e.message || '生成报告失败';
  } finally {
    clearInterval(progressInterval);
    loading.value = false;
  }
}

function downloadPDF(): void {
  if (!report.value) return;

  // TODO: 实现PDF下载功能
  alert('PDF导出功能开发中');
}

function copyMarkdown(): void {
  if (!report.value) return;

  navigator.clipboard.writeText(report.value.content).then(() => {
    alert('Markdown内容已复制到剪贴板');
  }).catch(() => {
    alert('复制失败');
  });
}

onMounted(() => {
  const routeTicker = route.params.ticker as string;
  if (routeTicker) {
    ticker.value = routeTicker;
  }
});
</script>

<template>
  <div class="research-report-page">
    <header class="page-header">
      <h2>AI研究报告生成</h2>
      <p class="muted">使用GPT-4o生成专业的股票研究报告</p>
    </header>

    <section class="control-panel">
      <div class="input-group">
        <label>股票代码</label>
        <input
          v-model="ticker"
          type="text"
          placeholder="例如: AAPL, 600519.SS"
          :disabled="loading"
          @keyup.enter="generateReport"
        />
      </div>

      <div class="input-group">
        <label>报告类型</label>
        <select v-model="reportType" :disabled="loading">
          <option
            v-for="option in reportTypeOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </option>
        </select>
        <span class="option-desc">{{ reportTypeOptions.find(o => o.value === reportType)?.desc }}</span>
      </div>

      <div class="checkbox-group">
        <label>
          <input v-model="includeNews" type="checkbox" :disabled="loading" />
          包含新闻分析
        </label>
        <label>
          <input v-model="includeTechnical" type="checkbox" :disabled="loading" />
          包含技术分析
        </label>
      </div>

      <button
        class="btn-primary"
        :disabled="loading"
        @click="generateReport"
      >
        {{ loading ? '生成中...' : '生成报告' }}
      </button>
    </section>

    <section v-if="loading" class="progress-section">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progress + '%' }"></div>
      </div>
      <p class="progress-text">正在生成报告... {{ progress }}%</p>
    </section>

    <section v-if="errorMsg" class="error-banner">
      {{ errorMsg }}
    </section>

    <section v-if="report && !loading" class="report-section">
      <header class="report-header">
        <h3>{{ report.title }}</h3>
        <div class="report-meta">
          <span>报告ID: {{ report.report_id }}</span>
          <span>生成时间: {{ new Date(report.generated_at).toLocaleString('zh-CN') }}</span>
          <span>数据源: {{ report.data_sources.join(', ') }}</span>
        </div>
        <div class="report-actions">
          <button class="btn-secondary" @click="copyMarkdown">复制Markdown</button>
          <button class="btn-secondary" @click="downloadPDF">下载PDF</button>
        </div>
      </header>

      <article class="report-content markdown-body" v-html="renderedContent"></article>
    </section>

    <section v-if="!report && !loading && !errorMsg" class="empty-state">
      <p>请输入股票代码并选择报告类型开始生成</p>
    </section>
  </div>
</template>

<style scoped>
.research-report-page {
  max-width: 1200px;
  margin: 0 auto;
  display: grid;
  gap: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 28px;
  color: var(--fin-text);
}

.page-header .muted {
  margin: 6px 0 0;
  color: var(--fin-muted);
  font-size: 14px;
}

.control-panel {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 16px;
  align-items: flex-end;
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-group label {
  font-size: 13px;
  font-weight: 600;
  color: var(--fin-text-2);
}

.input-group input,
.input-group select {
  padding: 10px 14px;
  border: 1px solid var(--fin-border);
  border-radius: 12px;
  background: var(--fin-card);
  color: var(--fin-text);
  font-size: 14px;
}

.option-desc {
  font-size: 12px;
  color: var(--fin-muted);
  margin-top: 4px;
}

.checkbox-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--fin-text-2);
  cursor: pointer;
}

.checkbox-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
}

.btn-primary,
.btn-secondary {
  padding: 10px 24px;
  border: 0;
  border-radius: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-primary {
  background: var(--fin-primary);
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--fin-card);
  border: 1px solid var(--fin-border);
  color: var(--fin-text);
}

.progress-section {
  padding: 20px;
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  text-align: center;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--fin-card-inset);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
}

.progress-fill {
  height: 100%;
  background: var(--fin-primary);
  transition: width 0.3s ease;
}

.progress-text {
  margin: 0;
  font-size: 14px;
  color: var(--fin-muted);
}

.error-banner {
  padding: 16px;
  border: 1px solid var(--fin-error);
  border-radius: 12px;
  background: color-mix(in srgb, var(--fin-error) 10%, transparent);
  color: var(--fin-error);
  font-size: 14px;
}

.report-section {
  border: 1px solid var(--fin-border);
  border-radius: 18px;
  background: var(--fin-card-soft);
  overflow: hidden;
}

.report-header {
  padding: 24px;
  border-bottom: 1px solid var(--fin-border);
  background: var(--fin-card);
}

.report-header h3 {
  margin: 0 0 12px;
  font-size: 22px;
  color: var(--fin-text);
}

.report-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.report-meta span {
  font-size: 13px;
  color: var(--fin-muted);
}

.report-actions {
  display: flex;
  gap: 12px;
}

.report-content {
  padding: 32px;
  line-height: 1.8;
  color: var(--fin-text);
}

.markdown-body {
  font-size: 15px;
}

.markdown-body :deep(h1) {
  font-size: 28px;
  margin-top: 32px;
  margin-bottom: 16px;
  border-bottom: 2px solid var(--fin-border);
  padding-bottom: 8px;
}

.markdown-body :deep(h2) {
  font-size: 22px;
  margin-top: 28px;
  margin-bottom: 14px;
}

.markdown-body :deep(h3) {
  font-size: 18px;
  margin-top: 24px;
  margin-bottom: 12px;
}

.markdown-body :deep(p) {
  margin: 12px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin: 12px 0;
}

.markdown-body :deep(li) {
  margin: 6px 0;
}

.markdown-body :deep(code) {
  padding: 2px 6px;
  background: var(--fin-card-inset);
  border-radius: 4px;
  font-family: var(--fin-mono);
  font-size: 13px;
}

.markdown-body :deep(pre) {
  padding: 16px;
  background: var(--fin-card-inset);
  border-radius: 8px;
  overflow-x: auto;
  margin: 16px 0;
}

.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--fin-primary);
  padding-left: 16px;
  margin: 16px 0;
  color: var(--fin-muted);
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 10px;
  border: 1px solid var(--fin-border);
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--fin-card-inset);
  font-weight: 600;
}

.empty-state {
  padding: 60px 20px;
  text-align: center;
  color: var(--fin-muted);
  font-size: 15px;
}

@media (max-width: 768px) {
  .control-panel {
    grid-template-columns: 1fr;
  }

  .report-meta {
    flex-direction: column;
    gap: 8px;
  }

  .report-actions {
    flex-direction: column;
  }

  .report-content {
    padding: 20px;
  }
}
</style>
