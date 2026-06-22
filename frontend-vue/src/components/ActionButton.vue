<script setup lang="ts">
type ButtonType = 'button' | 'submit' | 'reset';
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

const props = withDefaults(defineProps<{
  type?: ButtonType;
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  disabled?: boolean;
  loadingText?: string;
  ariaLabel?: string;
}>(), {
  type: 'button',
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  loadingText: '处理中...',
  ariaLabel: '',
});

const emit = defineEmits<{
  click: [event: MouseEvent];
}>();

function handleClick(event: MouseEvent): void {
  if (props.loading || props.disabled) {
    event.preventDefault();
    return;
  }
  emit('click', event);
}
</script>

<template>
  <button
    class="finsight-action-button"
    :class="[`is-${variant}`, `is-${size}`, { 'is-loading': loading }]"
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading"
    :aria-label="ariaLabel || undefined"
    @click="handleClick"
  >
    <span v-if="loading" class="spinner" aria-hidden="true" />
    <span class="label">
      <template v-if="loading">{{ loadingText }}</template>
      <slot v-else />
    </span>
  </button>
</template>

<style scoped>
.finsight-action-button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 700;
  white-space: nowrap;
}

.is-sm {
  min-height: 30px;
  padding: 5px 10px;
  font-size: 12px;
}

.is-md {
  padding: 8px 14px;
  font-size: 13px;
}

.is-primary {
  background: var(--fin-primary);
  color: #111827;
}

.is-secondary {
  border-color: var(--fin-border-strong);
  background: var(--fin-primary-soft);
  color: var(--fin-primary);
}

.is-ghost {
  border-color: var(--fin-border);
  background: var(--fin-card);
  color: var(--fin-text-2);
}

.is-danger {
  border-color: var(--fin-danger);
  background: var(--fin-danger-soft);
  color: var(--fin-danger);
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

.label {
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
