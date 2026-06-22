<script setup lang="ts">
type StatusVariant = 'info' | 'success' | 'warning' | 'error';

withDefaults(defineProps<{
  variant?: StatusVariant;
  title?: string;
  message?: string | null;
  actionLabel?: string;
  dismissible?: boolean;
}>(), {
  variant: 'info',
  title: '',
  message: '',
  actionLabel: '',
  dismissible: false,
});

const emit = defineEmits<{
  action: [];
  dismiss: [];
}>();
</script>

<template>
  <div class="finsight-status-banner" :class="`is-${variant}`" role="status">
    <span class="status-dot" aria-hidden="true" />
    <div class="status-copy">
      <strong v-if="title">{{ title }}</strong>
      <span v-if="message">{{ message }}</span>
      <slot />
    </div>
    <button v-if="actionLabel" class="status-action" type="button" @click="emit('action')">
      {{ actionLabel }}
    </button>
    <button v-if="dismissible" class="status-close" type="button" aria-label="关闭提示" @click="emit('dismiss')">
      ×
    </button>
  </div>
</template>

<style scoped>
.finsight-status-banner {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: start;
  gap: 10px;
  padding: 11px 13px;
  border: 1px solid var(--fin-border);
  border-radius: 8px;
  background: var(--fin-card);
  color: var(--fin-text-2);
  font-size: 13px;
  line-height: 1.55;
}

.status-dot {
  width: 8px;
  height: 8px;
  margin-top: 7px;
  border-radius: 999px;
  background: var(--fin-accent);
}

.status-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.status-copy strong {
  color: var(--fin-text);
}

.status-action,
.status-close {
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-weight: 700;
}

.status-action {
  color: var(--fin-primary);
  white-space: nowrap;
}

.status-close {
  width: 26px;
  height: 26px;
  padding: 0;
  border-radius: 999px;
  font-size: 18px;
  line-height: 1;
}

.is-error {
  border-color: color-mix(in srgb, var(--fin-danger) 44%, transparent);
  background: var(--fin-danger-soft);
  color: var(--fin-text);
}

.is-error .status-dot { background: var(--fin-danger); }
.is-warning {
  border-color: color-mix(in srgb, var(--fin-warning) 44%, transparent);
  background: var(--fin-warning-soft);
}
.is-warning .status-dot { background: var(--fin-warning); }
.is-success {
  border-color: color-mix(in srgb, var(--fin-success) 44%, transparent);
  background: var(--fin-success-soft);
}
.is-success .status-dot { background: var(--fin-success); }

@media (max-width: 520px) {
  .finsight-status-banner {
    grid-template-columns: auto 1fr auto;
  }

  .status-action {
    grid-column: 2 / -1;
    justify-self: start;
  }
}
</style>
