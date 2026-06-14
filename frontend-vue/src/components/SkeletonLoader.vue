<template>
  <div class="skeleton-loader">
    <!-- 卡片骨架 -->
    <div v-if="type === 'card'" class="skeleton-card">
      <div class="skeleton-header">
        <div class="skeleton-avatar"></div>
        <div class="skeleton-title-group">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-subtitle"></div>
        </div>
      </div>
      <div class="skeleton-content">
        <div v-for="i in 3" :key="i" class="skeleton-line"></div>
      </div>
    </div>

    <!-- 表格骨架 -->
    <div v-else-if="type === 'table'" class="skeleton-table">
      <div class="skeleton-table-header">
        <div v-for="i in columns" :key="i" class="skeleton-line"></div>
      </div>
      <div v-for="row in rows" :key="row" class="skeleton-table-row">
        <div v-for="col in columns" :key="col" class="skeleton-line"></div>
      </div>
    </div>

    <!-- 列表骨架 -->
    <div v-else-if="type === 'list'" class="skeleton-list">
      <div v-for="i in count" :key="i" class="skeleton-list-item">
        <div class="skeleton-avatar-small"></div>
        <div class="skeleton-text-group">
          <div class="skeleton-line"></div>
          <div class="skeleton-line skeleton-line-short"></div>
        </div>
      </div>
    </div>

    <!-- 图表骨架 -->
    <div v-else-if="type === 'chart'" class="skeleton-chart">
      <div class="skeleton-chart-header">
        <div class="skeleton-line skeleton-title"></div>
        <div class="skeleton-line skeleton-subtitle"></div>
      </div>
      <div class="skeleton-chart-body">
        <div class="skeleton-bars">
          <div v-for="i in 8" :key="i" class="skeleton-bar" :style="{ height: `${Math.random() * 60 + 20}%` }"></div>
        </div>
      </div>
    </div>

    <!-- 文本骨架（默认） -->
    <div v-else class="skeleton-text">
      <div v-for="i in lines" :key="i" class="skeleton-line" :class="{ 'skeleton-line-short': i === lines }"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { withDefaults } from 'vue';

interface Props {
  type?: 'card' | 'table' | 'list' | 'chart' | 'text';
  lines?: number;
  count?: number;
  rows?: number;
  columns?: number;
}

withDefaults(defineProps<Props>(), {
  type: 'text',
  lines: 3,
  count: 5,
  rows: 5,
  columns: 4,
});
</script>

<style scoped>
.skeleton-loader {
  width: 100%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

@keyframes shimmer {
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
}

.skeleton-line {
  height: 16px;
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
  border-radius: 4px;
  margin-bottom: 12px;
}

.skeleton-line-short {
  width: 60%;
}

/* 卡片骨架 */
.skeleton-card {
  background: white;
  border-radius: 8px;
  padding: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.skeleton-header {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.skeleton-avatar {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
  flex-shrink: 0;
}

.skeleton-title-group {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-title {
  width: 40%;
  height: 20px;
}

.skeleton-subtitle {
  width: 30%;
  height: 16px;
}

.skeleton-content {
  margin-top: 16px;
}

/* 表格骨架 */
.skeleton-table {
  background: white;
  border-radius: 8px;
  padding: 16px;
}

.skeleton-table-header {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.skeleton-table-row {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(100px, 1fr));
  margin-bottom: 12px;
}

/* 列表骨架 */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.skeleton-list-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: white;
  border-radius: 8px;
}

.skeleton-avatar-small {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
  flex-shrink: 0;
}

.skeleton-text-group {
  flex: 1;
}

/* 图表骨架 */
.skeleton-chart {
  background: white;
  border-radius: 8px;
  padding: 20px;
  height: 300px;
}

.skeleton-chart-header {
  margin-bottom: 20px;
}

.skeleton-chart-body {
  height: 220px;
  display: flex;
  align-items: flex-end;
  padding: 20px 0;
}

.skeleton-bars {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
  height: 100%;
}

.skeleton-bar {
  flex: 1;
  background: linear-gradient(
    90deg,
    #f0f0f0 25%,
    #e0e0e0 50%,
    #f0f0f0 75%
  );
  background-size: 1000px 100%;
  animation: shimmer 2s infinite;
  border-radius: 4px 4px 0 0;
}

/* 文本骨架 */
.skeleton-text {
  padding: 16px;
}
</style>
