<template>
  <Transition name="fade">
    <div v-if="isLoading" class="global-loading-overlay">
      <div class="loading-spinner">
        <div class="spinner"></div>
        <p class="loading-text">{{ message }}</p>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { onLoadingChange, resetGlobalLoading } from '@/api/client';

const isLoading = ref(false);
const message = ref('加载中...');

let unsubscribe: (() => void) | null = null;
let hintTimer: number | null = null;
let safetyTimer: number | null = null;

function clearTimers() {
  if (hintTimer != null) window.clearTimeout(hintTimer);
  if (safetyTimer != null) window.clearTimeout(safetyTimer);
  hintTimer = null;
  safetyTimer = null;
}

onMounted(() => {
  unsubscribe = onLoadingChange((loading) => {
    isLoading.value = loading;
    clearTimers();

    if (!loading) return;

    message.value = '加载中...';
    hintTimer = window.setTimeout(() => {
      if (isLoading.value) {
        message.value = '数据源切换中，请稍候...';
      }
    }, 15_000);

    safetyTimer = window.setTimeout(() => {
      if (isLoading.value) {
        resetGlobalLoading();
        isLoading.value = false;
      }
    }, 20_000);
  });
});

onUnmounted(() => {
  unsubscribe?.();
  clearTimers();
});
</script>

<style scoped>
.global-loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  pointer-events: none;
}

.loading-spinner {
  background: white;
  border-radius: 12px;
  padding: 24px 32px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--fin-border);
  border-top: 3px solid var(--fin-primary);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.loading-text {
  margin: 0;
  color: var(--fin-muted);
  font-size: 14px;
  font-weight: 500;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
