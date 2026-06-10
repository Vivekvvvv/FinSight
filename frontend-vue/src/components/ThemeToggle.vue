<script setup lang="ts">
import { computed } from 'vue';
import { useThemeStore, type ThemePreference } from '@/stores/theme';

const theme = useThemeStore();

const options: Array<{ value: ThemePreference; label: string; short: string }> = [
  { value: 'dark', label: '深色终端', short: '深' },
  { value: 'light', label: '浅色纸面', short: '浅' },
  { value: 'system', label: '跟随系统', short: '自' },
];

const activeLabel = computed(() => options.find((item) => item.value === theme.preference)?.label || '跟随系统');
</script>

<template>
  <div class="theme-toggle" :title="`当前主题：${activeLabel}`">
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :class="{ active: theme.preference === option.value }"
      :aria-pressed="theme.preference === option.value"
      @click="theme.setPreference(option.value)"
    >
      <span>{{ option.short }}</span>
      <em>{{ option.label }}</em>
    </button>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--fin-border);
  border-radius: 999px;
  background: var(--fin-card-soft);
}

.theme-toggle button {
  border: 0;
  border-radius: 999px;
  padding: 7px 9px;
  background: transparent;
  color: var(--fin-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 800;
  white-space: nowrap;
}

.theme-toggle button.active {
  background: var(--fin-primary);
  color: var(--fin-bg);
}

.theme-toggle span {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  font-size: 11px;
  font-weight: 900;
}

.theme-toggle em {
  font-style: normal;
  font-size: 12px;
}

@media (max-width: 960px) {
  .theme-toggle em {
    display: none;
  }
}
</style>
