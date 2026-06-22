<script setup lang="ts">
withDefaults(defineProps<{
  label?: string;
  compact?: boolean;
}>(), {
  label: '加载中...',
  compact: false,
});
</script>

<template>
  <div class="finsight-loading-state" :class="{ compact }" role="status" aria-live="polite">
    <span class="loader" aria-hidden="true" />
    <span>{{ label }}</span>
  </div>
</template>

<style scoped>
.finsight-loading-state {
  min-height: 112px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px;
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card-soft);
  color: var(--fin-muted);
  font-size: 13px;
}

.compact {
  min-height: auto;
  justify-content: flex-start;
  padding: 8px 0;
  border: 0;
  background: transparent;
}

.loader {
  width: 15px;
  height: 15px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
